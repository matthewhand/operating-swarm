"""OpenAI-compatible image generation (REQ-83 / #436).

Settings persist an opt-in ``image_gen`` block on ``swarm_config.json``:
base URL, model id, and an api-key **env name** only. Empty/off never
guesses a host (no OpenAI / LiteLLM / LAN default). Generated stills are
PNG/JPEG/WebP files under avatar storage — not GIF/APNG/video, and not
Blob theme eyes.
"""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import re
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

ENV_CONFIG_PATH = "SWARM_CONFIG_PATH"
ENV_AVATARS_PATH = "SWARM_AGENT_AVATARS_PATH"
ENV_AVATAR_STORAGE = "SWARM_AVATAR_STORAGE"

_FORBIDDEN_BASE_HINTS = ("fly.dev", "open-litellm", "openlitellm")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ID_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+$")

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_JPEG_SIG = b"\xff\xd8\xff"
_GIF_SIGS = (b"GIF87a", b"GIF89a")
_WEBP_RIFF = b"RIFF"
_WEBP_WEBP = b"WEBP"
_ACTL = b"acTL"
_ANIM = b"ANIM"

_DEFAULT_TIMEOUT_S = 3.0
_GENERATE_TIMEOUT_S = 30.0


class ImageGenError(Exception):
    """User-facing image-gen failure (not configured, DOWN, not still)."""


@dataclass
class ImageGenSettings:
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    api_key_env: str = ""
    source: str = "off"

    def configured(self) -> bool:
        return bool(self.base_url.strip())

    def public_dict(self) -> dict[str, Any]:
        key = str(self.api_key or "")
        return {
            "object": "image_gen",
            "configured": self.configured(),
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_set": bool(key) and not _is_unresolved_placeholder(key),
            "source": self.source,
        }


def _placeholder_env_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
        inner = raw[2:-1].strip()
        if inner and _ENV_NAME_RE.match(inner):
            return inner
    return ""


def _as_env_name(value: str) -> str:
    raw = (value or "").strip()
    derived = _placeholder_env_name(raw)
    if derived:
        return derived
    if raw and _ENV_NAME_RE.match(raw):
        return raw
    return ""


def _is_unresolved_placeholder(value: str) -> bool:
    raw = (value or "").strip()
    return raw.startswith("${") and raw.endswith("}") and len(raw) > 3


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        expanded = os.path.expandvars(value)
        if _is_unresolved_placeholder(expanded):
            return ""
        return expanded
    return value


def _normalize_base_url(url: str) -> str:
    raw = (url or "").strip().rstrip("/")
    if not raw:
        return ""
    if "://" not in raw:
        raise ImageGenError(
            "Image generation base URL must include a scheme (http:// or https://). "
            "Refusing to auto-prepend http:// for security."
        )
    return raw


def _looks_like_forbidden_llm_proxy(url: str) -> bool:
    lowered = (url or "").lower()
    return any(hint in lowered for hint in _FORBIDDEN_BASE_HINTS)


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    from swarm.core.config_loader import find_config_file

    if explicit:
        return Path(explicit).expanduser()
    found = find_config_file()
    if found:
        return found
    return get_user_config_dir_for_swarm() / "swarm_config.json"


def load_raw_config(config_path: str | Path | None = None) -> tuple[dict[str, Any], Path]:
    path = resolve_config_path(config_path)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data, path
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("image_gen: failed to read %s: %s", path, exc)
    return {}, path


def load_settings(config: dict[str, Any] | None = None) -> ImageGenSettings:
    """Defaults ← swarm_config.json image_gen ← env (env wins for URL/model/key)."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    block = cfg.get("image_gen") if isinstance(cfg.get("image_gen"), dict) else {}
    spec = ImageGenSettings()
    if isinstance(block, dict) and block:
        spec.source = "config"
        if block.get("base_url") is not None:
            spec.base_url = str(block.get("base_url") or "")
        if block.get("model") is not None:
            spec.model = str(block.get("model") or "")
        if block.get("api_key") is not None:
            spec.api_key = str(block.get("api_key") or "")
        if block.get("api_key_env") is not None:
            spec.api_key_env = str(block.get("api_key_env") or "")
    env_base = os.environ.get("IMAGE_GEN_BASE_URL", "").strip()
    if env_base:
        spec.base_url = env_base
        spec.source = "env"
    env_model = os.environ.get("IMAGE_GEN_MODEL", "").strip()
    if env_model:
        spec.model = env_model
    env_key_name = spec.api_key_env or os.environ.get("IMAGE_GEN_API_KEY_ENV", "").strip()
    if env_key_name:
        spec.api_key_env = env_key_name
    env_key = os.environ.get(spec.api_key_env, "").strip() if spec.api_key_env else ""
    if env_key:
        spec.api_key = env_key
    elif spec.api_key:
        spec.api_key = str(_expand(spec.api_key) or "")
    if not spec.api_key_env:
        spec.api_key_env = _placeholder_env_name(str(block.get("api_key") or ""))
    spec.base_url = _normalize_base_url(spec.base_url)
    return spec


def is_configured(config: dict[str, Any] | None = None) -> bool:
    return load_settings(config).configured()


def persist_settings(
    *,
    base_url: str | None = None,
    model: str | None = None,
    api_key_env: str | None = None,
    config_path: str | Path | None = None,
) -> tuple[ImageGenSettings, Path]:
    """Merge fields into ``image_gen`` and write swarm_config.json.

    Stores api-key-env as ``${ENV}`` only. Empty base URL stays empty — never
    invents a host.
    """
    cfg, path = load_raw_config(config_path)
    entry = cfg.get("image_gen") if isinstance(cfg.get("image_gen"), dict) else {}
    entry = dict(entry)
    if base_url is not None:
        normalized = _normalize_base_url(base_url)
        if normalized and _looks_like_forbidden_llm_proxy(normalized):
            raise ImageGenError(
                "Refusing to persist a Fly open-litellm URL as the image-gen host. "
                "Set the OpenAI-compatible images endpoint you actually run."
            )
        entry["base_url"] = normalized
    if model is not None:
        entry["model"] = (model or "").strip()
    if api_key_env is not None:
        env_name = _as_env_name(api_key_env)
        entry["api_key_env"] = env_name
        if env_name:
            entry["api_key"] = f"${{{env_name}}}"
        else:
            entry.pop("api_key", None)
    cfg["image_gen"] = entry
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    logger.info("Persisted image_gen to %s", path)
    return load_settings(cfg), path


def generations_url(base_url: str) -> str:
    """``{base}/v1/images/generations`` without inventing a host when base is empty."""
    raw = _normalize_base_url(base_url)
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    if path.endswith("/v1/images/generations"):
        return raw
    if path.endswith("/images/generations"):
        return raw
    if path.endswith("/v1"):
        return f"{raw}/images/generations"
    return f"{raw}/v1/images/generations"


def probe_status(settings: ImageGenSettings | None = None) -> dict[str, Any]:
    """Honest reachability. Empty/off does not call any host."""
    spec = settings if settings is not None else load_settings()
    pub = spec.public_dict()
    if not spec.configured():
        pub["status"] = "off"
        pub["detail"] = "Image generation is off. No host is used until you set a base URL."
        return pub
    url = generations_url(spec.base_url)
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT_S) as resp:
            code = int(getattr(resp, "status", 200) or 200)
        pub["status"] = "ok"
        pub["detail"] = f"Image generation endpoint answered HTTP {code}."
        pub["http_status"] = code
        return pub
    except urllib.error.HTTPError as exc:
        if exc.fp:
            with contextlib.suppress(Exception):
                exc.fp.close()
        pub["status"] = "ok"
        pub["detail"] = f"Image generation endpoint answered HTTP {exc.code}."
        pub["http_status"] = int(exc.code)
        return pub
    except Exception as exc:
        pub["status"] = "down"
        pub["detail"] = f"Image generation endpoint is DOWN: {exc}"
        pub["http_status"] = None
        return pub


def _is_still_image(payload: bytes) -> bool:
    """True for a single-frame PNG/JPEG/WebP. Rejects GIF/APNG/animated WebP."""
    if not payload:
        return False
    if payload.startswith(_GIF_SIGS):
        return False
    if payload.startswith(_PNG_SIG):
        return _ACTL not in payload[:8192]
    if payload.startswith(_JPEG_SIG):
        return True
    if payload.startswith(_WEBP_RIFF) and payload[8:12] == _WEBP_WEBP:
        return _ANIM not in payload[:64] and b"ANIM" not in payload[:256]
    return False


def _decode_generation_body(body: bytes, content_type: str) -> bytes:
    ctype = (content_type or "").split(";")[0].strip().lower()
    if ctype.startswith("image/") or body.startswith((_PNG_SIG, _JPEG_SIG) + _GIF_SIGS) or (
        body.startswith(_WEBP_RIFF) and body[8:12] == _WEBP_WEBP
    ):
        return body
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImageGenError("Image generation response was not JSON or image bytes.") from exc
    data = parsed.get("data") if isinstance(parsed, dict) else None
    first = data[0] if isinstance(data, list) and data else None
    if not isinstance(first, dict):
        raise ImageGenError("Image generation response had no data[0] image.")
    b64 = first.get("b64_json")
    if isinstance(b64, str) and b64.strip():
        try:
            return base64.b64decode(b64, validate=False)
        except Exception as exc:
            raise ImageGenError("Image generation b64_json was not valid base64.") from exc
    raise ImageGenError("Image generation response had no b64_json still image.")


def generate_still(
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    opener=None,
    timeout: float = _GENERATE_TIMEOUT_S,
) -> bytes:
    """POST ``/v1/images/generations``. Empty URL does not call any host."""
    spec = settings if settings is not None else load_settings()
    url = generations_url(spec.base_url)
    if not url:
        raise ImageGenError(
            "Image generation is not configured. Set a base URL in Settings → Image generation."
        )
    parsed = urlparse(url)
    if (
        parsed.scheme == "http"
        and parsed.hostname not in ("localhost", "127.0.0.1", "::1", "[::1]")
        and spec.api_key
        and not _is_unresolved_placeholder(spec.api_key)
    ):
        raise ImageGenError(
            "Insecure HTTP connection with API key is not permitted for remote hosts. "
            "Use HTTPS to protect credentials."
        )
    text = (prompt or "").strip()
    if not text:
        raise ImageGenError("Provide a prompt for the still avatar.")
    payload: dict[str, Any] = {
        "prompt": text,
        "n": 1,
        "response_format": "b64_json",
    }
    if spec.model.strip():
        payload["model"] = spec.model.strip()
    body = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if spec.api_key and not _is_unresolved_placeholder(spec.api_key):
        headers["Authorization"] = f"Bearer {spec.api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    call = opener or urllib.request.urlopen
    try:
        with call(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = ""
            try:
                ctype = resp.headers.get("Content-Type", "")
            except Exception:
                ctype = ""
    except urllib.error.HTTPError as exc:
        detail = ""
        if exc.fp:
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:240]
            finally:
                with contextlib.suppress(Exception):
                    exc.fp.close()
        raise ImageGenError(
            f"Image generation endpoint returned HTTP {exc.code}. {detail}".strip()
        ) from exc
    except ImageGenError:
        raise
    except Exception as exc:
        raise ImageGenError(f"Image generation endpoint is DOWN: {exc}") from exc
    image = _decode_generation_body(raw, ctype)
    if not _is_still_image(image):
        raise ImageGenError("Generated image is not a still (GIF/APNG/video rejected).")
    return image


def avatars_path() -> Path:
    env = (os.environ.get(ENV_AVATARS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_avatars.json"


def avatar_storage_dir() -> Path:
    env = (os.environ.get(ENV_AVATAR_STORAGE) or "").strip()
    if env:
        return Path(env)
    try:
        from django.conf import settings

        return Path(settings.AVATAR_STORAGE_PATH)
    except Exception:
        return Path("avatars")


def avatar_url_prefix() -> str:
    try:
        from django.conf import settings

        prefix = str(getattr(settings, "AVATAR_URL_PREFIX", "/avatars/") or "/avatars/")
    except Exception:
        prefix = "/avatars/"
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix.endswith("/"):
        prefix += "/"
    return prefix


def _empty_avatar_store() -> dict[str, Any]:
    return {"schema": 1, "avatars": {}}


def load_avatar_map() -> dict[str, str]:
    path = avatars_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    raw = data.get("avatars")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        agent = normalize_agent_id(str(key))
        url = ""
        if isinstance(value, str):
            url = value.strip()
        elif isinstance(value, dict):
            url = str(value.get("avatar_path") or value.get("url") or "").strip()
        if agent and url:
            out[agent] = url
    return out


_avatar_map_lock = threading.Lock()


def _write_avatar_map(mapping: dict[str, str]) -> None:
    path = avatars_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": 1, "avatars": dict(mapping)}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def avatar_path_for(agent_id: str) -> str | None:
    agent = normalize_agent_id(agent_id)
    return load_avatar_map().get(agent)


def _safe_stem(agent_id: str) -> str:
    raw = (agent_id or "").strip()
    if not raw or "/" in raw or "\\" in raw or ".." in raw:
        raise ImageGenError("Agent id is not safe for an avatar filename.")
    agent = normalize_agent_id(raw)
    if agent in (".", "..") or not _ID_FILE_RE.match(agent):
        raise ImageGenError("Agent id is not safe for an avatar filename.")
    return agent


def store_still_avatar(agent_id: str, image: bytes) -> str:
    """Write a still image and record the per-agent slot. Replaces the previous file."""
    if not _is_still_image(image):
        raise ImageGenError("Stored avatar must be a still image (not GIF/APNG/video).")
    stem = _safe_stem(agent_id)
    root = avatar_storage_dir().resolve()
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{stem}_still.png"
    dest = (root / filename).resolve()
    if not dest.is_relative_to(root) or dest.parent != root:
        raise ImageGenError("Avatar path escaped storage root.")
    dest.write_bytes(image)
    url = f"{avatar_url_prefix()}{filename}"
    with _avatar_map_lock:
        mapping = load_avatar_map()
        mapping[stem] = url
        _write_avatar_map(mapping)
    return url


def generate_and_store(
    agent_id: str,
    prompt: str,
    *,
    settings: ImageGenSettings | None = None,
    opener=None,
) -> str:
    image = generate_still(prompt, settings=settings, opener=opener)
    return store_still_avatar(agent_id, image)


def default_avatar_prompt(name: str, role: str = "") -> str:
    label = (name or "agent").strip() or "agent"
    role_bit = (role or "").strip()
    if role_bit and role_bit != "default":
        return f"Still portrait avatar of {label}, a {role_bit} agent, simple icon, no animation"
    return f"Still portrait avatar of {label}, simple icon, no animation"

"""Mic STT + read-aloud TTS (REQ-77 / #422).

Default is the OS/browser implementation. Settings can opt each of STT and
TTS into a custom OpenAI-compatible endpoint (Whisper-style
``/v1/audio/transcriptions`` and ``/v1/audio/speech``). Persist stores the
api-key **env name** only. Empty custom URL never guesses a host (no OpenAI,
LiteLLM, LAN, or ``:8001`` default).
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from swarm.core.paths import get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

ENV_CONFIG_PATH = "SWARM_CONFIG_PATH"

SOURCE_SYSTEM = "system"
SOURCE_CUSTOM = "custom"
SOURCES = (SOURCE_SYSTEM, SOURCE_CUSTOM)

_FORBIDDEN_BASE_HINTS = ("fly.dev", "open-litellm", "openlitellm")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_DEFAULT_TIMEOUT_S = 3.0
_TRANSCRIBE_TIMEOUT_S = 30.0
_SPEAK_TIMEOUT_S = 30.0
MAX_AUDIO_BYTES = 25 * 1024 * 1024


class SpeechError(Exception):
    """User-facing speech failure (not configured, DOWN, bad payload)."""


@dataclass
class SpeechEndpoint:
    source: str = SOURCE_SYSTEM
    base_url: str = ""
    model: str = ""
    api_key: str = ""
    api_key_env: str = ""

    def custom_configured(self) -> bool:
        return bool(self.base_url.strip())

    def using_custom(self) -> bool:
        return self.source == SOURCE_CUSTOM and self.custom_configured()

    def public_dict(self, kind: str) -> dict[str, Any]:
        key = str(self.api_key or "")
        return {
            "kind": kind,
            "source": self.source if self.source in SOURCES else SOURCE_SYSTEM,
            "configured": self.custom_configured(),
            "base_url": self.base_url,
            "model": self.model,
            "api_key_env": self.api_key_env,
            "api_key_set": bool(key) and not _is_unresolved_placeholder(key),
        }


@dataclass
class SpeechSettings:
    stt: SpeechEndpoint = field(default_factory=SpeechEndpoint)
    tts: SpeechEndpoint = field(default_factory=SpeechEndpoint)

    def public_dict(self) -> dict[str, Any]:
        return {
            "object": "speech",
            "stt": self.stt.public_dict("stt"),
            "tts": self.tts.public_dict("tts"),
        }


@dataclass(frozen=True)
class AgentSpeechBind:
    """Resolved per-agent speech overlay (#116). Unset bind == global."""

    settings: SpeechSettings
    mode: str = "inherit"
    voice: str = ""
    instruction: str = ""
    auto_speak_replies: bool = False

    def public_dict(self) -> dict[str, Any]:
        return {
            "speech_mode": self.mode,
            "tts_voice": self.voice,
            "tts_voice_instruction": self.instruction,
            "auto_speak_replies": self.auto_speak_replies,
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
        raw = f"http://{raw}"
    return raw


def _forbidden_host_reason(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    parsed = urlparse(lowered if "://" in lowered else f"http://{lowered}")
    if parsed.port == 8001 or ":8001" in (parsed.netloc or lowered):
        return ":8001"
    if any(hint in lowered for hint in _FORBIDDEN_BASE_HINTS):
        return "open-litellm"
    return ""


def _looks_like_forbidden_host(url: str) -> bool:
    return bool(_forbidden_host_reason(url))


def _normalize_source(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if raw == SOURCE_CUSTOM:
        return SOURCE_CUSTOM
    return SOURCE_SYSTEM


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
            logger.warning("speech: failed to read %s: %s", path, exc)
    return {}, path


def _apply_block(endpoint: SpeechEndpoint, block: dict[str, Any]) -> None:
    if block.get("source") is not None:
        endpoint.source = _normalize_source(block.get("source"))
    if block.get("base_url") is not None:
        endpoint.base_url = str(block.get("base_url") or "")
    if block.get("model") is not None:
        endpoint.model = str(block.get("model") or "")
    if block.get("api_key") is not None:
        endpoint.api_key = str(block.get("api_key") or "")
    if block.get("api_key_env") is not None:
        endpoint.api_key_env = str(block.get("api_key_env") or "")


def _apply_env(endpoint: SpeechEndpoint, *, prefix: str) -> None:
    env_source = os.environ.get(f"{prefix}_SOURCE", "").strip()
    if env_source:
        endpoint.source = _normalize_source(env_source)
    env_base = os.environ.get(f"{prefix}_BASE_URL", "").strip()
    if env_base:
        endpoint.base_url = env_base
    env_model = os.environ.get(f"{prefix}_MODEL", "").strip()
    if env_model:
        endpoint.model = env_model
    env_key_name = endpoint.api_key_env or os.environ.get(f"{prefix}_API_KEY_ENV", "").strip()
    if env_key_name:
        endpoint.api_key_env = env_key_name
    env_key = os.environ.get(endpoint.api_key_env, "").strip() if endpoint.api_key_env else ""
    if env_key:
        endpoint.api_key = env_key
    elif endpoint.api_key:
        endpoint.api_key = str(_expand(endpoint.api_key) or "")
    if not endpoint.api_key_env:
        endpoint.api_key_env = _placeholder_env_name(str(endpoint.api_key or ""))
    endpoint.base_url = _normalize_base_url(endpoint.base_url)
    endpoint.source = _normalize_source(endpoint.source)
    endpoint.api_key_env = _as_env_name(endpoint.api_key_env)


def _overlay_endpoint(
    endpoint: SpeechEndpoint,
    *,
    base_url: str = "",
    model: str = "",
    api_key_env: str = "",
) -> SpeechEndpoint:
    next_ep = replace(endpoint)
    url = _normalize_base_url(base_url)
    if url and not _looks_like_forbidden_host(url):
        next_ep.base_url = url
        next_ep.source = SOURCE_CUSTOM
    if (model or "").strip():
        next_ep.model = model.strip()
    env_name = _as_env_name(api_key_env)
    if env_name:
        next_ep.api_key_env = env_name
        live = os.environ.get(env_name, "").strip()
        next_ep.api_key = live or str(_expand(f"${{{env_name}}}") or "")
    return next_ep


def bind_for_agent(agent_id: str | None, *, settings: SpeechSettings | None = None) -> AgentSpeechBind:
    """Apply an agent's voice bind on top of global speech. Missing bind is inherit."""
    spec = settings if settings is not None else load_settings()
    fallback = AgentSpeechBind(settings=spec)
    agent = (agent_id or "").strip()
    if not agent:
        return fallback
    try:
        from swarm.core.agent_settings import (
            KEY_AUTO_SPEAK_REPLIES,
            KEY_SPEECH_MODE,
            KEY_STT_API_KEY_ENV,
            KEY_STT_BASE_URL,
            KEY_STT_MODEL,
            KEY_TTS_API_KEY_ENV,
            KEY_TTS_BASE_URL,
            KEY_TTS_MODEL,
            KEY_TTS_VOICE,
            KEY_TTS_VOICE_INSTRUCTION,
            SPEECH_MODE_ENDPOINT,
            SPEECH_MODE_INHERIT,
            SPEECH_MODE_VOICE,
            get_settings,
        )

        row = get_settings(agent)
    except Exception:
        logger.exception("speech bind: failed to load agent settings for %s", agent)
        return fallback
    mode = str(row.get(KEY_SPEECH_MODE) or SPEECH_MODE_INHERIT).strip().lower()
    if mode not in (SPEECH_MODE_INHERIT, SPEECH_MODE_VOICE, SPEECH_MODE_ENDPOINT):
        mode = SPEECH_MODE_INHERIT
    voice = str(row.get(KEY_TTS_VOICE) or "").strip()
    instruction = str(row.get(KEY_TTS_VOICE_INSTRUCTION) or "").strip()
    auto_speak = bool(row.get(KEY_AUTO_SPEAK_REPLIES))
    if mode == SPEECH_MODE_INHERIT:
        return AgentSpeechBind(
            settings=spec,
            mode=mode,
            auto_speak_replies=auto_speak,
        )
    if mode == SPEECH_MODE_VOICE:
        return AgentSpeechBind(
            settings=spec,
            mode=mode,
            voice=voice,
            instruction=instruction,
            auto_speak_replies=auto_speak,
        )
    overlaid = SpeechSettings(
        stt=_overlay_endpoint(
            spec.stt,
            base_url=str(row.get(KEY_STT_BASE_URL) or ""),
            model=str(row.get(KEY_STT_MODEL) or ""),
            api_key_env=str(row.get(KEY_STT_API_KEY_ENV) or ""),
        ),
        tts=_overlay_endpoint(
            spec.tts,
            base_url=str(row.get(KEY_TTS_BASE_URL) or ""),
            model=str(row.get(KEY_TTS_MODEL) or ""),
            api_key_env=str(row.get(KEY_TTS_API_KEY_ENV) or ""),
        ),
    )
    return AgentSpeechBind(
        settings=overlaid,
        mode=mode,
        voice=voice,
        instruction=instruction,
        auto_speak_replies=auto_speak,
    )


def load_settings(config: dict[str, Any] | None = None) -> SpeechSettings:
    """Defaults ← swarm_config.json speech ← env (env wins for URL/model/key)."""
    cfg = config if isinstance(config, dict) else load_raw_config()[0]
    block = cfg.get("speech") if isinstance(cfg.get("speech"), dict) else {}
    settings = SpeechSettings()
    if isinstance(block, dict):
        stt_block = block.get("stt") if isinstance(block.get("stt"), dict) else {}
        tts_block = block.get("tts") if isinstance(block.get("tts"), dict) else {}
        _apply_block(settings.stt, stt_block)
        _apply_block(settings.tts, tts_block)
        if not settings.stt.api_key_env:
            settings.stt.api_key_env = _placeholder_env_name(str(stt_block.get("api_key") or ""))
        if not settings.tts.api_key_env:
            settings.tts.api_key_env = _placeholder_env_name(str(tts_block.get("api_key") or ""))
    _apply_env(settings.stt, prefix="SPEECH_STT")
    _apply_env(settings.tts, prefix="SPEECH_TTS")
    return settings


def _merge_endpoint(
    entry: dict[str, Any],
    *,
    source: str | None,
    base_url: str | None,
    model: str | None,
    api_key_env: str | None,
    label: str,
) -> dict[str, Any]:
    next_entry = dict(entry)
    if source is not None:
        next_entry["source"] = _normalize_source(source)
    if base_url is not None:
        normalized = _normalize_base_url(base_url)
        if normalized and _looks_like_forbidden_host(normalized):
            reason = _forbidden_host_reason(normalized)
            raise SpeechError(
                f"Refusing to persist a {reason} host as the {label} endpoint. "
                "Set the OpenAI-compatible audio endpoint you actually run."
            )
        next_entry["base_url"] = normalized
    if model is not None:
        next_entry["model"] = (model or "").strip()
    if api_key_env is not None:
        env_name = _as_env_name(api_key_env)
        next_entry["api_key_env"] = env_name
        if env_name:
            next_entry["api_key"] = f"${{{env_name}}}"
        else:
            next_entry.pop("api_key", None)
    if "source" not in next_entry:
        next_entry["source"] = SOURCE_SYSTEM
    if "base_url" not in next_entry:
        next_entry["base_url"] = ""
    return next_entry


def persist_settings(
    *,
    stt: dict[str, Any] | None = None,
    tts: dict[str, Any] | None = None,
    config_path: str | Path | None = None,
) -> tuple[SpeechSettings, Path]:
    """Merge STT/TTS fields into ``speech`` and write swarm_config.json.

    Stores api-key-env as ``${ENV}`` only. Empty base URL stays empty — never
    invents a host. ``source`` defaults to system even when a custom URL is stored.
    """
    cfg, path = load_raw_config(config_path)
    block = cfg.get("speech") if isinstance(cfg.get("speech"), dict) else {}
    block = dict(block)
    stt_entry = block.get("stt") if isinstance(block.get("stt"), dict) else {}
    tts_entry = block.get("tts") if isinstance(block.get("tts"), dict) else {}
    if stt is not None:
        if not isinstance(stt, dict):
            raise SpeechError("stt must be an object.")
        if "api_key" in stt:
            raise SpeechError("Send api_key_env (environment variable name) only. Never a live token.")
        stt_entry = _merge_endpoint(
            stt_entry,
            source=stt.get("source") if "source" in stt else None,
            base_url=stt.get("base_url") if "base_url" in stt else None,
            model=stt.get("model") if "model" in stt else None,
            api_key_env=stt.get("api_key_env") if "api_key_env" in stt else None,
            label="STT",
        )
    if tts is not None:
        if not isinstance(tts, dict):
            raise SpeechError("tts must be an object.")
        if "api_key" in tts:
            raise SpeechError("Send api_key_env (environment variable name) only. Never a live token.")
        tts_entry = _merge_endpoint(
            tts_entry,
            source=tts.get("source") if "source" in tts else None,
            base_url=tts.get("base_url") if "base_url" in tts else None,
            model=tts.get("model") if "model" in tts else None,
            api_key_env=tts.get("api_key_env") if "api_key_env" in tts else None,
            label="TTS",
        )
    block["stt"] = stt_entry or {"source": SOURCE_SYSTEM, "base_url": ""}
    block["tts"] = tts_entry or {"source": SOURCE_SYSTEM, "base_url": ""}
    cfg["speech"] = block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cfg, indent=4) + "\n", encoding="utf-8")
    logger.info("Persisted speech settings to %s", path)
    return load_settings(cfg), path


def _join_audio_url(base_url: str, *suffix: str) -> str:
    raw = _normalize_base_url(base_url)
    if not raw:
        return ""
    parsed = urlparse(raw)
    path = (parsed.path or "").rstrip("/")
    wanted = "/".join(suffix)
    if path.endswith(f"/v1/{wanted}") or path.endswith(f"/{wanted}"):
        return raw
    if path.endswith("/v1"):
        return f"{raw}/{wanted}"
    return f"{raw}/v1/{wanted}"


def transcriptions_url(base_url: str) -> str:
    """``{base}/v1/audio/transcriptions`` without inventing a host when base is empty."""
    return _join_audio_url(base_url, "audio", "transcriptions")


def speech_url(base_url: str) -> str:
    """``{base}/v1/audio/speech`` without inventing a host when base is empty."""
    return _join_audio_url(base_url, "audio", "speech")


def _probe_one(endpoint: SpeechEndpoint, *, kind: str, url_fn, opener=None) -> dict[str, Any]:
    pub = endpoint.public_dict(kind)
    if endpoint.source != SOURCE_CUSTOM:
        pub["status"] = "system"
        pub["detail"] = (
            "Using the browser/OS implementation. Custom endpoint is stored but not used "
            "until you switch the source to custom."
            if endpoint.custom_configured()
            else "Using the browser/OS implementation. No custom host is called."
        )
        return pub
    if not endpoint.custom_configured():
        pub["status"] = "off"
        pub["detail"] = (
            f"Custom {kind.upper()} is off. No host is used until you set a base URL."
        )
        return pub
    url = url_fn(endpoint.base_url)
    call = opener or _default_urlopen
    try:
        req = _request(url, method="GET")
        with call(req, timeout=_DEFAULT_TIMEOUT_S) as resp:
            code = int(getattr(resp, "status", 200) or 200)
        pub["status"] = "ok"
        pub["detail"] = f"Custom {kind.upper()} endpoint answered HTTP {code}."
        pub["http_status"] = code
        return pub
    except Exception as exc:
        http_error = _http_error_code(exc)
        if http_error is not None:
            pub["status"] = "ok"
            pub["detail"] = f"Custom {kind.upper()} endpoint answered HTTP {http_error}."
            pub["http_status"] = http_error
            return pub
        pub["status"] = "down"
        pub["detail"] = f"Custom {kind.upper()} endpoint is DOWN: {exc}"
        pub["http_status"] = None
        return pub


def probe_status(settings: SpeechSettings | None = None, *, opener=None) -> dict[str, Any]:
    """Honest reachability. System / empty custom URL never call a host."""
    spec = settings if settings is not None else load_settings()
    return {
        "object": "speech",
        "stt": _probe_one(spec.stt, kind="stt", url_fn=transcriptions_url, opener=opener),
        "tts": _probe_one(spec.tts, kind="tts", url_fn=speech_url, opener=opener),
    }


def _default_urlopen(req, timeout: float = _DEFAULT_TIMEOUT_S):
    import urllib.request

    return urllib.request.urlopen(req, timeout=timeout)


def _request(url: str, *, method: str = "GET", data: bytes | None = None, headers: dict[str, str] | None = None):
    import urllib.request

    return urllib.request.Request(url, data=data, headers=headers or {}, method=method)


def _http_error_code(exc: Exception) -> int | None:
    import urllib.error

    if isinstance(exc, urllib.error.HTTPError):
        return int(exc.code)
    return None


def _auth_headers(endpoint: SpeechEndpoint) -> dict[str, str]:
    headers: dict[str, str] = {}
    if endpoint.api_key and not _is_unresolved_placeholder(endpoint.api_key):
        headers["Authorization"] = f"Bearer {endpoint.api_key}"
    return headers


def _encode_multipart(
    fields: dict[str, str],
    *,
    file_field: str,
    filename: str,
    content_type: str,
    payload: bytes,
) -> tuple[bytes, str]:
    boundary = f"----OpenSwarmSpeech{os.urandom(8).hex()}"
    crlf = b"\r\n"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.append(f"--{boundary}\r\n".encode("ascii"))
        chunks.append(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("ascii"))
        chunks.append(str(value).encode("utf-8"))
        chunks.append(crlf)
    chunks.append(f"--{boundary}\r\n".encode("ascii"))
    safe_name = (filename or "audio.webm").replace('"', "")
    chunks.append(
        f'Content-Disposition: form-data; name="{file_field}"; filename="{safe_name}"\r\n'.encode("ascii")
    )
    chunks.append(f"Content-Type: {content_type or 'application/octet-stream'}\r\n\r\n".encode("ascii"))
    chunks.append(payload)
    chunks.append(crlf)
    chunks.append(f"--{boundary}--\r\n".encode("ascii"))
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def transcribe_audio(
    payload: bytes,
    *,
    filename: str = "audio.webm",
    content_type: str = "audio/webm",
    settings: SpeechSettings | None = None,
    opener=None,
    timeout: float = _TRANSCRIBE_TIMEOUT_S,
) -> str:
    """POST ``/v1/audio/transcriptions``. Empty URL does not call any host."""
    spec = settings if settings is not None else load_settings()
    url = transcriptions_url(spec.stt.base_url)
    if not url:
        raise SpeechError(
            "Custom STT is not configured. Set a base URL in Settings → Speech, "
            "or use the browser/OS microphone."
        )
    if not payload:
        raise SpeechError("Audio is empty.")
    if len(payload) > MAX_AUDIO_BYTES:
        raise SpeechError(f"Audio is too large (max {MAX_AUDIO_BYTES} bytes).")
    fields: dict[str, str] = {}
    if spec.stt.model.strip():
        fields["model"] = spec.stt.model.strip()
    body, ctype = _encode_multipart(
        fields,
        file_field="file",
        filename=filename or "audio.webm",
        content_type=content_type or "audio/webm",
        payload=payload,
    )
    headers = {"Content-Type": ctype, "Accept": "application/json", **_auth_headers(spec.stt)}
    req = _request(url, method="POST", data=body, headers=headers)
    call = opener or _default_urlopen
    try:
        with call(req, timeout=timeout) as resp:
            raw = resp.read()
    except Exception as exc:
        http_error = _http_error_code(exc)
        detail = ""
        if http_error is not None:
            fp = getattr(exc, "fp", None)
            if fp is not None:
                try:
                    detail = fp.read().decode("utf-8", errors="replace")[:240]
                except Exception:
                    detail = ""
            raise SpeechError(
                f"Custom STT endpoint returned HTTP {http_error}. {detail}".strip()
            ) from exc
        raise SpeechError(f"Custom STT endpoint is DOWN: {exc}") from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            return text
        raise SpeechError("Custom STT response was not JSON or text.") from exc
    if isinstance(parsed, dict):
        text = parsed.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    raise SpeechError("Custom STT response had no text.")


def synthesize_speech(
    text: str,
    *,
    voice: str = "",
    instruction: str = "",
    settings: SpeechSettings | None = None,
    opener=None,
    timeout: float = _SPEAK_TIMEOUT_S,
) -> tuple[bytes, str]:
    """POST ``/v1/audio/speech``. Empty URL does not call any host."""
    spec = settings if settings is not None else load_settings()
    url = speech_url(spec.tts.base_url)
    if not url:
        raise SpeechError(
            "Custom TTS is not configured. Set a base URL in Settings → Speech, "
            "or use the browser/OS read-aloud."
        )
    spoken = (text or "").strip()
    if not spoken:
        raise SpeechError("Provide text to read aloud.")
    payload: dict[str, Any] = {"input": spoken}
    if spec.tts.model.strip():
        payload["model"] = spec.tts.model.strip()
    if (voice or "").strip():
        payload["voice"] = voice.strip()
    if (instruction or "").strip():
        payload["instruction"] = instruction.strip()
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "audio/mpeg, audio/*, application/json",
        **_auth_headers(spec.tts),
    }
    req = _request(url, method="POST", data=body, headers=headers)
    call = opener or _default_urlopen
    try:
        with call(req, timeout=timeout) as resp:
            raw = resp.read()
            ctype = ""
            try:
                ctype = resp.headers.get("Content-Type", "") or ""
            except Exception:
                ctype = ""
    except Exception as exc:
        http_error = _http_error_code(exc)
        if http_error is not None:
            detail = ""
            fp = getattr(exc, "fp", None)
            if fp is not None:
                try:
                    detail = fp.read().decode("utf-8", errors="replace")[:240]
                except Exception:
                    detail = ""
            raise SpeechError(
                f"Custom TTS endpoint returned HTTP {http_error}. {detail}".strip()
            ) from exc
        raise SpeechError(f"Custom TTS endpoint is DOWN: {exc}") from exc
    if not raw:
        raise SpeechError("Custom TTS response had no audio.")
    return raw, (ctype.split(";")[0].strip() or "audio/mpeg")

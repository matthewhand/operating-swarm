"""Per-agent settings store (REQ-65).

File-backed JSON so the SPA editor, CoS handoffs, API session create, and
CLI/remote resume gates share one source of truth. Default is reuse (off).

Layout::

    <user-config>/agent_settings.json

    {
      "schema": 1,
      "agents": {
        "<agent_id>": {
          "new_chat_per_task": false,
          "use_suggestions": false,
          "cli_session_id": null,
          "remote_session_id": null,
          "folder": null,
          "speech_mode": "inherit",
          "tts_voice": "",
          "tts_voice_instruction": "",
          "stt_base_url": "",
          "stt_model": "",
          "stt_api_key_env": "",
          "tts_base_url": "",
          "tts_model": "",
          "tts_api_key_env": "",
          "auto_speak_replies": false
        }
      }
    }

This is **not** global Settings (Remotes / Retention / Hostname). Agent-scoped
only — see the SPA ``AgentEditorSheet``. Speech bind (#116) stores env-var
names only, never live tokens.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_SETTINGS_PATH = "SWARM_AGENT_SETTINGS_PATH"
KEY_NEW_CHAT_PER_TASK = "new_chat_per_task"
KEY_USE_SUGGESTIONS = "use_suggestions"
KEY_CLI_SESSION = "cli_session_id"
KEY_REMOTE_SESSION = "remote_session_id"
KEY_FOLDER = "folder"
KEY_SPEECH_MODE = "speech_mode"
KEY_TTS_VOICE = "tts_voice"
KEY_TTS_VOICE_INSTRUCTION = "tts_voice_instruction"
KEY_STT_BASE_URL = "stt_base_url"
KEY_STT_MODEL = "stt_model"
KEY_STT_API_KEY_ENV = "stt_api_key_env"
KEY_TTS_BASE_URL = "tts_base_url"
KEY_TTS_MODEL = "tts_model"
KEY_TTS_API_KEY_ENV = "tts_api_key_env"
KEY_AUTO_SPEAK_REPLIES = "auto_speak_replies"
KEY_STT_API_KEY = "stt_api_key"
KEY_TTS_API_KEY = "tts_api_key"

SPEECH_MODE_INHERIT = "inherit"
SPEECH_MODE_VOICE = "voice"
SPEECH_MODE_ENDPOINT = "endpoint"
SPEECH_MODES = (SPEECH_MODE_INHERIT, SPEECH_MODE_VOICE, SPEECH_MODE_ENDPOINT)

_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SECRET_PATCH_KEYS = frozenset({"api_key", KEY_STT_API_KEY, KEY_TTS_API_KEY})

DEFAULTS: dict[str, Any] = {
    KEY_NEW_CHAT_PER_TASK: False,
    KEY_USE_SUGGESTIONS: False,
    KEY_CLI_SESSION: None,
    KEY_REMOTE_SESSION: None,
    KEY_FOLDER: None,
    KEY_SPEECH_MODE: SPEECH_MODE_INHERIT,
    KEY_TTS_VOICE: "",
    KEY_TTS_VOICE_INSTRUCTION: "",
    KEY_STT_BASE_URL: "",
    KEY_STT_MODEL: "",
    KEY_STT_API_KEY_ENV: "",
    KEY_TTS_BASE_URL: "",
    KEY_TTS_MODEL: "",
    KEY_TTS_API_KEY_ENV: "",
    KEY_AUTO_SPEAK_REPLIES: False,
}

_ALLOWED_KEYS = frozenset(DEFAULTS)
_BOOL_KEYS = frozenset({KEY_NEW_CHAT_PER_TASK, KEY_USE_SUGGESTIONS, KEY_AUTO_SPEAK_REPLIES})
_ID_KEYS = frozenset({KEY_CLI_SESSION, KEY_REMOTE_SESSION})
_PATH_KEYS = frozenset({KEY_FOLDER})
_URL_KEYS = frozenset({KEY_STT_BASE_URL, KEY_TTS_BASE_URL})
_ENV_KEYS = frozenset({KEY_STT_API_KEY_ENV, KEY_TTS_API_KEY_ENV})
_TEXT_KEYS = frozenset({KEY_TTS_VOICE, KEY_TTS_VOICE_INSTRUCTION, KEY_STT_MODEL, KEY_TTS_MODEL})

_cache: dict[str, Any] | None = None


def settings_path() -> Path:
    """Path of the agent-settings JSON file."""
    env = (os.environ.get(ENV_SETTINGS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_settings.json"


def reset_agent_settings_cache() -> None:
    """Drop the in-process cache (tests)."""
    global _cache
    _cache = None


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = settings_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read agent settings at %s", path, exc_info=True)
        _cache = _empty_store()
        return _cache
    if not isinstance(data, dict):
        _cache = _empty_store()
        return _cache
    agents = data.get("agents")
    if not isinstance(agents, dict):
        agents = {}
    _cache = {"schema": SCHEMA, "agents": dict(agents)}
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "agents": store.get("agents") or {}}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, default=str)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _cache = payload


def _as_env_name(value: str) -> str:
    raw = (value or "").strip()
    if raw.startswith("${") and raw.endswith("}") and len(raw) > 3:
        inner = raw[2:-1].strip()
        if inner and _ENV_NAME_RE.match(inner):
            return inner
        return ""
    if raw and _ENV_NAME_RE.match(raw):
        return raw
    return ""


def _normalize_bind_url(key: str, value: Any) -> str:
    text = "" if value is None else str(value).strip().rstrip("/")
    if not text:
        return ""
    if "://" not in text:
        text = f"http://{text}"
    from swarm.core.speech import SpeechError, _forbidden_host_reason, _looks_like_forbidden_host

    if _looks_like_forbidden_host(text):
        reason = _forbidden_host_reason(text)
        raise ValueError(
            f"Refusing to persist a {reason} host as the {key} endpoint. "
            "Set the OpenAI-compatible audio endpoint you actually run."
        )
    try:
        from swarm.core.speech import _normalize_base_url

        return _normalize_base_url(text)
    except SpeechError as exc:
        raise ValueError(str(exc)) from exc


def _placeholder_for_env(env_name: str) -> str:
    name = (env_name or "").strip()
    return f"${{{name}}}" if name else ""


def _normalize_value(key: str, value: Any) -> Any:
    if key in _BOOL_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in (0, 1):
            return bool(value)
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes", "on"):
                return True
            if lowered in ("false", "0", "no", "off", ""):
                return False
        raise ValueError(f"{key} must be a boolean.")
    if key in _ID_KEYS or key in _PATH_KEYS:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
    if key == KEY_SPEECH_MODE:
        text = ("" if value is None else str(value)).strip().lower() or SPEECH_MODE_INHERIT
        if text not in SPEECH_MODES:
            raise ValueError(
                f"{KEY_SPEECH_MODE} must be one of {', '.join(SPEECH_MODES)}."
            )
        return text
    if key in _URL_KEYS:
        return _normalize_bind_url(key, value)
    if key in _ENV_KEYS:
        if value is None:
            return ""
        text = str(value).strip()
        if not text:
            return ""
        env_name = _as_env_name(text)
        if not env_name:
            raise ValueError(
                f"{key} must be an environment variable name (for example STT_API_KEY), never a live token."
            )
        return env_name
    if key in _TEXT_KEYS:
        if value is None:
            return ""
        return str(value).strip()
    return value


def public_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stable JSON shape for the editor / API."""
    merged = dict(DEFAULTS)
    if isinstance(raw, dict):
        for key in _ALLOWED_KEYS:
            if key in raw:
                try:
                    merged[key] = _normalize_value(key, raw[key])
                except ValueError:
                    continue
    return {
        KEY_NEW_CHAT_PER_TASK: bool(merged[KEY_NEW_CHAT_PER_TASK]),
        KEY_USE_SUGGESTIONS: bool(merged[KEY_USE_SUGGESTIONS]),
        KEY_CLI_SESSION: merged[KEY_CLI_SESSION],
        KEY_REMOTE_SESSION: merged[KEY_REMOTE_SESSION],
        KEY_FOLDER: merged[KEY_FOLDER],
        KEY_SPEECH_MODE: merged[KEY_SPEECH_MODE] or SPEECH_MODE_INHERIT,
        KEY_TTS_VOICE: str(merged[KEY_TTS_VOICE] or ""),
        KEY_TTS_VOICE_INSTRUCTION: str(merged[KEY_TTS_VOICE_INSTRUCTION] or ""),
        KEY_STT_BASE_URL: str(merged[KEY_STT_BASE_URL] or ""),
        KEY_STT_MODEL: str(merged[KEY_STT_MODEL] or ""),
        KEY_STT_API_KEY_ENV: str(merged[KEY_STT_API_KEY_ENV] or ""),
        KEY_TTS_BASE_URL: str(merged[KEY_TTS_BASE_URL] or ""),
        KEY_TTS_MODEL: str(merged[KEY_TTS_MODEL] or ""),
        KEY_TTS_API_KEY_ENV: str(merged[KEY_TTS_API_KEY_ENV] or ""),
        KEY_AUTO_SPEAK_REPLIES: bool(merged[KEY_AUTO_SPEAK_REPLIES]),
    }


def get_settings(agent_id: str) -> dict[str, Any]:
    """Return settings for one agent. Missing agents get defaults (toggle off)."""
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    raw = store["agents"].get(agent)
    return public_settings(raw if isinstance(raw, dict) else None)


def _record_for_disk(public: dict[str, Any]) -> dict[str, Any]:
    """Persist env placeholders next to env names. Never a live token."""
    record = dict(public)
    for env_key, secret_key in (
        (KEY_STT_API_KEY_ENV, KEY_STT_API_KEY),
        (KEY_TTS_API_KEY_ENV, KEY_TTS_API_KEY),
    ):
        placeholder = _placeholder_for_env(str(record.get(env_key) or ""))
        if placeholder:
            record[secret_key] = placeholder
        else:
            record.pop(secret_key, None)
    return record


def update_settings(agent_id: str, patch: dict[str, Any] | None) -> dict[str, Any]:
    """Merge ``patch`` into one agent's settings and persist."""
    agent = normalize_agent_id(agent_id)
    incoming = patch if isinstance(patch, dict) else {}
    secret_keys = [key for key in incoming if key in _SECRET_PATCH_KEYS]
    if secret_keys:
        raise ValueError(
            "Send stt_api_key_env / tts_api_key_env (environment variable name) only. Never a live token."
        )
    unknown = [key for key in incoming if key not in _ALLOWED_KEYS]
    if unknown:
        raise ValueError(f"Unknown agent setting(s): {', '.join(sorted(unknown))}.")
    current = get_settings(agent)
    for key, value in incoming.items():
        current[key] = _normalize_value(key, value)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    agents[agent] = _record_for_disk(current)
    _write_store({"schema": SCHEMA, "agents": agents})
    return dict(current)


def is_new_chat_per_task(agent_id: str | None) -> bool:
    """True when this agent starts a fresh session per task (default False)."""
    if not (agent_id or "").strip():
        return False
    return bool(get_settings(agent_id)[KEY_NEW_CHAT_PER_TASK])


def is_use_suggestions(agent_id: str | None) -> bool:
    """True when this consumer wires the suggestions role (default False)."""
    if not (agent_id or "").strip():
        return False
    return bool(get_settings(agent_id)[KEY_USE_SUGGESTIONS])


def stored_cli_session_id(agent_id: str) -> str | None:
    value = get_settings(agent_id).get(KEY_CLI_SESSION)
    return str(value) if value else None


def stored_remote_session_id(agent_id: str) -> str | None:
    value = get_settings(agent_id).get(KEY_REMOTE_SESSION)
    return str(value) if value else None


def set_cli_session_id(agent_id: str, session_id: str | None) -> dict[str, Any]:
    return update_settings(agent_id, {KEY_CLI_SESSION: session_id})


def set_remote_session_id(agent_id: str, session_id: str | None) -> dict[str, Any]:
    return update_settings(agent_id, {KEY_REMOTE_SESSION: session_id})


def stored_folder(agent_id: str) -> str | None:
    value = get_settings(agent_id).get(KEY_FOLDER)
    return str(value) if value else None


def set_folder(agent_id: str, folder: str | None) -> dict[str, Any]:
    return update_settings(agent_id, {KEY_FOLDER: folder})


def is_auto_speak_replies(agent_id: str | None) -> bool:
    """True when this agent's chat should read assistant replies aloud."""
    if not (agent_id or "").strip():
        return False
    return bool(get_settings(agent_id)[KEY_AUTO_SPEAK_REPLIES])

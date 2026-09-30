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
          "auto_speak_replies": false,
          "command_allowlist": {"allow": [], "deny": [], "ask": []},
          "mcp_tool_grants": [],
          "mcp_tool_grants_set": false,
          "profile": {
            "display_name": "",
            "description": "",
            "title": "",
            "role": "",
            "avatar_shape": "circle",
            "avatar_color": "",
            "avatar_path": null
          }
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

from swarm.core.agent_profile import (
    KEY_ROLE,
    apply_profile_patch,
    default_profile,
    normalize_profile,
    profile_for_replace,
    public_profile,
)
from swarm.core.chat_store import normalize_agent_id
from swarm.core.command_allowlist import KEY as KEY_COMMAND_ALLOWLIST
from swarm.core.command_allowlist import empty_policy as _empty_command_policy
from swarm.core.command_allowlist import normalize_policy as _normalize_command_policy
from swarm.core.mcp_tool_grants import KEY as KEY_MCP_TOOL_GRANTS
from swarm.core.mcp_tool_grants import KEY_SET as KEY_MCP_TOOL_GRANTS_SET
from swarm.core.mcp_tool_grants import empty_grants as _empty_mcp_tool_grants
from swarm.core.mcp_tool_grants import normalize_mcp_tool_grants as _normalize_mcp_tool_grants
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

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
KEY_PROFILE = "profile"
KEY_STT_API_KEY = "stt_api_key"
KEY_TTS_API_KEY = "tts_api_key"
# #1312: per-bot exact command allowlist (allow / deny / ask). Empty = inactive.
# #1313: per-bot MCP / connector tool grants. Unset = inactive; saved [] = deny-all.

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
    KEY_COMMAND_ALLOWLIST: _empty_command_policy(),
    KEY_MCP_TOOL_GRANTS: _empty_mcp_tool_grants(),
    KEY_MCP_TOOL_GRANTS_SET: False,
    KEY_PROFILE: default_profile(),
}

_ALLOWED_KEYS = frozenset(DEFAULTS)
_BOOL_KEYS = frozenset({
    KEY_NEW_CHAT_PER_TASK,
    KEY_USE_SUGGESTIONS,
    KEY_AUTO_SPEAK_REPLIES,
    KEY_MCP_TOOL_GRANTS_SET,
})
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
    from swarm.core.speech import (
        SpeechError,
        _forbidden_host_reason,
        _looks_like_forbidden_host,
    )

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
    if key == KEY_COMMAND_ALLOWLIST:
        try:
            return _normalize_command_policy(value)
        except ValueError as exc:
            raise ValueError(f"{KEY_COMMAND_ALLOWLIST}: {exc}") from exc
    if key == KEY_MCP_TOOL_GRANTS:
        try:
            return _normalize_mcp_tool_grants(value)
        except ValueError as exc:
            raise ValueError(f"{KEY_MCP_TOOL_GRANTS}: {exc}") from exc
    if key == KEY_PROFILE:
        return normalize_profile(value)
    return value


def public_settings(raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """Stable JSON shape for the editor / API."""
    merged = dict(DEFAULTS)
    profile_raw = None
    if isinstance(raw, dict):
        profile_raw = raw.get(KEY_PROFILE)
        for key in _ALLOWED_KEYS:
            if key == KEY_PROFILE or key not in raw:
                continue
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
        KEY_COMMAND_ALLOWLIST: _normalize_command_policy(merged[KEY_COMMAND_ALLOWLIST]),
        KEY_MCP_TOOL_GRANTS: _normalize_mcp_tool_grants(merged[KEY_MCP_TOOL_GRANTS]),
        KEY_MCP_TOOL_GRANTS_SET: bool(merged[KEY_MCP_TOOL_GRANTS_SET]),
        KEY_PROFILE: public_profile(profile_raw),
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


def _reject_incapable_role(agent_id: str, incoming: dict[str, Any]) -> None:
    """#1706 D.16 — refuse a role write a seat cannot carry.

    Every agent-settings write (PATCH and PUT) funnels through
    :func:`update_settings`, so this is the one place the settings API can
    reject a role. It asks :func:`validate_role_for_kind` — the single
    decision point — rather than re-deriving which seats are role-capable, so
    this rejection and the editor's field suppression cannot disagree.

    A patch that does not mention a role is untouched: the gate fires on the
    *write*, not on the seat's current state, so an ordinary settings save for
    a team id (voice, folder, …) is not collateral damage.
    """
    from swarm.core.roles.registry import role_seat_kind_for, validate_role_for_kind

    profile = incoming.get(KEY_PROFILE)
    if not isinstance(profile, dict) or KEY_ROLE not in profile:
        return
    raw_role = profile.get(KEY_ROLE)
    if raw_role is None or not str(raw_role).strip():
        return
    error = validate_role_for_kind(str(raw_role), role_seat_kind_for(agent_id))
    if error:
        raise ValueError(error)


def update_settings(agent_id: str, patch: dict[str, Any] | None) -> dict[str, Any]:
    """Merge ``patch`` into one agent's settings and persist."""
    agent = normalize_agent_id(agent_id)
    incoming = dict(patch) if isinstance(patch, dict) else {}
    # Derived from a saved grant list. A client must not clear deny-all, or
    # arm it, by writing this flag on its own.
    incoming.pop(KEY_MCP_TOOL_GRANTS_SET, None)
    secret_keys = [key for key in incoming if key in _SECRET_PATCH_KEYS]
    if secret_keys:
        raise ValueError(
            "Send stt_api_key_env / tts_api_key_env (environment variable name) only. Never a live token."
        )
    unknown = [key for key in incoming if key not in _ALLOWED_KEYS]
    if unknown:
        raise ValueError(f"Unknown agent setting(s): {', '.join(sorted(unknown))}.")
    # #1706 D.16 — before any write, so a rejected role leaves the store as it
    # was. `agent_id` is the RAW id: `normalize_agent_id` slugs a `chat:` /
    # `team:` row id into something that no longer classifies.
    _reject_incapable_role(agent_id, incoming)
    current = get_settings(agent)
    for key, value in incoming.items():
        if key == KEY_PROFILE:
            current[key] = apply_profile_patch(current.get(KEY_PROFILE), value)
        else:
            current[key] = _normalize_value(key, value)
    # Saving the list, including [], marks the policy as configured so an
    # explicit "all off" stays deny-all instead of looking unset.
    if KEY_MCP_TOOL_GRANTS in incoming:
        current[KEY_MCP_TOOL_GRANTS_SET] = True
    store = _read_store()
    agents = dict(store.get("agents") or {})
    agents[agent] = _record_for_disk(current)
    _write_store({"schema": SCHEMA, "agents": agents})
    from swarm.core.activity_log import emit_activity

    emit_activity(
        action="settings.patched",
        entity_type="agent",
        entity_id=agent,
        agent_id=agent,
        detail={"keys": sorted(incoming.keys())},
    )
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


def get_profile(agent_id: str) -> dict[str, Any]:
    """Public storefront / rail profile for one agent."""
    return dict(get_settings(agent_id)[KEY_PROFILE])


def update_profile(agent_id: str, patch: dict[str, Any] | None) -> dict[str, Any]:
    """Merge ``patch`` into one agent's profile and persist."""
    return update_settings(agent_id, {KEY_PROFILE: patch})[KEY_PROFILE]


def replace_profile(agent_id: str, profile: dict[str, Any] | None) -> dict[str, Any]:
    """Replace one agent's profile (PUT). Missing fields become defaults."""
    current = get_profile(agent_id)
    return update_settings(agent_id, {KEY_PROFILE: profile_for_replace(current, profile)})[KEY_PROFILE]


def get_command_allowlist(agent_id: str) -> dict[str, list[str]]:
    """Return this agent's exact-command allowlist (empty dicts = inactive)."""
    return _normalize_command_policy(get_settings(agent_id)[KEY_COMMAND_ALLOWLIST])


def set_command_allowlist(
    agent_id: str, policy: dict[str, Any] | None
) -> dict[str, Any]:
    """Persist this agent's exact-command allowlist policy."""
    return update_settings(agent_id, {KEY_COMMAND_ALLOWLIST: policy})


def get_mcp_tool_grants(agent_id: str) -> list[str]:
    """Return this agent's persisted MCP tool grant names.

    Empty is deny-all only when ``mcp_tool_grants_set`` is true. Flag false
    means the operator has never saved a list.
    """
    return _normalize_mcp_tool_grants(get_settings(agent_id)[KEY_MCP_TOOL_GRANTS])


def set_mcp_tool_grants(agent_id: str, grants: Any) -> dict[str, Any]:
    """Persist this agent's MCP / connector tool grant list."""
    return update_settings(agent_id, {KEY_MCP_TOOL_GRANTS: grants})

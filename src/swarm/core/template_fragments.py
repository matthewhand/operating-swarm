"""JSON Schema checks, Grok mapper notes, and legacy fragment fallback (#1398).

Routine and plugin sections are owned by ``routine_pack`` and
``agent_plugin_pack``. This module still documents the file-only Grok
mapper and can read fragments written before those stores were wired.
It does not call Grok or xAI.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from swarm.core.agent_settings import get_profile
from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

SCHEMA_PATH = Path(__file__).with_name("agent_template.schema.json")
ENV_FRAGMENTS_PATH = "SWARM_AGENT_TEMPLATE_FRAGMENTS_PATH"
STORE_NAME = "agent_template_fragments.json"
SCHEMA = 1

GROK_KEY_NAMES = ("XAI_API_KEY", "GROK_API_KEY")

_FILL_IN_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_TRIGGER_KEYS = frozenset(
    {"kind", "owner_repo", "cron", "schedule", "event", "timezone"}
)
_PLUGIN_REFUSED = frozenset(
    {
        "url",
        "command",
        "args",
        "headers",
        "env",
        "token",
        "tokens",
        "api_key",
        "secret",
        "password",
        "authorization",
        "credentials",
        "openapi_spec_url",
        "openapispecurl",
        "cwd",
        "bearer",
    }
)
_FILL_IN_LABELS = {
    "owner_repo": "GitHub owner/repo",
    "repo": "GitHub owner/repo",
    "repository": "GitHub owner/repo",
    "schedule": "Schedule",
    "cron": "Cron expression",
}

_cache: dict[str, Any] | None = None
_cache_path: str | None = None
_schema_cache: dict[str, Any] | None = None


class FragmentError(ValueError):
    """Invalid routine or plugin fragment."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


def load_json_schema() -> dict[str, Any]:
    """Return the versioned agent-template JSON Schema."""
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema_cache


def assert_json_schema(pack: dict[str, Any]) -> None:
    """Validate *pack* against the shipped JSON Schema."""
    try:
        import jsonschema
    except ImportError:
        _assert_required_shape(pack)
        return
    validator = jsonschema.Draft202012Validator(load_json_schema())
    errors = sorted(
        validator.iter_errors(pack), key=lambda item: list(item.absolute_path)
    )
    if not errors:
        return
    first = errors[0]
    loc = ".".join(str(part) for part in first.absolute_path) or "template"
    raise FragmentError(f"{loc}: {first.message}", code="template_schema_invalid")


def _assert_required_shape(pack: dict[str, Any]) -> None:
    required = (
        "object",
        "schema",
        "kind",
        "profile",
        "memories",
        "skills",
        "gettingStarted",
        "routines",
        "plugins",
        "fill_ins",
    )
    missing = [key for key in required if key not in pack]
    if missing:
        raise FragmentError(
            f"template is missing {', '.join(missing)}",
            code="template_schema_invalid",
        )
    if not isinstance(pack["routines"], list) or not isinstance(pack["plugins"], list):
        raise FragmentError(
            "routines and plugins must be lists", code="template_schema_invalid"
        )


def grok_live_key_configured() -> bool:
    """True when a Grok/xAI key name is set to a non-empty value.

    Does not return or log the value.
    """
    return any((os.environ.get(name) or "").strip() for name in GROK_KEY_NAMES)


def grok_mapper_document() -> dict[str, Any]:
    """File-only Grok mapper. Never includes secret values or share links."""
    schema = load_json_schema()
    mapper = (
        schema.get("x-grok-mapper")
        if isinstance(schema.get("x-grok-mapper"), dict)
        else {}
    )
    field_map = dict(mapper.get("fields") or {})
    reason = "Live Grok call skipped because no XAI_API_KEY or GROK_API_KEY is set."
    if grok_live_key_configured():
        reason = (
            "A Grok/xAI key name is set, but this spike does not call out. "
            "Share ids and deep links are not used."
        )
    return {
        "object": "grok_template_mapper",
        "schema": SCHEMA,
        "transport": "file-only",
        "live_call": "skipped",
        "reason": reason,
        "share_id": "not-used",
        "deep_link": "not-used",
        "field_map": field_map,
        "findings": [
            reason,
            "Grok Bot share ids and deep links were not requested. Fetching grok.com or x.ai would be an unsolicited scrape.",
            "Interop is file JSON: kind grok_bot_template maps onto kind agent_template and back.",
            "POST /v1/agent-templates/from-grok/ accepts that file shape and returns the canonical pack.",
            "Routines and plugins pass through as the same fragments as the agent template schema.",
        ],
    }


def _fill_in_label(key: str) -> str:
    return _FILL_IN_LABELS.get(key, key.replace("_", " "))


def _fill_in(
    key: str, *, locations: list[str], required: bool = True
) -> dict[str, Any]:
    return {
        "key": key,
        "label": _fill_in_label(key),
        "required": required,
        "locations": list(locations),
        "status": "pending",
    }


def _scan_fill_ins(text: str, *, location: str) -> list[tuple[str, str]]:
    return [(match.group(1), location) for match in _FILL_IN_RE.finditer(text or "")]


def _walk_strings(value: Any, prefix: str, found: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _walk_strings(item, f"{prefix}.{key}", found)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _walk_strings(item, f"{prefix}[{index}]", found)
    elif isinstance(value, str):
        found.extend(_scan_fill_ins(value, location=prefix))


def _normalize_trigger(raw: Any, *, index: int) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise FragmentError(
            f"routines[{index}].trigger must be an object with kind",
            code="template_routines_invalid",
        )
    kind = str(raw.get("kind") or "").strip()
    if not kind:
        raise FragmentError(
            f"routines[{index}].trigger.kind is required",
            code="template_routines_invalid",
        )
    trigger = {"kind": kind}
    for key in sorted(_TRIGGER_KEYS - {"kind"}):
        if key not in raw or raw[key] is None:
            continue
        trigger[key] = str(raw[key])
    return trigger


def normalize_routine(raw: Any, *, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise FragmentError(
            f"routines[{index}] must be an object with name, instruction, and trigger",
            code="template_routines_invalid",
        )
    name = str(raw.get("name") or "").strip()
    if not name:
        raise FragmentError(
            f"routines[{index}].name is required", code="template_routines_invalid"
        )
    instruction = str(raw.get("instruction") or "")
    trigger = _normalize_trigger(raw.get("trigger"), index=index)
    found: list[tuple[str, str]] = []
    found.extend(_scan_fill_ins(name, location="name"))
    found.extend(_scan_fill_ins(instruction, location="instruction"))
    _walk_strings(trigger, "trigger", found)
    locations: dict[str, list[str]] = {}
    for key, loc in found:
        bucket = locations.setdefault(key, [])
        if loc not in bucket:
            bucket.append(loc)
    declared = raw.get("fill_ins") if isinstance(raw.get("fill_ins"), list) else []
    for item in declared:
        if isinstance(item, dict) and str(item.get("key") or "").strip():
            locations.setdefault(str(item["key"]).strip(), [])
        elif isinstance(item, str) and item.strip():
            locations.setdefault(item.strip(), [])
    row: dict[str, Any] = {
        "name": name,
        "instruction": instruction,
        "trigger": trigger,
        "fill_ins": [_fill_in(key, locations=locs) for key, locs in locations.items()],
    }
    for optional in ("description", "key", "role"):
        text = str(raw.get(optional) or "").strip()
        if text:
            row[optional] = text
    return row


def normalize_routines(raw: Any) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("routines")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise FragmentError("routines must be a list", code="template_routines_invalid")
    return [normalize_routine(item, index=index) for index, item in enumerate(raw)]


def merge_fill_ins(routines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for routine in routines:
        for slot in routine.get("fill_ins") or []:
            key = str(slot.get("key") or "").strip()
            if not key:
                continue
            current = merged.setdefault(key, _fill_in(key, locations=[]))
            for loc in slot.get("locations") or []:
                if loc not in current["locations"]:
                    current["locations"].append(loc)
    return list(merged.values())


def _plugin_id(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, dict):
        return ""
    for key in ("pluginId", "plugin_id", "id"):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_plugin(raw: Any, *, index: int) -> dict[str, str]:
    if isinstance(raw, str):
        incoming: dict[str, Any] = {"pluginId": raw.strip()}
    elif isinstance(raw, dict):
        incoming = dict(raw)
    else:
        raise FragmentError(
            f"plugins[{index}] must be a plugin id or {{pluginId, name, description}}",
            code="template_plugins_invalid",
        )
    refused = sorted(
        str(key) for key in incoming if str(key).strip().lower() in _PLUGIN_REFUSED
    )
    if refused:
        raise FragmentError(
            f"plugins[{index}] must be ids only; refused field(s): {', '.join(refused)}",
            code="template_secrets",
        )
    plugin_id = _plugin_id(incoming)
    if not plugin_id:
        raise FragmentError(
            f"plugins[{index}].pluginId is required", code="template_plugins_invalid"
        )
    name = str(incoming.get("name") or incoming.get("label") or "").strip()
    if not name:
        name = plugin_id.rsplit("/", 1)[-1]
    description = str(
        incoming.get("description") or incoming.get("summary") or ""
    ).strip()
    return {"pluginId": plugin_id, "name": name, "description": description}


def normalize_plugins(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if isinstance(raw, dict):
        raw = raw.get("plugins") or raw.get("pluginIds") or raw.get("ids")
    if raw is None:
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        raise FragmentError("plugins must be a list", code="template_plugins_invalid")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(raw):
        row = normalize_plugin(item, index=index)
        if row["pluginId"] in seen:
            continue
        seen.add(row["pluginId"])
        rows.append(row)
    return rows


def connect_checklist(plugins: list[dict[str, str]]) -> list[dict[str, str]]:
    """Plugins stay pending until an operator connects them on this host."""
    return [
        {
            "pluginId": row["pluginId"],
            "name": row.get("name") or row["pluginId"],
            "description": row.get("description") or "",
            "status": "pending",
            "detail": "Connect this plugin on the host before the agent can use it.",
        }
        for row in plugins
    ]


def fragments_path() -> Path:
    env = (os.environ.get(ENV_FRAGMENTS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / STORE_NAME


def reset_fragment_cache() -> None:
    global _cache, _cache_path
    _cache = None
    _cache_path = None


def _read_store() -> dict[str, Any]:
    global _cache, _cache_path
    path = fragments_path()
    key = str(path)
    if _cache is not None and _cache_path == key:
        return _cache
    if not path.is_file():
        _cache = {"schema": SCHEMA, "agents": {}}
        _cache_path = key
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read template fragments at %s", path, exc_info=True)
        _cache = {"schema": SCHEMA, "agents": {}}
        _cache_path = key
        return _cache
    agents = data.get("agents") if isinstance(data, dict) else None
    if not isinstance(agents, dict):
        agents = {}
    _cache = {"schema": SCHEMA, "agents": dict(agents)}
    _cache_path = key
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache, _cache_path
    path = fragments_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema": SCHEMA, "agents": store.get("agents") or {}}
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
    _cache = payload
    _cache_path = str(path)


def read_fragments(agent_id: str) -> dict[str, Any]:
    agent = normalize_agent_id(agent_id)
    stored = _read_store()["agents"].get(agent)
    if not isinstance(stored, dict):
        return {"routines": [], "plugins": []}
    routines = (
        stored.get("routines") if isinstance(stored.get("routines"), list) else []
    )
    plugins = stored.get("plugins") if isinstance(stored.get("plugins"), list) else []
    return {"routines": list(routines), "plugins": list(plugins)}


def write_fragments(agent_id: str, *, routines: list[Any], plugins: list[Any]) -> None:
    agent = normalize_agent_id(agent_id)
    store = _read_store()
    store["agents"][agent] = {"routines": routines, "plugins": plugins}
    _write_store(store)


def seat_occupied(agent_id: str) -> bool:
    agent = normalize_agent_id(agent_id)
    profile = get_profile(agent)
    if any(
        str(profile.get(key) or "").strip()
        for key in ("display_name", "description", "title")
    ):
        return True
    from swarm.core.agent_memory import list_memories
    from swarm.core.agent_skills import list_skills

    if list_memories(agent) or list_skills(agent):
        return True
    stored = read_fragments(agent)
    return bool(stored["routines"] or stored["plugins"])


def allocate_agent_id(display_name: str, preferred: str | None = None) -> str:
    """Pick a fresh seat id. A requested id that is already in use gets a suffix."""
    base_source = (
        (preferred or "").strip() or (display_name or "").strip() or "imported-agent"
    )
    base = normalize_agent_id(base_source)
    if not seat_occupied(base):
        return base
    for suffix in range(2, 51):
        candidate = normalize_agent_id(f"{base}-{suffix}")
        if not seat_occupied(candidate):
            return candidate
    raise FragmentError(
        "could not allocate a free agent id", code="template_agent_id_exhausted"
    )

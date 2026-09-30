"""Per-agent plugin pack (#1396).

Export packs marketplace plugin ids only (``pluginId``, optional name and
description). Custom / non-marketplace MCP servers are named in a scrubbed
memory log and left out of ``plugins[]``. Import attempts marketplace
install and enable, then reports ``enabled``, ``missing-auth`` (connect
needed), or ``missing-plugin``. Connection fields and token values never
travel in the pack. One plugin miss does not abort agent create.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from swarm.core.chat_plugin_tools import PLUGIN_CATALOG_IDS
from swarm.core.chat_store import normalize_agent_id
from swarm.core.mcp_registry import public_text
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
PACK_KIND = "agent_plugin_pack"
PACK_OBJECT = "agent_plugin_pack"
IMPORT_OBJECT = "agent_plugin_pack_import"
ENV_PLUGINS_PATH = "SWARM_AGENT_PLUGINS_PATH"

STATUS_ENABLED = "enabled"
STATUS_MISSING = "missing-plugin"
STATUS_MISSING_PLUGIN = STATUS_MISSING
STATUS_MISSING_AUTH = "missing-auth"

KEY_PLUGIN_ID = "pluginId"
KEY_NAME = "name"
KEY_DESCRIPTION = "description"

_REFUSED_KEYS = frozenset(
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
        "openapiSpecUrl",
        "cwd",
        "bearer",
    }
)
# Compared after stripping ``-`` and ``_`` so ``apiKey`` / ``api-key`` / ``private_key`` match.
_SECRET_KEY_TOKENS = (
    "secret",
    "token",
    "password",
    "apikey",
    "authorization",
    "credential",
    "privatekey",
    "bearer",
)
_SECRET_VALUE_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{4,}"
    r"|bearer\s+[A-Za-z0-9._\-]{8,}"
    r"|gh[pousr]_[A-Za-z0-9]{8,}"
    r"|-----BEGIN [A-Za-z0-9 ]{0,40}?PRIVATE KEY-----",
    re.IGNORECASE,
)
_REFUSED_COMPACT = frozenset(
    key.strip().lower().replace("-", "").replace("_", "") for key in _REFUSED_KEYS
)
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ID_PREFIXES = ("mcp:", "github:")

_cache: dict[str, Any] | None = None


class PluginPackError(ValueError):
    """Invalid plugin pack. ``code`` is stable for API clients."""

    def __init__(self, message: str, *, code: str = "plugin_pack_invalid") -> None:
        super().__init__(message)
        self.code = code


def plugins_path() -> Path:
    env = (os.environ.get(ENV_PLUGINS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_plugins.json"


def reset_agent_plugin_pack_cache() -> None:
    """Drop the in-process cache (tests)."""
    global _cache
    _cache = None


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = plugins_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read agent plugin pack store at %s", path, exc_info=True)
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
    path = plugins_path()
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


def _compact_key(key: Any) -> str:
    return str(key).strip().lower().replace("-", "").replace("_", "")


def _key_is_secret(key: Any) -> bool:
    compact = _compact_key(key)
    if compact in _REFUSED_COMPACT:
        return True
    return any(token in compact for token in _SECRET_KEY_TOKENS)


def _refuse_secrets(raw: Any, *, where: str) -> None:
    if isinstance(raw, dict):
        hits = sorted(str(key) for key in raw if _key_is_secret(key))
        if hits:
            raise PluginPackError(
                f"{where} must be plugin ids only; refused field(s): {', '.join(hits)}",
                code="plugin_pack_secrets",
            )
        for key, value in raw.items():
            _refuse_secrets(value, where=f"{where}.{key}")
    elif isinstance(raw, list):
        for index, item in enumerate(raw):
            _refuse_secrets(item, where=f"{where}[{index}]")
    elif isinstance(raw, str) and _SECRET_VALUE_RE.search(raw):
        raise PluginPackError(
            f"{where} looks like a credential and was refused.",
            code="plugin_pack_secrets",
        )


def _plugin_id(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, Mapping):
        return ""
    for key in (KEY_PLUGIN_ID, "plugin_id", "id", KEY_NAME):
        value = str(raw.get(key) or "").strip()
        if value:
            return value
    return ""


def public_plugin_row(raw: Any) -> dict[str, str]:
    """Stable id-only row. Raises :class:`PluginPackError` on secrets or blank id."""
    if isinstance(raw, str):
        incoming = {KEY_PLUGIN_ID: raw}
    elif isinstance(raw, Mapping):
        incoming = dict(raw)
    else:
        raise PluginPackError("plugin must be an id string or {pluginId, name?, description?}")
    _refuse_secrets(incoming, where="plugin")
    plugin_id = _plugin_id(incoming)
    if not plugin_id:
        raise PluginPackError("pluginId is required", code="plugin_pack_id_missing")
    if _SECRET_VALUE_RE.search(plugin_id):
        raise PluginPackError("pluginId looks like a credential and was refused.", code="plugin_pack_secrets")
    name = public_text(incoming.get(KEY_NAME) or incoming.get("label") or "", 80)
    if not name:
        name = plugin_id.rsplit("/", 1)[-1].removeprefix("mcp:").removeprefix("github:")
    description = public_text(incoming.get(KEY_DESCRIPTION) or incoming.get("summary") or "", 240)
    return {
        KEY_PLUGIN_ID: plugin_id,
        KEY_NAME: name,
        KEY_DESCRIPTION: description,
    }


def _plugins_payload(raw: Any) -> list[Any]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return raw
    if isinstance(raw, Mapping):
        for key in ("plugins", "pluginIds", "plugin_ids", "ids"):
            value = raw.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, str) and value.strip():
                return [value]
    if isinstance(raw, str) and raw.strip():
        return [raw]
    raise PluginPackError("pack must include plugins[] of plugin ids", code="plugin_pack_invalid")


def validate_pack(raw: Any) -> dict[str, Any]:
    """Normalize a plugin-id pack. Raises :class:`PluginPackError` on secrets."""
    if raw is None:
        raise PluginPackError("pack must be a JSON object or plugins list", code="plugin_pack_invalid")
    if isinstance(raw, list):
        incoming: dict[str, Any] = {"plugins": raw}
    elif isinstance(raw, Mapping):
        incoming = dict(raw)
    else:
        raise PluginPackError("pack must be a JSON object or plugins list", code="plugin_pack_invalid")
    _refuse_secrets(incoming, where="pack")
    rows = [public_plugin_row(item) for item in _plugins_payload(incoming)]
    seen: set[str] = set()
    plugins: list[dict[str, str]] = []
    for row in rows:
        key = row[KEY_PLUGIN_ID]
        if key in seen:
            continue
        seen.add(key)
        plugins.append(row)
    kind = str(incoming.get("kind") or PACK_KIND).strip() or PACK_KIND
    return {
        "object": PACK_OBJECT,
        "schema": SCHEMA,
        "kind": kind,
        "plugins": plugins,
    }


def list_plugin_rows(agent_id: str) -> list[dict[str, str]]:
    """Stored plugin-id rows for *agent_id* (empty when unset)."""
    agent = normalize_agent_id(agent_id)
    stored = _read_store()["agents"].get(agent)
    if not isinstance(stored, Mapping):
        return []
    raw = stored.get("plugins")
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw:
        try:
            row = public_plugin_row(item)
        except PluginPackError:
            continue
        if row[KEY_PLUGIN_ID] in seen:
            continue
        seen.add(row[KEY_PLUGIN_ID])
        out.append(row)
    return out


def replace_plugin_rows(agent_id: str, rows: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    agent = normalize_agent_id(agent_id)
    plugins = [public_plugin_row(item) for item in (rows or [])]
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for row in plugins:
        if row[KEY_PLUGIN_ID] in seen:
            continue
        seen.add(row[KEY_PLUGIN_ID])
        unique.append(row)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    agents[agent] = {"plugins": unique}
    _write_store({"schema": SCHEMA, "agents": agents})
    return unique


def _strip_prefixes(value: str) -> str:
    stripped = (value or "").strip().lower()
    changed = True
    while changed:
        changed = False
        for prefix in _ID_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :]
                changed = True
    return stripped


def _fold_underscores(item: str) -> str:
    """Hyphen-alias the bare id or the slash tail, not the owner segment."""
    if "/" not in item:
        return item.replace("_", "-")
    prefix, tail = item.rsplit("/", 1)
    return f"{prefix}/{tail.replace('_', '-')}"


def _strong_ids(value: str) -> set[str]:
    """Full-id forms. Slash tails are not included."""
    raw = (value or "").strip().lower()
    if not raw:
        return set()
    forms = {raw}
    stripped = _strip_prefixes(raw)
    if stripped and stripped != raw:
        forms.add(stripped)
    expanded: set[str] = set()
    for item in forms:
        hyphen = _fold_underscores(item)
        expanded.add(item)
        expanded.add(hyphen)
        expanded.add(f"mcp:{item}")
        expanded.add(f"mcp:{hyphen}")
    return {item for item in expanded if item and item != "mcp:"}


def _literal_ids(value: str) -> set[str]:
    """Ids written on the server, without underscore-to-hyphen aliases."""
    raw = (value or "").strip().lower()
    if not raw:
        return set()
    ids = {raw, f"mcp:{raw}"}
    stripped = _strip_prefixes(raw)
    if stripped and stripped != raw:
        ids.add(stripped)
        ids.add(f"mcp:{stripped}")
    return {item for item in ids if item and item != "mcp:"}


def _tail_ids(value: str) -> set[str]:
    stripped = _strip_prefixes(value)
    if "/" not in stripped:
        return set()
    tail = stripped.rsplit("/", 1)[-1]
    if not tail:
        return set()
    hyphen = tail.replace("_", "-")
    return {tail, hyphen, f"mcp:{tail}", f"mcp:{hyphen}"}


def _namespaced(plugin_id: str) -> bool:
    return "/" in _strip_prefixes(plugin_id)


def _spec_disabled(spec: Mapping[str, Any]) -> bool:
    from swarm.core.cli_mcp import mcp_entry_disabled

    return mcp_entry_disabled(spec)


def _primary_keys(name: str, spec: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    """Strong ids plus the literal ids that count as an exact hit."""
    registry = str(spec.get("registry_name") or "")
    primary = _strong_ids(name) | _strong_ids(registry)
    exact = _literal_ids(name) | _literal_ids(registry)
    return primary, exact


def _secondary_keys(name: str, spec: Mapping[str, Any], primary: set[str]) -> set[str]:
    """Labels and slash-tails. Used only when no full id matches."""
    registry = str(spec.get("registry_name") or "")
    label = str(spec.get("label") or "")
    keys = _tail_ids(name) | _tail_ids(registry) | _tail_ids(label) | _strong_ids(label)
    return {item for item in keys if item and item not in primary}


def _required_env_names(spec: Mapping[str, Any]) -> list[str]:
    from swarm.core.mcp_registry import required_env_names

    return list(required_env_names(spec if isinstance(spec, dict) else {}))


def _unsatisfied_env_names(spec: Mapping[str, Any]) -> list[str]:
    """Env names the server still needs. Values are never returned."""
    from swarm.core.mcp_plugins import _missing_env

    missing: list[str] = []
    seen: set[str] = set()
    for name in _missing_env(spec if isinstance(spec, dict) else {}):
        token = str(name).strip()
        if not token or token in seen or not _ENV_NAME_RE.match(token):
            continue
        seen.add(token)
        missing.append(token)
    return missing


def _env_names_only(names: Any) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for name in names or []:
        token = str(name).strip()
        if not token or token in seen or not _ENV_NAME_RE.match(token):
            continue
        seen.add(token)
        out.append(token)
    return out


def marketplace_plugin_id(name: str, spec: Mapping[str, Any]) -> str | None:
    """Marketplace id for an installed server, or a catalog tool id.

    Custom servers (no registry id, not a catalog tool) return None so
    callers can name them in memory instead of inventing a plugin row.
    """
    registry = str(spec.get("registry_name") or "").strip()
    if registry:
        if registry.startswith(("mcp:", "github:")):
            return registry
        return f"mcp:{registry}"
    server_name = str(name or "").strip()
    if server_name in PLUGIN_CATALOG_IDS:
        return server_name
    return None


def _installed_index(config: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    from swarm.core import mcp_plugins as plugins

    cfg = config if isinstance(config, Mapping) else plugins.swarm_config()
    servers = plugins.load_mcp_servers(cfg)
    entries: list[dict[str, Any]] = []
    for name, spec in servers.items():
        if not isinstance(spec, Mapping):
            spec = {}
        primary, exact = _primary_keys(str(name), spec)
        if _spec_disabled(spec):
            entries.append(
                {
                    "primary": primary,
                    "exact": exact,
                    "secondary": set(),
                    "disabled": True,
                    "row": {"name": str(name).strip()},
                }
            )
            continue
        registry_name = str(spec.get("registry_name") or "").strip()
        row = {
            "name": str(name).strip(),
            "label": public_text(spec.get("label") or name, 80),
            "description": public_text(spec.get("note") or "", 240),
            "required_env": _required_env_names(spec),
            "missing_env": _unsatisfied_env_names(spec),
            "registry_name": registry_name,
        }
        entries.append(
            {
                "primary": primary,
                "exact": exact,
                "secondary": _secondary_keys(str(name), spec, primary),
                "disabled": False,
                "row": row,
            }
        )
    return entries


def _find_installed(plugin_id: str, entries: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Resolve a pack id to one installed server.

    Full server names and registry ids win. A namespaced id (``owner/name``)
    never falls through to a slash-tail, so ``io.github.evil/fetch`` cannot
    attach a server whose id is ``io.github.example/fetch``. Bare ids still
    match a unique label or tail. A disabled server keeps its id, so a label
    cannot impersonate it.
    """
    strong = _strong_ids(plugin_id)
    if not strong:
        return None
    raw = (plugin_id or "").strip().lower()
    enabled = [entry for entry in entries if not entry.get("disabled")]
    blocked: set[str] = set()
    for entry in entries:
        if entry.get("disabled"):
            blocked |= set(entry.get("primary") or ())
    if strong & blocked and not any(strong & entry["primary"] for entry in enabled):
        return None
    primary_hits = [entry for entry in enabled if strong & entry["primary"]]
    if len(primary_hits) == 1:
        return primary_hits[0]["row"]
    if len(primary_hits) > 1:
        exact = [entry for entry in primary_hits if raw in (entry.get("exact") or ())]
        if len(exact) == 1:
            return exact[0]["row"]
        return None
    if _namespaced(plugin_id):
        labeled = [entry for entry in enabled if strong & entry["secondary"]]
        if len(labeled) == 1:
            return labeled[0]["row"]
        return None
    secondary_hits = [entry for entry in enabled if strong & entry["secondary"]]
    if len(secondary_hits) == 1:
        return secondary_hits[0]["row"]
    return None


def _match_index(plugin_id: str, index: Any) -> dict[str, Any] | None:
    if isinstance(index, list):
        return _find_installed(plugin_id, index)
    if isinstance(index, Mapping):
        for alias in _strong_ids(plugin_id):
            if alias in index:
                return index[alias]
    return None


def _is_catalog_id(plugin_id: str) -> str:
    """Return the catalog tool id when *plugin_id* is a built-in, else ``""``.

    A slash-tail is not a catalog id. ``io.github.evil/web_search`` must not
    enable the built-in ``web_search`` tool.
    """
    raw = str(plugin_id or "").strip()
    if raw in PLUGIN_CATALOG_IDS:
        return raw
    bare = _strip_prefixes(raw)
    if bare and "/" not in bare and bare in PLUGIN_CATALOG_IDS:
        return bare
    return ""


def _remember_custom_mcp(agent_id: str, *, name: str, note: str) -> None:
    """Scrubbed memory log that names a custom MCP. No commands or secrets."""
    from swarm.core.agent_memory import KIND_LOG, create_memory, list_memories
    from swarm.core.memory_scrubber import scrub_for_pack

    label = scrub_for_pack(public_text(name, 80)) or "unnamed"
    title = scrub_for_pack(f"custom MCP: {label}")[:200]
    body = scrub_for_pack(public_text(note, 240))
    if not title:
        return
    try:
        existing = list_memories(agent_id, kind=KIND_LOG)
    except Exception:
        logger.warning("custom MCP memory lookup failed for %s", agent_id, exc_info=True)
        return
    if any(isinstance(row, Mapping) and row.get("title") == title for row in existing):
        return
    try:
        create_memory(agent_id, {"kind": KIND_LOG, "title": title, "body": body or title})
    except ValueError:
        logger.info("custom MCP memory naming refused for %s", agent_id)


def _row_from_installed(plugin_id: str, installed: Mapping[str, Any]) -> dict[str, str]:
    return {
        KEY_PLUGIN_ID: plugin_id,
        KEY_NAME: str(installed.get("label") or installed.get("name") or plugin_id),
        KEY_DESCRIPTION: str(installed.get("description") or ""),
    }


def _host_servers(config: Mapping[str, Any] | None) -> dict[str, Any]:
    from swarm.core import mcp_plugins as plugins

    cfg = config if isinstance(config, Mapping) else plugins.swarm_config()
    servers = plugins.load_mcp_servers(cfg)
    return servers if isinstance(servers, dict) else {}


def _marketplace_rows_from_assigned(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Marketplace ids for assigned servers. Custom MCP becomes a memory log."""
    from swarm.core import agent_mcp as mcp

    assigned = list(mcp.get_mcp(agent_id).get(mcp.KEY_SERVERS) or [])
    if not assigned:
        return []
    servers = _host_servers(config)
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_name in assigned:
        name = str(raw_name).strip()
        if not name:
            continue
        spec = servers.get(name)
        if not isinstance(spec, Mapping):
            _remember_custom_mcp(agent_id, name=name, note="")
            continue
        if _spec_disabled(spec):
            continue
        plugin_id = marketplace_plugin_id(name, spec)
        if not plugin_id:
            _remember_custom_mcp(
                agent_id,
                name=str(spec.get("label") or name),
                note=str(spec.get("note") or ""),
            )
            continue
        if plugin_id in seen:
            continue
        seen.add(plugin_id)
        rows.append(
            _row_from_installed(
                plugin_id,
                {
                    "name": name,
                    "label": public_text(spec.get("label") or name, 80) or name,
                    "description": public_text(spec.get("note") or "", 240),
                },
            )
        )
    return rows


def plugins_section_for_pack(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Secret-free ``plugins`` list. Custom MCP is named in memory, not here."""
    discovered = _marketplace_rows_from_assigned(agent_id, config=config)
    stored = list_plugin_rows(agent_id)
    if stored:
        return stored
    return discovered


def export_pack(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Pack assigned plugin ids. Never includes tokens or connection fields."""
    agent = normalize_agent_id(agent_id)
    pack = validate_pack({"kind": PACK_KIND, "plugins": plugins_section_for_pack(agent, config=config)})
    pack["agent_id"] = agent
    return pack


def _status_shell(row: Mapping[str, str], *, status: str, source: str) -> dict[str, Any]:
    return {
        KEY_PLUGIN_ID: row[KEY_PLUGIN_ID],
        KEY_NAME: row.get(KEY_NAME) or row[KEY_PLUGIN_ID],
        KEY_DESCRIPTION: row.get(KEY_DESCRIPTION) or "",
        "status": status,
        "source": source,
    }


def _status_from_match(row: Mapping[str, str], match: Mapping[str, Any]) -> dict[str, Any]:
    missing = _env_names_only(match.get("missing_env") or [])
    payload = _status_shell(
        {
            KEY_PLUGIN_ID: row[KEY_PLUGIN_ID],
            KEY_NAME: row.get(KEY_NAME) or match.get("label") or match.get("name") or row[KEY_PLUGIN_ID],
            KEY_DESCRIPTION: row.get(KEY_DESCRIPTION) or match.get("description") or "",
        },
        status=STATUS_MISSING_AUTH if missing else STATUS_ENABLED,
        source="installed",
    )
    payload["server"] = match.get("name")
    names = missing or _env_names_only(match.get("required_env") or [])
    if names:
        payload["required_env"] = names
    if missing:
        payload["connect_needed"] = True
    return payload


def _resolve_status(
    row: Mapping[str, str],
    *,
    index: list[dict[str, Any]],
) -> dict[str, Any]:
    plugin_id = row[KEY_PLUGIN_ID]
    match = _match_index(plugin_id, index)
    if match is not None:
        return _status_from_match(row, match)
    if _is_catalog_id(plugin_id):
        return _status_shell(row, status=STATUS_ENABLED, source="catalog")
    return _status_shell(row, status=STATUS_MISSING_PLUGIN, source="pack")


def install_marketplace_plugin(plugin_id: str) -> dict[str, Any]:
    """Attempt a marketplace install for one plugin id. May raise.

    Tries the packed id, then the same id without an ``mcp:`` / ``github:``
    prefix, so a marketplace id still reaches the catalog.
    """
    from swarm.core.marketplace_catalog import MarketplaceCatalogError, install_item

    raw = str(plugin_id or "").strip()
    candidates: list[str] = []
    for candidate in (raw, raw.removeprefix("mcp:"), raw.removeprefix("github:")):
        if candidate and candidate not in candidates:
            candidates.append(candidate)
    last: Exception | None = None
    for candidate in candidates:
        try:
            return install_item("plugins", candidate)
        except MarketplaceCatalogError as exc:
            last = exc
            if exc.code == "not_found":
                continue
            raise
    if last is not None:
        raise last
    raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)


def _match_from_install(row: Mapping[str, str], result: Mapping[str, Any]) -> dict[str, Any] | None:
    if not result.get("installed"):
        return None
    name = str(result.get("name") or "").strip()
    required = _env_names_only(result.get("required_env") or [])
    missing = [item for item in required if not os.environ.get(item, "").strip()]
    if not name and not required:
        return None
    return {
        "name": name or row[KEY_PLUGIN_ID],
        "label": row.get(KEY_NAME) or name or row[KEY_PLUGIN_ID],
        "description": row.get(KEY_DESCRIPTION) or "",
        "required_env": required,
        "missing_env": missing,
        "registry_name": "",
    }


def _grant_catalog_if_policy_active(agent_id: str, plugin_id: str) -> None:
    """Add a catalog id to an existing grant allowlist.

    An empty grant list means "no policy" (every tool stays available).
    Writing a single id would turn that into a restrictive allowlist, so
    this only extends a policy that is already active.
    """
    try:
        from swarm.core.agent_settings import update_settings
        from swarm.core.mcp_tool_grants import grants_active, load_grants

        grants = load_grants(agent_id)
        if not grants_active(grants) or plugin_id in grants:
            return
        update_settings(agent_id, {"mcp_tool_grants": [*grants, plugin_id]})
    except Exception:
        logger.warning("catalog plugin enable skipped for %s", agent_id, exc_info=True)


def _enable_one(
    agent_id: str,
    row: Mapping[str, str],
    *,
    config: Mapping[str, Any] | None,
    index: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    """Install/enable one plugin. Failures become a status, not an exception."""
    plugin_id = row[KEY_PLUGIN_ID]
    install_result: Mapping[str, Any] | None = None
    try:
        raw_result = install_marketplace_plugin(plugin_id)
        if isinstance(raw_result, Mapping):
            install_result = raw_result
    except Exception as exc:
        install_result = None
        if getattr(exc, "code", "") == "not_found":
            logger.debug("marketplace plugin not installed for %s", agent_id)
        else:
            logger.info("marketplace install did not complete for %s", agent_id, exc_info=True)
    fresh = _installed_index(config)
    match = _match_index(plugin_id, fresh) or _match_index(plugin_id, index)
    if match is None and install_result is not None:
        match = _match_from_install(row, install_result)
    if match is not None:
        payload = _status_from_match(row, match)
        payload["install_attempted"] = True
        return payload
    catalog_id = _is_catalog_id(plugin_id)
    if catalog_id:
        _grant_catalog_if_policy_active(agent_id, catalog_id)
        payload = _status_shell(row, status=STATUS_ENABLED, source="catalog")
        payload["install_attempted"] = True
        return payload
    payload = _status_shell(row, status=STATUS_MISSING_PLUGIN, source="pack")
    payload["install_attempted"] = True
    return payload


def _attach_servers(agent_id: str, statuses: list[dict[str, Any]]) -> None:
    """Attach installed servers. A store error must not abort the caller."""
    from swarm.core import agent_mcp as mcp

    attachable = {STATUS_ENABLED, STATUS_MISSING_AUTH}
    servers = [
        str(row.get("server") or "").strip()
        for row in statuses
        if row.get("status") in attachable and row.get("source") == "installed"
    ]
    servers = [name for name in servers if name]
    if not servers:
        return
    try:
        current = mcp.get_mcp(agent_id)
        merged = list(current.get(mcp.KEY_SERVERS) or [])
        seen = {str(name).strip() for name in merged}
        for name in servers:
            if name not in seen:
                merged.append(name)
                seen.add(name)
        mode = current.get(mcp.KEY_MODE) or mcp.MODE_OFF
        if mode == mcp.MODE_OFF:
            mode = mcp.MODE_ALL
        mcp.update_mcp(agent_id, {mcp.KEY_MODE: mode, mcp.KEY_SERVERS: merged})
    except Exception:
        logger.warning("plugin pack attach failed for %s", agent_id, exc_info=True)
        for row in statuses:
            if row.get("server") and row.get("status") in attachable:
                row["attach_error"] = "mcp_update_failed"


def import_status_payload(statuses: list[dict[str, Any]], *, agent_id: str) -> dict[str, Any]:
    """Public import result. Tokens, urls, commands, and env values stay out."""
    enabled = [row[KEY_PLUGIN_ID] for row in statuses if row.get("status") == STATUS_ENABLED]
    missing_plugin = [row[KEY_PLUGIN_ID] for row in statuses if row.get("status") == STATUS_MISSING_PLUGIN]
    missing_auth = [row[KEY_PLUGIN_ID] for row in statuses if row.get("status") == STATUS_MISSING_AUTH]
    safe_rows = []
    for row in statuses:
        item = {
            KEY_PLUGIN_ID: row[KEY_PLUGIN_ID],
            KEY_NAME: row.get(KEY_NAME) or row[KEY_PLUGIN_ID],
            KEY_DESCRIPTION: row.get(KEY_DESCRIPTION) or "",
            "status": row.get("status") or STATUS_MISSING_PLUGIN,
        }
        names = _env_names_only(row.get("required_env") or [])
        if names:
            item["required_env"] = names
        if row.get("connect_needed"):
            item["connect_needed"] = True
        if row.get("install_attempted"):
            item["install_attempted"] = True
        safe_rows.append(item)
    return {
        "object": IMPORT_OBJECT,
        "agent_id": normalize_agent_id(agent_id),
        "plugins": safe_rows,
        "enabled": enabled,
        "missing": missing_plugin,
        "missing_plugin": missing_plugin,
        "missing_auth": missing_auth,
    }


def host_status(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Current plugin ids plus host install status (no tokens)."""
    pack = export_pack(agent_id, config=config)
    index = _installed_index(config)
    statuses = [_resolve_status(row, index=index) for row in pack["plugins"]]
    payload = import_status_payload(statuses, agent_id=agent_id)
    payload["object"] = "agent_plugins"
    payload["pack"] = {key: pack[key] for key in ("object", "schema", "kind", "plugins")}
    return payload


def import_pack(
    agent_id: str,
    raw: Any,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist packed plugin ids and report host status without tokens."""
    agent = normalize_agent_id(agent_id)
    pack = validate_pack(raw)
    replace_plugin_rows(agent, pack["plugins"])
    index = _installed_index(config)
    statuses: list[dict[str, Any]] = []
    for row in pack["plugins"]:
        try:
            statuses.append(_enable_one(agent, row, config=config, index=index))
        except Exception:
            logger.warning("plugin enable failed for %s", agent, exc_info=True)
            failed = _status_shell(row, status=STATUS_MISSING_PLUGIN, source="pack")
            failed["install_attempted"] = True
            statuses.append(failed)
    _attach_servers(agent, statuses)
    payload = import_status_payload(statuses, agent_id=agent)
    payload["pack"] = pack
    return payload


def export_pack_fragment(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Template fragment: marketplace plugin ids only."""
    pack = export_pack(agent_id, config=config)
    return {key: pack[key] for key in ("object", "schema", "kind", "plugins")}


def import_pack_fragment(
    agent_id: str,
    raw: Any,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Import a template plugin fragment. Same contract as :func:`import_pack`."""
    return import_pack(agent_id, raw, config=config)


def apply_plugin_pack_on_create(
    agent_id: str,
    raw: Any,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Import plugins after the agent exists.

    Secret refusal and per-plugin misses are reported on the payload.
    This function does not raise, so agent create can keep the new seat.
    """
    agent = normalize_agent_id(agent_id)
    if raw in (None, "", [], {}):
        payload = import_status_payload([], agent_id=agent)
        payload["ok"] = True
        return payload
    try:
        payload = import_pack(agent, raw, config=config)
    except PluginPackError as exc:
        logger.info("plugin pack refused during agent create for %s (%s)", agent, exc.code)
        return {
            "object": IMPORT_OBJECT,
            "agent_id": agent,
            "ok": False,
            "code": exc.code,
            "error": str(exc),
            "plugins": [],
            "enabled": [],
            "missing": [],
            "missing_plugin": [],
            "missing_auth": [],
        }
    except Exception:
        logger.warning("plugin pack failed during agent create for %s", agent, exc_info=True)
        return {
            "object": IMPORT_OBJECT,
            "agent_id": agent,
            "ok": False,
            "code": "plugin_pack_error",
            "error": "Plugin import failed; the agent was still created.",
            "plugins": [],
            "enabled": [],
            "missing": [],
            "missing_plugin": [],
            "missing_auth": [],
        }
    payload["ok"] = True
    return payload

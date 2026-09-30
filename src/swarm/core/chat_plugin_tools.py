"""Per-bot plugin tool allowlist (#805 / #516 / #1313).

The SPA sends ``params.enabled_tools`` — ids the operator turned On for the
current bot. Catalog / fixture plugin tools that are Off are excluded.
Blueprint-native functions that are not in the catalog stay available.

#1313 persists those ids as ``mcp_tool_grants`` on the agent-settings bag so
a turn without ``enabled_tools`` still honours the bot's grant set, and a
client cannot widen it.

#502 extends the catalog with discovered MCP tool names from configured
servers (see ``swarm.core.mcp_plugins.plugin_catalog_ids``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Keep in sync with webui/frontend/src/lib/chatPluginTools.ts FIXTURE_PLUGIN_TOOLS.
PLUGIN_CATALOG_IDS: frozenset[str] = frozenset(
    {
        "web_search",
        "web_fetch",
        "browser_navigate",
        "browser_snapshot",
        "browser_click",
        "browser_type",
        "read_file",
        "write_file",
        "list_directory",
        "git_status",
        "git_diff",
        "git_log",
        "get_current_time",
        "convert_timezone",
    }
)


def tool_name(fn: Any) -> str:
    name = getattr(fn, "name", None) or getattr(fn, "__name__", None) or ""
    return str(name)


def allowlist_from_persistent_tools(
    persistent_tools: Mapping[str, Any] | None,
    server_catalog: Mapping[str, Iterable[str]] | None = None,
) -> list[str] | None:
    """Flatten ``{server: [tool, ...] | "*"}`` into tool names.

    ``None`` when the map is omitted. ``"*"`` expands via ``server_catalog``.
    An explicit list is kept as written, including ``[]`` (that server grants
    nothing). A non-empty map is the bot's grant and beats a turn list.
    """
    if not isinstance(persistent_tools, Mapping) or not persistent_tools:
        return None
    catalog = server_catalog or {}
    out: list[str] = []
    seen: set[str] = set()
    for server, entry in persistent_tools.items():
        if entry == "*" or (isinstance(entry, str) and entry.strip() == "*"):
            raw = catalog.get(str(server), ())
            names = [str(item).strip() for item in raw]
        elif isinstance(entry, (list, tuple)):
            names = [str(item).strip() for item in entry]
        else:
            continue
        for name in names:
            if not name or name in seen:
                continue
            seen.add(name)
            out.append(name)
    return out


def _resolve_allowlist(
    enabled_tools: Iterable[Any] | None,
    persistent_tools: Mapping[str, Any] | None,
    server_catalog: Mapping[str, Iterable[str]] | None,
) -> Iterable[Any] | None:
    """Persisted ``mcp_tools`` wins. A turn list applies only when the map is omitted."""
    flattened = allowlist_from_persistent_tools(persistent_tools, server_catalog)
    if flattened is not None:
        return flattened
    return enabled_tools


def filter_plugin_tools_for_chat(
    functions: Iterable[Any] | None,
    enabled_tools: Iterable[Any] | None,
    catalog_ids: Iterable[str] | None = None,
    *,
    persistent_tools: Mapping[str, Any] | None = None,
    server_catalog: Mapping[str, Iterable[str]] | None = None,
) -> list[Any]:
    """Drop catalog plugin tools that are not in the per-chat allowlist."""
    items = list(functions or [])
    enabled_tools = _resolve_allowlist(enabled_tools, persistent_tools, server_catalog)
    enabled = {str(item).strip() for item in (enabled_tools or []) if str(item).strip()}
    catalog = frozenset(str(item).strip() for item in catalog_ids) if catalog_ids is not None else PLUGIN_CATALOG_IDS
    catalog = frozenset(item for item in catalog if item)
    kept: list[Any] = []
    for fn in items:
        name = tool_name(fn)
        if name in catalog and name not in enabled:
            continue
        kept.append(fn)
    return kept


def _filter_agent(
    agent: Any,
    enabled_tools: Iterable[Any] | None,
    catalog_ids: Iterable[str] | None = None,
) -> list[str]:
    removed: list[str] = []
    for attr in ("functions", "tools"):
        current = getattr(agent, attr, None)
        if isinstance(current, list):
            before = {getattr(fn, "name", None) or getattr(fn, "__name__", None) for fn in current}
            setattr(agent, attr, filter_plugin_tools_for_chat(current, enabled_tools, catalog_ids=catalog_ids))
            after = {getattr(fn, "name", None) or getattr(fn, "__name__", None) for fn in getattr(agent, attr)}
            removed.extend(sorted(before - after))
    return removed


def apply_chat_plugin_allowlist(
    blueprint: Any,
    enabled_tools: Iterable[Any] | None,
    catalog_ids: Iterable[str] | None = None,
    *,
    persistent_tools: Mapping[str, Any] | None = None,
    server_catalog: Mapping[str, Iterable[str]] | None = None,
) -> list[str]:
    """Filter plugin tools on a loaded blueprint's agents (in place).

    Returns the sorted names removed (#1263) so the caller can log an honest
    per-turn count. Also patches a ``_plugin_factory_tools`` registry (#1263):
    when tool attachment wrapped ``create_starting_agent``, the allowlist
    drops any registry tool NOT in ``enabled_tools`` from the factory path so
    a toggled-off plugin stays off for agents built later in the same turn.

    ``persistent_tools`` is the bot's ``mcp_tools`` map. When it is set, it is
    the grant for this turn. A client ``enabled_tools`` list cannot replace it.
    """
    enabled_tools = _resolve_allowlist(enabled_tools, persistent_tools, server_catalog)
    removed: list[str] = []
    agents = getattr(blueprint, "agents", None)
    if isinstance(agents, dict):
        for agent in agents.values():
            removed.extend(_filter_agent(agent, enabled_tools, catalog_ids=catalog_ids))
    elif isinstance(agents, list):
        for agent in agents:
            removed.extend(_filter_agent(agent, enabled_tools, catalog_ids=catalog_ids))
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting):
        removed.extend(_filter_agent(starting, enabled_tools, catalog_ids=catalog_ids))

    # #1263: keep the factory registry consistent with this chat's allowlist.
    registry = getattr(blueprint, "_plugin_factory_tools", None)
    if isinstance(registry, list):
        allowed = {str(item).strip() for item in (enabled_tools or []) if str(item).strip()}
        kept: list = []
        for entry in registry:
            if not (isinstance(entry, tuple) and len(entry) == 3):
                kept.append(entry)
                continue
            name, tools, sink = entry
            keep_tools = [t for t in tools if str(getattr(t, "name", "")) in allowed]
            dropped = [str(getattr(t, "name", "")) for t in tools if str(getattr(t, "name", "")) not in allowed]
            removed.extend(dropped)
            if keep_tools:
                kept.append((name, keep_tools, sink))
        registry[:] = kept
    return sorted(set(removed))

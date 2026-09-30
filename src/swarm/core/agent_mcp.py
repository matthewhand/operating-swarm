"""MCP tool modes for API managed agents (#142).

Modes:

* ``all`` — every tool from the agent's allowed MCP servers is attached.
* ``progressive`` — the agent only gets list → inspect → execute meta-tools.
* ``off`` — no MCP tools (default until registration or a mode PATCH).

Persisted in ``agent_mcp.json`` so registration and mode switches survive restarts.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from swarm.core.chat_store import normalize_agent_id
from swarm.core.paths import (
    ensure_swarm_directories_exist,
    get_user_config_dir_for_swarm,
)

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_MCP_PATH = "SWARM_AGENT_MCP_PATH"

MODE_OFF = "off"
MODE_ALL = "all"
MODE_PROGRESSIVE = "progressive"
MCP_MODES = (MODE_OFF, MODE_ALL, MODE_PROGRESSIVE)

LIST_TOOL = "list_mcp_tools"
INSPECT_TOOL = "inspect_mcp_tool"
EXECUTE_TOOL = "execute_mcp_tool"
PROGRESSIVE_TOOLS = (LIST_TOOL, INSPECT_TOOL, EXECUTE_TOOL)

KEY_MODE = "mode"
KEY_SERVERS = "mcp_servers"
KEY_TOOLS = "mcp_tools"
STAR = "*"

_MODE_ALIASES = {
    "off": MODE_OFF,
    "none": MODE_OFF,
    "disabled": MODE_OFF,
    "all": MODE_ALL,
    "all_mcp": MODE_ALL,
    "all-mcp": MODE_ALL,
    "all mcp": MODE_ALL,
    "unrestricted": MODE_ALL,
    "progressive": MODE_PROGRESSIVE,
    "progressive_mcp": MODE_PROGRESSIVE,
    "progressive-mcp": MODE_PROGRESSIVE,
    "progressive mcp": MODE_PROGRESSIVE,
    "step": MODE_PROGRESSIVE,
}

DEFAULTS: dict[str, Any] = {
    KEY_MODE: MODE_OFF,
    KEY_SERVERS: [],
    KEY_TOOLS: {},
}

_cache: dict[str, Any] | None = None


class McpAccessError(Exception):
    """Unauthorized or missing MCP tool access for a managed agent."""

    def __init__(self, message: str, *, code: str = "unauthorized", status: int = 403):
        super().__init__(message)
        self.code = code
        self.status = status


def mcp_path() -> Path:
    env = (os.environ.get(ENV_MCP_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "agent_mcp.json"


def reset_agent_mcp_cache() -> None:
    """Drop the in-process cache (tests)."""
    global _cache
    _cache = None


def normalize_mcp_mode(value: Any, *, default: str = MODE_OFF) -> str:
    if value is None:
        return default if default in MCP_MODES else MODE_OFF
    text = str(value).strip().lower().replace("-", "_")
    text = " ".join(text.split())
    if not text:
        return default if default in MCP_MODES else MODE_OFF
    mapped = _MODE_ALIASES.get(text) or _MODE_ALIASES.get(text.replace(" ", "_"))
    if mapped:
        return mapped
    raise ValueError(
        "mcp_mode must be 'all' (unrestricted MCP tools) or "
        "'progressive' (list, inspect, then execute)."
    )


def normalize_mcp_servers(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",") if part.strip()]
        return list(dict.fromkeys(parts))
    if not isinstance(value, (list, tuple)):
        raise ValueError("mcp_servers must be a list of server names.")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name[:80])
    return out


def normalize_mcp_tools(value: Any) -> dict[str, list[str] | str]:
    """Normalize ``{server: [tool, ...] | "*"}``.

    ``None`` and ``{}`` are an omitted map (server-level behaviour). A server
    value of ``"*"`` keeps every tool on that server. A list is an explicit
    grant, including ``[]`` (the server is granted and none of its tools).
    """
    if value is None or value == "" or value == {}:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("mcp_tools must be an object mapping server names to tool lists or '*'.")
    out: dict[str, list[str] | str] = {}
    for raw_server, raw_tools in value.items():
        server = str(raw_server).strip()[:80]
        if not server:
            continue
        if isinstance(raw_tools, str) and raw_tools.strip() == STAR:
            out[server] = STAR
            continue
        if isinstance(raw_tools, str):
            raw_tools = [part.strip() for part in raw_tools.split(",") if part.strip()]
        if not isinstance(raw_tools, (list, tuple)):
            raise ValueError(f"mcp_tools[{server}] must be a list of tool names or '*'.")
        names: list[str] = []
        seen: set[str] = set()
        for item in raw_tools:
            if not isinstance(item, str):
                raise ValueError(f"mcp_tools[{server}] entries must be tool name strings.")
            name = item.strip()
            if not name or name in seen:
                continue
            if len(name) > 120:
                raise ValueError("mcp_tools entry exceeds 120 characters.")
            seen.add(name)
            names.append(name)
        out[server] = names
    return out


def mcp_fields_from_raw(raw: Mapping[str, Any] | None, *, kind: str = "") -> dict[str, Any]:
    """Extract MCP registration fields. Empty when the payload omits them."""
    incoming = raw if isinstance(raw, Mapping) else {}
    has_mode = "mcp_mode" in incoming
    has_servers = "mcp_servers" in incoming
    has_tools = "mcp_tools" in incoming or KEY_TOOLS in incoming
    if not has_mode and not has_servers and not has_tools:
        return {}
    if kind in ("cli", "remote") and (has_mode or has_servers or has_tools):
        # An off mode and an empty map are not a grant. Only a live mode or a
        # non-empty tool list is rejected, matching the pre-#1571 check.
        default = MODE_ALL if has_servers and not has_mode else MODE_OFF
        mode = (
            normalize_mcp_mode(incoming.get("mcp_mode"), default=default)
            if has_mode or has_servers
            else MODE_OFF
        )
        tools = (
            normalize_mcp_tools(incoming.get("mcp_tools", incoming.get(KEY_TOOLS)))
            if has_tools
            else {}
        )
        tools_on = any(
            entry == STAR or (isinstance(entry, list) and len(entry) > 0)
            for entry in tools.values()
        )
        if mode != MODE_OFF or tools_on:
            raise ValueError(
                "MCP tool modes apply to API managed agents, not CLI or remote teams."
            )
    fields: dict[str, Any] = {}
    if has_mode or has_servers:
        default = MODE_ALL if has_servers and not has_mode else MODE_OFF
        mode = normalize_mcp_mode(incoming.get("mcp_mode"), default=default)
        fields["mcp_mode"] = mode
        fields["mcp_servers"] = normalize_mcp_servers(incoming.get("mcp_servers"))
    if has_tools:
        fields["mcp_tools"] = normalize_mcp_tools(
            incoming.get("mcp_tools", incoming.get(KEY_TOOLS))
        )
    return fields


def public_mcp(raw: Mapping[str, Any] | None = None) -> dict[str, Any]:
    mode = MODE_OFF
    servers: list[str] = []
    tools: dict[str, list[str] | str] = {}
    if isinstance(raw, Mapping):
        try:
            mode = normalize_mcp_mode(raw.get(KEY_MODE, raw.get("mcp_mode")), default=MODE_OFF)
        except ValueError:
            mode = MODE_OFF
        try:
            servers = normalize_mcp_servers(raw.get(KEY_SERVERS, raw.get("mcp_servers")))
        except ValueError:
            servers = []
        try:
            tools = normalize_mcp_tools(raw.get(KEY_TOOLS, raw.get("mcp_tools")))
        except ValueError:
            tools = {}
    return {
        KEY_MODE: mode,
        KEY_SERVERS: list(servers),
        KEY_TOOLS: tools,
        "enabled": mode != MODE_OFF,
    }


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "agents": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = mcp_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read agent MCP store at %s", path, exc_info=True)
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
    path = mcp_path()
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


def get_mcp(agent_id: str, *, spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Runtime MCP config. Store wins; design spec is the fallback."""
    agent = normalize_agent_id(agent_id)
    stored = _read_store()["agents"].get(agent)
    if isinstance(stored, dict):
        return public_mcp(stored)
    if isinstance(spec, Mapping):
        return public_mcp(spec)
    return public_mcp(None)


def register_mcp(
    agent_id: str,
    *,
    mode: Any = MODE_ALL,
    mcp_servers: Any = None,
    mcp_tools: Any = None,
) -> dict[str, Any]:
    """Persist MCP capability for a newly registered API agent."""
    patch: dict[str, Any] = {KEY_MODE: mode, KEY_SERVERS: mcp_servers}
    if mcp_tools is not None:
        patch[KEY_TOOLS] = mcp_tools
    return update_mcp(agent_id, patch)


def update_mcp(agent_id: str, patch: Mapping[str, Any] | None) -> dict[str, Any]:
    """Merge ``patch`` into one agent's MCP config and persist."""
    agent = normalize_agent_id(agent_id)
    incoming = dict(patch) if isinstance(patch, Mapping) else {}
    current = get_mcp(agent)
    if "mcp_mode" in incoming or KEY_MODE in incoming:
        current[KEY_MODE] = normalize_mcp_mode(
            incoming.get("mcp_mode", incoming.get(KEY_MODE)),
            default=current[KEY_MODE],
        )
    if KEY_SERVERS in incoming or "servers" in incoming:
        current[KEY_SERVERS] = normalize_mcp_servers(
            incoming.get(KEY_SERVERS, incoming.get("servers"))
        )
    if KEY_TOOLS in incoming or "mcp_tools" in incoming:
        current[KEY_TOOLS] = normalize_mcp_tools(
            incoming.get(KEY_TOOLS, incoming.get("mcp_tools"))
        )
    unknown = [
        key
        for key in incoming
        if key not in {KEY_MODE, KEY_SERVERS, KEY_TOOLS, "mcp_mode", "mcp_tools", "servers"}
    ]
    if unknown:
        raise ValueError(f"Unknown MCP setting(s): {', '.join(sorted(unknown))}.")
    public = public_mcp(current)
    store = _read_store()
    agents = dict(store.get("agents") or {})
    agents[agent] = {
        KEY_MODE: public[KEY_MODE],
        KEY_SERVERS: list(public[KEY_SERVERS]),
        KEY_TOOLS: public[KEY_TOOLS],
    }
    _write_store({"schema": SCHEMA, "agents": agents})
    _mirror_to_design(agent, public)
    return public


def _mirror_to_design(agent_id: str, mcp: Mapping[str, Any]) -> None:
    try:
        from swarm.core.router_designs import load_designs, save_designs

        agents = load_designs()
        changed = False
        for row in agents:
            if row.get("agent_id") == agent_id:
                row["mcp_mode"] = mcp[KEY_MODE]
                row["mcp_servers"] = list(mcp[KEY_SERVERS])
                row["mcp_tools"] = dict(mcp.get(KEY_TOOLS) or {})
                changed = True
                break
        if changed:
            save_designs(agents)
    except Exception:
        logger.debug("Could not mirror MCP settings onto agent design", exc_info=True)


def _allowed_servers(mcp: Mapping[str, Any]) -> list[str] | None:
    names = [str(item).strip() for item in (mcp.get(KEY_SERVERS) or []) if str(item).strip()]
    return names or None


def _tool_map(mcp: Mapping[str, Any] | None) -> dict[str, Any]:
    raw = (mcp or {}).get(KEY_TOOLS) if isinstance(mcp, Mapping) else None
    if not isinstance(raw, Mapping) or not raw:
        return {}
    return dict(raw)


def _allowed_tools(server: str, mcp: Mapping[str, Any] | None = None) -> list[str] | None:
    """Tool grant for one server.

    ``None`` means no tool-level restriction: the map is omitted, or this
    server is granted ``"*"`` (today's select behaviour). An active map that
    does not name ``server`` returns ``[]``. An explicit list is that grant.
    """
    mapping = _tool_map(mcp)
    if not mapping:
        return None
    if server not in mapping:
        return []
    entry = mapping[server]
    if entry == STAR:
        return None
    if isinstance(entry, list):
        return list(entry)
    return []


def catalog_tools(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
    scope: str = "effective",
) -> list[dict[str, Any]]:
    """Tools this agent may list / inspect / execute.

    ``scope="effective"`` honours ``mcp_tools`` when present, otherwise
    ``mcp_servers``, otherwise every enabled server. ``scope="all"`` is the
    enabled catalog with no per-bot filter (used to detach a revoked tool).
    """
    from swarm.core import mcp_plugins as plugins

    mcp = get_mcp(agent_id, spec=spec)
    if scope not in {"effective", "servers", "all"}:
        scope = "effective"
    tool_map = _tool_map(mcp) if scope == "effective" else {}
    allow = None if scope == "all" or tool_map else _allowed_servers(mcp)
    rows: list[dict[str, Any]] = []
    cfg = config if isinstance(config, dict) else plugins.swarm_config()
    enabled = plugins.enabled_mcp_servers(cfg)
    saved = plugins.load_mcp_servers(cfg)
    for name, spec_row in enabled.items():
        if allow is not None and name not in allow:
            continue
        granted: list[str] | None = None
        if tool_map:
            if name not in tool_map:
                continue
            granted = _allowed_tools(name, mcp)
            if granted is not None and not granted:
                continue
        merged = {**saved.get(name, {}), **spec_row}
        metas = merged.get("discovered_tools")
        if not isinstance(metas, list) or not metas:
            provides = merged.get("provides") or []
            if isinstance(provides, str):
                provides = [provides]
            metas = [
                {"name": str(cap).strip(), "description": str(merged.get("note") or "")}
                for cap in provides
                if str(cap).strip()
            ]
        for item in metas:
            if isinstance(item, dict):
                tool_name = str(item.get("name") or "").strip()
                description = str(item.get("description") or "").strip()
                schema = item.get("input_schema") or item.get("inputSchema") or {}
            else:
                tool_name = str(item).strip()
                description = ""
                schema = {}
            if not tool_name:
                continue
            if granted is not None and tool_name not in granted:
                continue
            rows.append(
                {
                    "name": tool_name,
                    "description": description,
                    "server": name,
                    "input_schema": schema if isinstance(schema, dict) else {},
                }
            )
    from swarm.core.mcp_tool_grants import filter_catalog_rows

    return filter_catalog_rows(rows, agent_id)


def _require_enabled(agent_id: str, *, spec: Mapping[str, Any] | None = None) -> dict[str, Any]:
    mcp = get_mcp(agent_id, spec=spec)
    if mcp[KEY_MODE] == MODE_OFF:
        raise McpAccessError(
            "This agent is not registered for MCP tools.",
            code="unauthorized",
            status=403,
        )
    return mcp


def list_tools(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    _require_enabled(agent_id, spec=spec)
    return catalog_tools(agent_id, config=config, spec=spec)


def inspect_tool(
    agent_id: str,
    tool_name: str,
    *,
    config: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    _require_enabled(agent_id, spec=spec)
    name = str(tool_name or "").strip()
    if not name:
        raise ValueError("tool name is required")
    for row in catalog_tools(agent_id, config=config, spec=spec):
        if row["name"] == name:
            return {
                "name": row["name"],
                "description": row["description"],
                "server": row["server"],
                "input_schema": row.get("input_schema") or {},
                "parameters": row.get("input_schema") or {},
            }
    raise McpAccessError(
        f"MCP tool {name!r} is not available to this agent.",
        code="unauthorized",
        status=403,
    )


def _spec_for_server(server: str, config: Mapping[str, Any] | None) -> dict[str, Any]:
    from swarm.core import mcp_plugins as plugins

    cfg = config if isinstance(config, dict) else plugins.swarm_config()
    enabled = plugins.enabled_mcp_servers(cfg)
    if server not in enabled:
        raise McpAccessError(
            f"MCP server {server!r} is disabled or missing.",
            code="unauthorized",
            status=403,
        )
    saved = plugins.load_mcp_servers(cfg)
    return {**saved.get(server, {}), **enabled[server]}


def execute_tool(
    agent_id: str,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
    *,
    config: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
    execute_fn: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    details = inspect_tool(agent_id, tool_name, config=config, spec=spec)
    args = dict(arguments or {})
    server_spec = _spec_for_server(str(details["server"]), config)
    if execute_fn is not None:
        result = execute_fn(details["name"], server_spec, args)
    else:
        from swarm.core.mcp_plugins import call_plugin_mcp_tool

        result = call_plugin_mcp_tool(details["name"], server_spec, args)
    return {
        "ok": True,
        "tool": details["name"],
        "server": details["server"],
        "result": _jsonable(result),
    }


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return _jsonable(dump())
        except Exception:
            pass
    content = getattr(value, "content", None)
    if content is not None:
        return {"content": _jsonable(content)}
    return str(value)


def _tool_name(fn: Any) -> str:
    name = getattr(fn, "name", None) or getattr(fn, "__name__", None) or ""
    return str(name)


def _iter_agents(blueprint: Any) -> list[Any]:
    agents: list[Any] = []
    raw = getattr(blueprint, "agents", None)
    if isinstance(raw, dict):
        agents.extend(raw.values())
    elif isinstance(raw, list):
        agents.extend(raw)
    starting = getattr(blueprint, "starting_agent", None)
    if starting is not None and not callable(starting) and starting not in agents:
        agents.append(starting)
    router = getattr(blueprint, "_agents", None)
    if isinstance(router, dict):
        for agent in router.values():
            if agent not in agents:
                agents.append(agent)
    return agents


def _strip_mcp_tools(agent: Any, catalog_names: set[str]) -> None:
    drop = set(catalog_names) | set(PROGRESSIVE_TOOLS)
    for attr in ("functions", "tools"):
        current = getattr(agent, attr, None)
        if isinstance(current, list):
            setattr(agent, attr, [fn for fn in current if _tool_name(fn) not in drop])


def _ensure_list(agent: Any, attr: str) -> list[Any] | None:
    current = getattr(agent, attr, None)
    if current is None:
        try:
            setattr(agent, attr, [])
            current = getattr(agent, attr)
        except Exception:
            return None
    return current if isinstance(current, list) else None


def _append_tools(agent: Any, tools: Iterable[Any]) -> list[str]:
    attached: list[str] = []
    extras = list(tools)
    if not extras:
        return attached
    for attr in ("functions", "tools"):
        current = _ensure_list(agent, attr)
        if current is None:
            continue
        have = {_tool_name(fn) for fn in current}
        for tool in extras:
            name = _tool_name(tool)
            if not name or name in have:
                continue
            current.append(tool)
            have.add(name)
            attached.append(name)
    return attached


def _all_mode_tools(
    agent_id: str,
    *,
    config: Mapping[str, Any] | None,
    spec: Mapping[str, Any] | None,
    scope: str = "effective",
) -> list[Any]:
    from swarm.core.mcp_plugins import tools_from_server

    tools: list[Any] = []
    seen: set[str] = set()
    cfg = config
    for row in catalog_tools(agent_id, config=cfg, spec=spec, scope=scope):
        if row["name"] in seen:
            continue
        seen.add(row["name"])
        server_spec = _spec_for_server(str(row["server"]), cfg)
        for tool in tools_from_server(str(row["server"]), server_spec):
            if _tool_name(tool) == row["name"] and _tool_name(tool) not in {
                _tool_name(existing) for existing in tools
            }:
                tools.append(tool)
    return tools


def _progressive_callables(agent_id: str) -> list[Any]:
    ident = normalize_agent_id(agent_id)

    def list_mcp_tools() -> dict[str, Any]:
        """List MCP tools this agent may inspect and execute."""
        return {"object": "mcp_tool_list", "tools": list_tools(ident)}

    def inspect_mcp_tool(name: str) -> dict[str, Any]:
        """Inspect one MCP tool's description and parameters."""
        return inspect_tool(ident, name)

    def execute_mcp_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a previously listed MCP tool with JSON arguments."""
        return execute_tool(ident, name, arguments)

    list_mcp_tools.name = LIST_TOOL
    list_mcp_tools.description = (
        "List MCP tools available to this agent. Inspect a tool before executing it."
    )
    inspect_mcp_tool.name = INSPECT_TOOL
    inspect_mcp_tool.description = (
        "Inspect one MCP tool (description and parameters) before executing it."
    )
    execute_mcp_tool.name = EXECUTE_TOOL
    execute_mcp_tool.description = (
        "Execute one MCP tool by name with a JSON arguments object."
    )
    return [list_mcp_tools, inspect_mcp_tool, execute_mcp_tool]


def _progressive_tools(agent_id: str) -> list[Any]:
    try:
        from agents import function_tool
    except Exception:
        function_tool = None
    if function_tool is not None:
        wrapped = []
        for fn in _progressive_callables(agent_id):
            # #890: newer openai-agents + pydantic enforce strict JSON schemas
            # that reject dict[str, Any] returns (additionalProperties). These
            # meta tools are free-form by design, so opt out of strict mode.
            try:
                wrapped.append(function_tool(fn, strict_mode=False))
            except TypeError:  # older SDK without the kwarg
                wrapped.append(function_tool(fn))
        if wrapped:
            return wrapped
    from swarm.types import Tool

    return [
        Tool(
            name=getattr(fn, "name", fn.__name__),
            func=fn,
            description=getattr(fn, "description", "") or "",
        )
        for fn in _progressive_callables(agent_id)
    ]


def apply_mcp_to_agent(
    agent: Any,
    agent_id: str,
    *,
    config: Mapping[str, Any] | None = None,
    spec: Mapping[str, Any] | None = None,
) -> list[str]:
    """Attach MCP tools for ``agent_id``'s current mode. Idempotent.

    A persisted ``mcp_tools`` map is the tool grant for every turn. A client
    ``enabled_tools`` list is not an override: it cannot add a tool the map
    omitted, and an empty list cannot clear the grant. Tools dropped from the
    grant are stripped on this call — no process restart. An omitted map
    keeps server-level ``mcp_servers`` behaviour.
    """
    from swarm.core.chat_plugin_tools import filter_plugin_tools_for_chat

    mcp = get_mcp(agent_id, spec=spec)
    detach_names = {
        row["name"]
        for row in catalog_tools(agent_id, config=config, spec=spec, scope="all")
    }
    _strip_mcp_tools(agent, detach_names)
    if mcp[KEY_MODE] == MODE_OFF:
        return []
    tool_map = _tool_map(mcp)
    allow = None if tool_map else _allowed_servers(mcp)
    server_names = list(tool_map) if tool_map else list(allow or [])
    if server_names:
        try:
            agent.mcp_servers = server_names
        except Exception:
            pass
    if mcp[KEY_MODE] == MODE_PROGRESSIVE:
        return _append_tools(agent, _progressive_tools(agent_id))
    tools = _all_mode_tools(agent_id, config=config, spec=spec, scope="effective")
    if tool_map:
        allowed = [
            row["name"]
            for row in catalog_tools(agent_id, config=config, spec=spec, scope="effective")
        ]
        tools = filter_plugin_tools_for_chat(tools, allowed, catalog_ids=detach_names)
    return _append_tools(agent, tools)


def install_mcp_for_runtime(
    blueprint: Any,
    *,
    caller_id: str,
    params: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> list[str]:
    """Attach MCP tools for an API managed agent chat/completions run."""
    agent_id = normalize_agent_id(caller_id)
    params = params if isinstance(params, Mapping) else {}
    cfg = config
    if cfg is None:
        raw_cfg = getattr(blueprint, "config", None)
        cfg = raw_cfg if isinstance(raw_cfg, dict) else None
    spec = None
    if isinstance(params.get("mcp_mode"), str) or params.get("mcp_servers") is not None:
        spec = {
            "mcp_mode": params.get("mcp_mode"),
            "mcp_servers": params.get("mcp_servers"),
        }
    if get_mcp(agent_id, spec=spec)[KEY_MODE] == MODE_OFF:
        return []
    attached: list[str] = []
    targets = _iter_agents(blueprint)
    if not targets and blueprint is not None:
        targets = [blueprint]
    for agent in targets:
        attached.extend(
            apply_mcp_to_agent(
                agent,
                agent_id,
                config=cfg,
                spec=spec,
            )
        )
    return attached


def apply_turn_plugin_tools(
    blueprint: Any,
    agent_id: str,
    params: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> None:
    """Attach plugin MCP tools for one turn.

    A persisted ``mcp_tools`` map is the grant on every turn, including when
    the client still sends ``params.enabled_tools`` (the SPA's per-chat list,
    often ``[]``). That list cannot replace or widen the map. An omitted map
    leaves the existing grant-list / per-turn allowlist path, which is today's
    server-level behaviour.

    A saved ``mcp_tool_grants`` policy still caps every path, including an
    explicit empty list (deny-all). ``grants_active`` is the wrong check
    for that: it is false for ``[]``.
    """
    from swarm.core.chat_plugin_tools import allowlist_from_persistent_tools
    from swarm.core.mcp_plugins import (
        apply_plugin_mcp_runtime,
        server_tool_index,
        swarm_config,
    )
    from swarm.core.mcp_tool_grants import (
        intersect_with_grants,
        load_grant_state,
        resolve_enabled_tools,
    )

    incoming = params if isinstance(params, Mapping) else {}
    cfg = config if isinstance(config, dict) else getattr(blueprint, "config", None)
    if not isinstance(cfg, dict):
        cfg = swarm_config()
    record = get_mcp(str(agent_id or ""))
    persistent = record.get(KEY_TOOLS) or {}
    policy, configured = load_grant_state(str(agent_id or ""))
    enforced = configured or bool(policy)
    if persistent:
        expanded = allowlist_from_persistent_tools(persistent, server_tool_index(cfg)) or []
        if enforced:
            expanded = intersect_with_grants(expanded, policy)
        apply_plugin_mcp_runtime(blueprint, cfg, expanded)
        return
    resolved = resolve_enabled_tools(str(agent_id or ""), incoming)
    if resolved is not None:
        apply_plugin_mcp_runtime(blueprint, cfg, resolved)

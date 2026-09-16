"""Plugins manage path (#502 / #750): swarm as an MCP *client*.

Server topology is global (``swarm_config.json`` ``mcpServers``). Tool On/Off
is per-chat (#805 ``params.enabled_tools``). Distinct from
``ENABLE_MCP_SERVER`` (exposing swarm *as* an MCP server).

Local servers use stdio (command + args + env ``${VAR}``). Remote servers use
a URL plus optional headers whose values are env placeholders — never plaintext
secrets. OpenAPI-backed servers (#750) launch or attach
``mcp-openapi-proxy`` (https://github.com/matthewhand/mcp-openapi-proxy)
so OpenAPI operations become MCP tools. Live ``list_tools`` is injectable so
CI uses fixture mocks, not hosts.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from collections.abc import Callable, Iterable, Mapping
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from swarm.core.chat_plugin_tools import PLUGIN_CATALOG_IDS, apply_chat_plugin_allowlist
from swarm.core.cli_mcp import normalize_mcp_servers
from swarm.core.config_ownership import (
    ConfigOwnershipError,
    is_placeholder,
    looks_like_env_name,
    refuse_plaintext_secrets,
)

logger = logging.getLogger(__name__)

KIND_LOCAL = "local"
KIND_REMOTE = "remote"
SOURCE_GENERIC = "generic"
SOURCE_OPENAPI = "openapi"
OPENAPI_PROXY_COMMAND = "uvx"
OPENAPI_PROXY_ARGS = ("mcp-openapi-proxy",)
OPENAPI_SPEC_ENV = "OPENAPI_SPEC_URL"
OPENAPI_PROXY_PACKAGE = "mcp-openapi-proxy"
_OPENAPI_SOURCE_ALIASES = frozenset(
    {"openapi", "mcp-openapi-proxy", "openapi-proxy", "openapi_proxy"}
)
_PLACEHOLDER_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_SAFE_URL_SCHEMES = frozenset({"http", "https"})
_FILE_SCHEMES = frozenset({"file"})

ListToolsFn = Callable[[dict[str, Any]], list[dict[str, str]]]


class McpPluginError(Exception):
    """Honest operator-facing MCP plugin failure (connect / validate)."""

    def __init__(self, message: str, *, code: str = "mcp_plugin_error", status: int = 400):
        super().__init__(message)
        self.code = code
        self.status = status


def _slug(name: str) -> str:
    raw = (name or "").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "mcp-server"


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = [part.strip() for part in re.split(r"[\s,]+", value) if part.strip()]
        return parts
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _placeholder_map(value: Any, *, field: str) -> dict[str, str]:
    """Keep only ``${VAR}`` / ENV_NAME values. Refuse plaintext secrets."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise McpPluginError(f"{field} must be an object of ${{VAR}} placeholders.", code="bad_payload")
    out: dict[str, str] = {}
    for raw_key, raw_val in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        if raw_val is None or raw_val == "":
            continue
        if not isinstance(raw_val, str):
            raise McpPluginError(
                f"Refusing plaintext secret at {field}.{key}. Use ${{ENV_VAR}}.",
                code="plaintext_secret",
            )
        trimmed = raw_val.strip()
        if is_placeholder(trimmed):
            out[key] = trimmed
            continue
        if looks_like_env_name(trimmed):
            out[key] = f"${{{trimmed}}}"
            continue
        raise McpPluginError(
            f"Refusing plaintext secret at {field}.{key}. Use ${{ENV_VAR}}.",
            code="plaintext_secret",
        )
    return out


def _kind_of(spec: Mapping[str, Any] | None) -> str:
    raw = spec or {}
    explicit = str(raw.get("kind") or raw.get("type") or raw.get("transport") or "").strip().lower()
    if explicit in {KIND_LOCAL, "stdio"}:
        return KIND_LOCAL
    if explicit in {KIND_REMOTE, "http", "sse", "url", "streamable-http", "streamable_http"}:
        return KIND_REMOTE
    if isinstance(raw.get("url"), str) and raw["url"].strip():
        return KIND_REMOTE
    return KIND_LOCAL


def _args_mention_openapi_proxy(spec: Mapping[str, Any] | None) -> bool:
    raw = spec or {}
    haystack = " ".join(
        [str(raw.get("command") or "")] + [str(item) for item in (raw.get("args") or [])]
    )
    return OPENAPI_PROXY_PACKAGE in haystack


def _source_of(spec: Mapping[str, Any] | None) -> str:
    raw = spec or {}
    explicit = str(raw.get("source") or raw.get("adapter") or "").strip().lower()
    if explicit in _OPENAPI_SOURCE_ALIASES:
        return SOURCE_OPENAPI
    if str(raw.get("openapi_spec_url") or raw.get("openapiSpecUrl") or raw.get("spec_url") or "").strip():
        return SOURCE_OPENAPI
    env = raw.get("env")
    if isinstance(env, dict) and str(env.get(OPENAPI_SPEC_ENV) or "").strip():
        return SOURCE_OPENAPI
    if _args_mention_openapi_proxy(raw):
        return SOURCE_OPENAPI
    return SOURCE_GENERIC


def _looks_like_local_path(value: str) -> bool:
    trimmed = (value or "").strip()
    if not trimmed:
        return False
    return trimmed.startswith(("/", "./", "../", "~/")) or (
        len(trimmed) >= 2 and trimmed[1] == ":" and trimmed[0].isalpha()
    )


def _normalize_openapi_spec_source(value: Any, *, allow_file: bool) -> str:
    """Accept http(s) spec URLs; local mode also accepts a file path / file://."""
    trimmed = str(value or "").strip()
    if not trimmed:
        return ""
    if trimmed.startswith("${") or looks_like_env_name(trimmed):
        raise McpPluginError(
            "OpenAPI spec source must be a URL or local file path, not an env name. "
            f"The proxy reads {OPENAPI_SPEC_ENV} from the saved spec field.",
            code="bad_payload",
        )
    if "://" not in trimmed and _looks_like_local_path(trimmed):
        if not allow_file:
            raise McpPluginError(
                "Remote OpenAPI uses a running proxy MCP URL. "
                "Local file specs are for Local (stdio mcp-openapi-proxy) only.",
                code="bad_payload",
            )
        expanded = os.path.expanduser(trimmed)
        path = Path(expanded).expanduser()
        if path.exists() and path.is_file():
            return path.resolve().as_uri()
        if path.is_absolute() or trimmed.startswith(("/", "file:")):
            return Path(expanded).absolute().as_uri()
        return f"file://{expanded}"
    parsed = urlparse(trimmed)
    if parsed.scheme in _FILE_SCHEMES:
        if not allow_file:
            raise McpPluginError(
                "Remote OpenAPI uses a running proxy MCP URL. "
                "file:// specs are for Local (stdio mcp-openapi-proxy) only.",
                code="bad_payload",
            )
        if parsed.username or parsed.password:
            raise McpPluginError(
                "Refusing credentials in the OpenAPI spec URL. Use a ${VAR} env for API_KEY.",
                code="plaintext_secret",
            )
        return trimmed
    if parsed.scheme in _SAFE_URL_SCHEMES and parsed.netloc:
        if parsed.username or parsed.password:
            raise McpPluginError(
                "Refusing credentials in the OpenAPI spec URL. Use a ${VAR} env for API_KEY.",
                code="plaintext_secret",
            )
        return trimmed
    raise McpPluginError(
        "OpenAPI spec source must be an http(s) URL"
        + (" or a local file path." if allow_file else "."),
        code="bad_payload",
    )


def _lift_openapi_spec_from_env(raw_env: Any) -> tuple[dict[str, Any], str]:
    """Pull a literal OPENAPI_SPEC_URL out of env so it is not treated as a secret."""
    if not isinstance(raw_env, dict):
        return {}, ""
    lifted = ""
    rest: dict[str, Any] = {}
    for raw_key, raw_val in raw_env.items():
        key = str(raw_key).strip()
        if (
            key == OPENAPI_SPEC_ENV
            and isinstance(raw_val, str)
            and raw_val.strip()
            and not is_placeholder(raw_val)
            and not looks_like_env_name(raw_val)
        ):
            lifted = raw_val.strip()
            continue
        rest[key] = raw_val
    return rest, lifted


def _apply_openapi_defaults(entry: dict[str, Any], raw: Mapping[str, Any]) -> dict[str, Any]:
    """Fill mcp-openapi-proxy command/env for the OpenAPI add path (#750)."""
    kind = entry["kind"]
    allow_file = kind == KIND_LOCAL
    raw_spec = (
        raw.get("openapi_spec_url")
        or raw.get("openapiSpecUrl")
        or raw.get("spec_url")
        or raw.get("spec")
        or ""
    )
    spec_url = _normalize_openapi_spec_source(raw_spec, allow_file=allow_file) if raw_spec else ""
    if not spec_url:
        existing = str(entry.get("openapi_spec_url") or "").strip()
        spec_url = _normalize_openapi_spec_source(existing, allow_file=allow_file) if existing else ""
    env = dict(entry.get("env") or {})
    env_spec = env.pop(OPENAPI_SPEC_ENV, "")
    if not spec_url and env_spec:
        spec_url = _normalize_openapi_spec_source(env_spec, allow_file=allow_file)
    if spec_url:
        entry["openapi_spec_url"] = spec_url
    entry["source"] = SOURCE_OPENAPI
    if kind == KIND_REMOTE:
        if not str(entry.get("url") or "").strip():
            raise McpPluginError(
                "Remote OpenAPI needs the running proxy MCP URL (http/s). "
                "Use Local to launch mcp-openapi-proxy with OPENAPI_SPEC_URL.",
                code="bad_payload",
            )
        return entry
    if not spec_url:
        raise McpPluginError(
            "Local OpenAPI (mcp-openapi-proxy) needs an OpenAPI spec URL or file path.",
            code="bad_payload",
        )
    command = str(raw.get("command") or entry.get("command") or OPENAPI_PROXY_COMMAND).strip()
    args = _str_list(raw.get("args") if raw.get("args") not in (None, "") else entry.get("args"))
    if not command:
        command = OPENAPI_PROXY_COMMAND
    if not args:
        args = list(OPENAPI_PROXY_ARGS)
    entry["command"] = command
    entry["args"] = args
    env[OPENAPI_SPEC_ENV] = spec_url
    entry["env"] = env
    return entry


def _with_openapi_runtime_env(spec: Mapping[str, Any]) -> dict[str, Any]:
    """Ensure the stdio child sees OPENAPI_SPEC_URL (name only in docs; value is the spec)."""
    out = dict(spec)
    if _source_of(out) != SOURCE_OPENAPI:
        return out
    spec_url = str(out.get("openapi_spec_url") or "").strip()
    env = dict(out.get("env") or {}) if isinstance(out.get("env"), dict) else {}
    if spec_url:
        env.setdefault(OPENAPI_SPEC_ENV, spec_url)
    if env:
        out["env"] = env
    return out


def _openapi_discover_hint(exc: Exception, spec: Mapping[str, Any]) -> str:
    text = str(exc) or exc.__class__.__name__
    lowered = text.lower()
    if _source_of(spec) != SOURCE_OPENAPI and not _args_mention_openapi_proxy(spec):
        return f"Could not list tools from the MCP server: {text}"
    if isinstance(exc, FileNotFoundError) or "no such file" in lowered or "not found" in lowered:
        return (
            "mcp-openapi-proxy is not installed. "
            "Install with: uvx mcp-openapi-proxy (PyPI) or pip install mcp-openapi-proxy."
        )
    if "timeout" in lowered or "timed out" in lowered:
        return (
            "Connect timeout talking to mcp-openapi-proxy. "
            f"Check {OPENAPI_SPEC_ENV} and that the proxy can fetch the spec."
        )
    return f"Could not list tools from mcp-openapi-proxy: {text}"


def _validate_remote_url(url: str) -> str:
    trimmed = (url or "").strip()
    if not trimmed:
        raise McpPluginError("Remote MCP servers need an http(s) URL.", code="bad_payload")
    parsed = urlparse(trimmed)
    if parsed.scheme not in _SAFE_URL_SCHEMES or not parsed.netloc:
        raise McpPluginError(
            "Remote MCP URL must be http(s) with a host. Do not paste secrets in the URL.",
            code="bad_payload",
        )
    if parsed.username or parsed.password:
        raise McpPluginError(
            "Refusing credentials in the remote MCP URL. Use a ${VAR} header instead.",
            code="plaintext_secret",
        )
    return trimmed


def normalize_plugin_spec(raw: Any, *, name: str = "") -> dict[str, Any]:
    """Normalize a Plugins UI / API body into a ``mcpServers`` entry."""
    if not isinstance(raw, dict):
        raise McpPluginError("Server config must be an object.", code="bad_payload")
    try:
        refuse_plaintext_secrets(raw)
    except ConfigOwnershipError as exc:
        raise McpPluginError(str(exc), code=exc.code, status=exc.status) from exc
    display = str(raw.get("label") or raw.get("name") or name).strip()
    key = _slug(str(raw.get("id") or raw.get("name") or name))
    kind = _kind_of(raw)
    source = _source_of(raw)
    enabled = raw.get("enabled")
    entry: dict[str, Any] = {
        "name": key,
        "label": display or key,
        "kind": kind,
        "source": source,
        "enabled": not (enabled is False or enabled == "false"),
        "provides": _str_list(raw.get("provides")),
        "note": str(raw.get("note") or "").strip(),
    }
    raw_env, lifted_spec = _lift_openapi_spec_from_env(raw.get("env"))
    env = _placeholder_map(raw_env, field="env")
    if lifted_spec:
        entry["openapi_spec_url"] = lifted_spec
    if env:
        entry["env"] = env
    headers = _placeholder_map(raw.get("headers"), field="headers")
    if headers:
        entry["headers"] = headers
    discovered = raw.get("discovered_tools") or raw.get("tools")
    if isinstance(discovered, list):
        tools: list[dict[str, str]] = []
        for item in discovered:
            if not isinstance(item, dict):
                continue
            tool_name = str(item.get("name") or "").strip()
            if not tool_name:
                continue
            tools.append(
                {
                    "name": tool_name,
                    "description": str(item.get("description") or "").strip(),
                }
            )
        if tools:
            entry["discovered_tools"] = tools
            if not entry["provides"]:
                entry["provides"] = [row["name"] for row in tools]
    if kind == KIND_REMOTE:
        url_value = str(raw.get("url") or "")
        if source == SOURCE_OPENAPI and not url_value.strip():
            raise McpPluginError(
                "Remote OpenAPI needs the running proxy MCP URL (http/s). "
                "Use Local to launch mcp-openapi-proxy with OPENAPI_SPEC_URL.",
                code="bad_payload",
            )
        entry["url"] = _validate_remote_url(url_value)
        transport = str(raw.get("type") or raw.get("transport") or "sse").strip() or "sse"
        entry["type"] = transport
    else:
        command = str(raw.get("command") or "").strip()
        if source == SOURCE_OPENAPI and not command:
            command = OPENAPI_PROXY_COMMAND
        if not command:
            raise McpPluginError("Local MCP servers need a command (stdio).", code="bad_payload")
        entry["command"] = command
        entry["args"] = _str_list(raw.get("args"))
        cwd = str(raw.get("cwd") or "").strip()
        if cwd:
            entry["cwd"] = cwd
    if source == SOURCE_OPENAPI:
        _apply_openapi_defaults(entry, raw)
    return entry


def spec_to_config_entry(spec: Mapping[str, Any]) -> dict[str, Any]:
    """``swarm_config.json`` ``mcpServers`` value (no duplicate name key)."""
    entry = dict(spec)
    entry.pop("name", None)
    return entry


def public_server(name: str, spec: Mapping[str, Any] | None) -> dict[str, Any]:
    """Redacted server row for the Plugins UI. No secret values."""
    from swarm.core.config_ownership import redact_for_api

    raw = spec if isinstance(spec, dict) else {}
    kind = _kind_of(raw)
    redacted = redact_for_api(raw)
    tools = []
    discovered = raw.get("discovered_tools")
    if isinstance(discovered, list):
        tools = [
            {
                "name": str(item.get("name") or "").strip(),
                "description": str(item.get("description") or "").strip(),
            }
            for item in discovered
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ]
    if not tools:
        tools = [
            {"name": cap, "description": str(raw.get("note") or "").strip()}
            for cap in _str_list(raw.get("provides"))
        ]
    return {
        "name": name,
        "label": str(raw.get("label") or name),
        "kind": kind,
        "source": _source_of(raw),
        "enabled": raw.get("enabled") is not False,
        "command": str(redacted.get("command") or ""),
        "args": list(redacted.get("args") or []),
        "url": str(redacted.get("url") or ""),
        "openapi_spec_url": str(raw.get("openapi_spec_url") or ""),
        "type": str(redacted.get("type") or redacted.get("transport") or ""),
        "cwd": str(redacted.get("cwd") or ""),
        "env": redacted.get("env") if isinstance(redacted.get("env"), dict) else {},
        "headers": redacted.get("headers") if isinstance(redacted.get("headers"), dict) else {},
        "provides": _str_list(raw.get("provides")),
        "note": str(raw.get("note") or ""),
        "tools": tools,
    }


def load_mcp_servers(config: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    raw = (config or {}).get("mcpServers")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for name, spec in raw.items():
        key = str(name).strip()
        if not key or not isinstance(spec, dict):
            continue
        out[key] = dict(spec)
    return out


def enabled_mcp_servers(config: Mapping[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Enabled local/remote servers (``enabled: false`` dropped)."""
    return normalize_mcp_servers(load_mcp_servers(config))


def plugin_catalog_ids(config: Mapping[str, Any] | None = None) -> frozenset[str]:
    """Fixture ids plus discovered / provides names from configured servers."""
    ids = set(PLUGIN_CATALOG_IDS)
    for spec in load_mcp_servers(config).values():
        if spec.get("enabled") is False:
            continue
        for item in spec.get("discovered_tools") or []:
            if isinstance(item, dict) and item.get("name"):
                ids.add(str(item["name"]).strip())
        for cap in _str_list(spec.get("provides")):
            ids.add(cap)
    return frozenset(name for name in ids if name)


def _expand_placeholders(value: Any) -> Any:
    from swarm.core.config_loader import _substitute_env_vars

    return _substitute_env_vars(value)


def _missing_env(spec: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for field in ("env", "headers"):
        block = spec.get(field)
        if not isinstance(block, dict):
            continue
        for _key, raw in block.items():
            name = ""
            if isinstance(raw, str):
                match = _PLACEHOLDER_RE.match(raw.strip())
                name = match.group(1) if match else (raw.strip() if looks_like_env_name(raw) else "")
            if name and not os.environ.get(name, "").strip():
                missing.append(name)
    return missing


def _tool_rows(tools: Iterable[Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for tool in tools:
        if isinstance(tool, dict):
            name = str(tool.get("name") or "").strip()
            description = str(tool.get("description") or "").strip()
        else:
            name = str(getattr(tool, "name", "") or "").strip()
            description = str(getattr(tool, "description", "") or "").strip()
        if name:
            rows.append({"name": name, "description": description})
    return rows


async def _discover_local(spec: Mapping[str, Any], *, timeout: int) -> list[dict[str, str]]:
    from swarm.extensions.mcp.mcp_client import MCPClient

    live = _with_openapi_runtime_env(spec)
    client = MCPClient(
        {
            "command": live.get("command"),
            "args": list(live.get("args") or []),
            "env": live.get("env") or {},
        },
        timeout=timeout,
        debug=False,
    )
    return _tool_rows(await client.list_tools())


async def _discover_remote(spec: Mapping[str, Any], *, timeout: int) -> list[dict[str, str]]:
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    url = str(spec.get("url") or "")
    headers = spec.get("headers") if isinstance(spec.get("headers"), dict) else None
    # Never log header values — they may contain resolved secrets after expand.
    async with (
        sse_client(url, headers=headers, timeout=float(timeout)) as (read, write),
        ClientSession(read, write) as session,
    ):
        await asyncio.wait_for(session.initialize(), timeout=timeout)
        response = await asyncio.wait_for(session.list_tools(), timeout=timeout)
        return _tool_rows(getattr(response, "tools", None) or [])


async def _discover_live(spec: Mapping[str, Any], *, timeout: int = 15) -> list[dict[str, str]]:
    kind = _kind_of(spec)
    if kind == KIND_REMOTE:
        return await _discover_remote(spec, timeout=timeout)
    return await _discover_local(spec, timeout=timeout)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise McpPluginError(
        "MCP discover was called from a running event loop without a mock.",
        code="mcp_discover_failed",
        status=500,
    )


def list_tools_for_spec(
    spec: Mapping[str, Any],
    *,
    list_tools_fn: ListToolsFn | None = None,
    timeout: int = 15,
) -> list[dict[str, str]]:
    """Connect and list tools. ``list_tools_fn`` is the CI/test seam (no live host)."""
    normalized = normalize_plugin_spec(dict(spec), name=str(spec.get("name") or "server"))
    if normalized.get("enabled") is False:
        raise McpPluginError("Server is disabled. Enable it before discovering tools.", code="disabled")
    if list_tools_fn is not None:
        return _tool_rows(list_tools_fn(_with_openapi_runtime_env(normalized)))
    missing = _missing_env(normalized)
    if missing:
        names = ", ".join(sorted(set(missing)))
        raise McpPluginError(
            f"Secret env {names} is not set. Export the variable; do not paste the value.",
            code="secret_unset",
        )
    live = _with_openapi_runtime_env(_expand_placeholders(normalized))
    try:
        return _tool_rows(_run_async(_discover_live(live, timeout=timeout)))
    except McpPluginError:
        raise
    except Exception as exc:
        logger.warning("MCP list_tools failed for %s", normalized.get("name") or normalized.get("kind"))
        raise McpPluginError(
            _openapi_discover_hint(exc, normalized),
            code="mcp_discover_failed",
            status=502,
        ) from exc


def discover_and_store(
    name: str,
    spec: Mapping[str, Any] | None = None,
    *,
    config: Mapping[str, Any] | None = None,
    list_tools_fn: ListToolsFn | None = None,
    persist: bool = True,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
    """Discover tools for a named server (saved or draft). Optionally persist names."""
    key = _slug(name)
    saved = load_mcp_servers(config).get(key)
    raw = dict(saved or {})
    if spec:
        raw.update(spec)
    raw.setdefault("name", key)
    normalized = normalize_plugin_spec(raw, name=key)
    tools = list_tools_for_spec(normalized, list_tools_fn=list_tools_fn)
    normalized["discovered_tools"] = tools
    normalized["provides"] = [row["name"] for row in tools]
    if persist and saved is not None:
        from swarm.core.config_ownership import persist_webui_section

        persist_webui_section(
            "mcpServers",
            upsert={key: spec_to_config_entry(normalized)},
        )
    return tools, normalized


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
    return agents


def _make_tool_caller(tool_name: str, spec: Mapping[str, Any]) -> Callable[..., Any]:
    body = dict(spec)

    async def _call(**kwargs: Any) -> Any:
        live = _with_openapi_runtime_env(_expand_placeholders(body))
        if _kind_of(live) == KIND_REMOTE:
            from mcp import ClientSession
            from mcp.client.sse import sse_client

            headers = live.get("headers") if isinstance(live.get("headers"), dict) else None
            async with (
                sse_client(str(live.get("url") or ""), headers=headers, timeout=15.0) as (read, write),
                ClientSession(read, write) as session,
            ):
                await session.initialize()
                return await session.call_tool(tool_name, kwargs)
        from swarm.extensions.mcp.mcp_client import MCPClient

        client = MCPClient(
            {
                "command": live.get("command"),
                "args": list(live.get("args") or []),
                "env": live.get("env") or {},
            },
            timeout=15,
        )
        fn = client._create_tool_callable(tool_name)
        return await fn(**kwargs)

    return _call


def _tools_from_server(name: str, spec: Mapping[str, Any]) -> list[Any]:
    from swarm.types import Tool

    metas = spec.get("discovered_tools")
    if not isinstance(metas, list) or not metas:
        metas = [{"name": cap, "description": str(spec.get("note") or "")} for cap in _str_list(spec.get("provides"))]
    tools: list[Any] = []
    for item in metas:
        if isinstance(item, dict):
            tool_name = str(item.get("name") or "").strip()
            description = str(item.get("description") or "").strip()
        else:
            tool_name = str(item).strip()
            description = ""
        if not tool_name:
            continue
        tools.append(
            Tool(
                name=tool_name,
                description=description or f"{name} MCP tool",
                func=_make_tool_caller(tool_name, spec),
                dynamic=True,
            )
        )
    return tools


def tools_from_server(name: str, spec: Mapping[str, Any]) -> list[Any]:
    """Public wrapper used by per-agent MCP modes (#142)."""
    return _tools_from_server(name, spec)


def call_plugin_mcp_tool(
    tool_name: str,
    spec: Mapping[str, Any],
    arguments: Mapping[str, Any] | None = None,
) -> Any:
    """Execute one MCP tool against ``spec``. Sync; tests inject mocks instead."""
    fn = _make_tool_caller(tool_name, spec)
    return _run_async(fn(**dict(arguments or {})))


def attach_plugin_mcp_tools(blueprint: Any, config: Mapping[str, Any] | None) -> list[str]:
    """Attach tools from enabled MCP servers. Disabled / missing servers add nothing."""
    attached: list[str] = []
    servers = enabled_mcp_servers(config)
    extras = {name: load_mcp_servers(config).get(name, {}) for name in servers}
    for name, spec in servers.items():
        merged = {**extras.get(name, {}), **spec}
        tools = _tools_from_server(name, merged)
        if not tools:
            continue
        for agent in _iter_agents(blueprint):
            names = getattr(agent, "mcp_servers", None)
            if isinstance(names, list) and name not in names:
                names.append(name)
            elif names is None:
                with suppress(Exception):
                    agent.mcp_servers = [name]
            for attr in ("functions", "tools"):
                current = getattr(agent, attr, None)
                if not isinstance(current, list):
                    continue
                have = {getattr(fn, "name", None) or getattr(fn, "__name__", None) for fn in current}
                for tool in tools:
                    if tool.name not in have:
                        current.append(tool)
                        have.add(tool.name)
                        attached.append(tool.name)
    return attached


def apply_plugin_mcp_runtime(
    blueprint: Any,
    config: Mapping[str, Any] | None,
    enabled_tools: Iterable[Any] | None,
) -> None:
    """Attach enabled-server tools, then apply the per-chat allowlist (#805)."""
    attach_plugin_mcp_tools(blueprint, config)
    apply_chat_plugin_allowlist(
        blueprint,
        enabled_tools,
        catalog_ids=plugin_catalog_ids(config),
    )


def swarm_config() -> dict[str, Any]:
    try:
        from django.apps import apps

        cfg = getattr(apps.get_app_config("swarm"), "config", None)
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        logger.debug("swarm AppConfig.config unavailable", exc_info=True)
    try:
        from swarm.core.server_config import load_server_config

        loaded = load_server_config()
        return loaded if isinstance(loaded, dict) else {}
    except Exception:
        return {}

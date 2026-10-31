"""Integration layer between BlueprintMCPProvider and django-mcp-server.

This remains import-guarded and safe when the MCP server package is absent.
Supports both django-mcp-server >=0.5.0 (add_tool) and legacy (registry.register_tool).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Callable
from typing import Any

from .provider import BlueprintMCPProvider

logger = logging.getLogger(__name__)


def register_blueprints_with_mcp() -> int:
    """Register discovered blueprints as MCP tools.

    Supports both django-mcp-server >=0.5.0 (via ``mcp_server.mcp_server.add_tool``)
    and legacy versions (via ``mcp_server.registry.register_tool``).

    Returns the number of tools registered. If the MCP server module is missing
    or no supported registration API is found, logs an error and returns 0 without raising.
    """
    try:
        import mcp_server
    except Exception as exc:
        logger.error(
            "MCP blueprint→tool bridge unavailable: cannot import "
            "mcp_server (%s). Install django-mcp-server with `pip install .[mcp]` "
            "— blueprints are NOT MCP tools until installed "
            "(docs/mcp_server_mode.md, ROADMAP §3.3).",
            exc,
        )
        return 0

    server = getattr(mcp_server, "mcp_server", None)
    registry = getattr(mcp_server, "registry", None)
    if registry is None:
        try:
            from mcp_server import registry as _reg  # type: ignore

            registry = _reg
        except Exception:
            registry = None

    has_add_tool = server is not None and hasattr(server, "add_tool")
    has_register_tool = registry is not None and hasattr(registry, "register_tool")

    if not has_add_tool and not has_register_tool:
        logger.error(
            "MCP blueprint→tool bridge no-op: mcp_server has neither "
            "mcp_server.add_tool nor registry.register_tool — blueprints are "
            "NOT MCP tools (docs/mcp_server_mode.md, ROADMAP §3.3)."
        )
        return 0

    provider = BlueprintMCPProvider()
    count = 0
    for tool in provider.list_tools():
        name = tool.get("name")
        if not name:
            continue
        parameters = tool.get("parameters")
        description = tool.get("description") or f"Blueprint {name}"

        try:
            if has_add_tool:
                def make_tool_fn(b_name: str, doc_str: str):
                    def blueprint_tool(instruction: str) -> str:
                        res = provider.call_tool(b_name, {"instruction": instruction})
                        if isinstance(res, dict):
                            return res.get("content", str(res))
                        return str(res)

                    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", b_name)
                    blueprint_tool.__name__ = f"tool_{sanitized}"
                    blueprint_tool.__doc__ = doc_str
                    return blueprint_tool

                fn = make_tool_fn(name, description)
                server.add_tool(fn, name=name, description=description)
                count += 1
            elif has_register_tool:
                def make_handler(n: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
                    def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
                        return provider.call_tool(n, arguments)

                    return _handler

                registry.register_tool(
                    name=name,
                    parameters=parameters,
                    description=description,
                    handler=make_handler(name),
                )
                count += 1
        except Exception:
            logger.error(
                "Failed to register blueprint %r as MCP tool",
                name,
                exc_info=True,
            )
            continue

    if count == 0:
        logger.error(
            "MCP blueprint→tool bridge registered 0 tools. ENABLE_MCP_SERVER "
            "may still mount /mcp/, but blueprints are NOT exposed as MCP tools "
            "(docs/mcp_server_mode.md, ROADMAP §3.3)."
        )
    else:
        logger.info("Registered %d blueprint(s) as MCP tools", count)

    return count

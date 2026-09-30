"""Integration layer between BlueprintMCPProvider and django-mcp-server.

This remains import-guarded and safe when the MCP server package is absent.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from .provider import BlueprintMCPProvider

logger = logging.getLogger(__name__)


def register_blueprints_with_mcp() -> int:
    """Register discovered blueprints as MCP tools.

    Returns the number of tools registered. If the MCP server module is missing
    or the flat ``registry.register_tool`` API is absent (``mcp_server`` ≥0.5),
    logs at ERROR and returns 0 without raising.

    NOTE (2026-06-19): `django-mcp-server` (module `mcp_server`) ≥0.5 exposes an
    ``MCPToolset`` / decorator API, NOT the flat ``registry.register_tool(...)``
    this was written against — so this bridge is a **no-op** today and needs
    porting to the toolset paradigm (tracked in ROADMAP §3.3). ``ENABLE_MCP_SERVER``
    still mounts ``/mcp/`` via ``mcp_server.urls`` once the package is installed;
    that mount does **not** expose Operating Swarm blueprints as tools until this
    bridge is ported.
    """
    try:
        # Legacy/expected flat registry API — absent in mcp_server >=0.5 (see note).
        from mcp_server import registry  # type: ignore
    except Exception as exc:
        logger.error(
            "MCP blueprint→tool bridge unavailable: cannot import "
            "mcp_server.registry (%s). mcp_server≥0.5 replaced flat "
            "registry.register_tool with MCPToolset — ENABLE_MCP_SERVER mounts "
            "/mcp/ but blueprints are NOT MCP tools until the bridge is ported "
            "(docs/mcp_server_mode.md, ROADMAP §3.3).",
            exc,
        )
        return 0

    if not hasattr(registry, "register_tool"):
        logger.error(
            "MCP blueprint→tool bridge no-op: mcp_server.registry has no "
            "register_tool (mcp_server≥0.5 MCPToolset API). ENABLE_MCP_SERVER "
            "mounts /mcp/ but blueprints are NOT MCP tools until the bridge is "
            "ported (docs/mcp_server_mode.md, ROADMAP §3.3)."
        )
        return 0

    provider = BlueprintMCPProvider()
    count = 0
    for tool in provider.list_tools():
        name = tool.get("name")
        parameters = tool.get("parameters")
        description = tool.get("description")

        def make_handler(n: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
            def _handler(arguments: dict[str, Any]) -> dict[str, Any]:
                return provider.call_tool(n, arguments)

            return _handler

        try:
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

    return count

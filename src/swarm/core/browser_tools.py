"""Browser automation honesty helpers.

Operating Swarm provisions the official microsoft/playwright-mcp server for blueprints
that declare a ``browser`` capability (see :mod:`swarm.core.tool_capabilities`).
There is no built-in stub that fakes successful navigation: when Playwright MCP
is not running or not reachable, callers should surface a clear structured error
instead of pretending the page load succeeded.

Usage::

    from swarm.core.browser_tools import browser_unavailable_error, BROWSER_UNAVAILABLE

    if not playwright_mcp_ready:
        return browser_unavailable_error(detail="npx @playwright/mcp failed to start")
"""
from __future__ import annotations

from typing import Any

BROWSER_UNAVAILABLE = "browser automation unavailable: no playwright MCP server"


def browser_unavailable_error(detail: str | None = None) -> dict[str, Any]:
    """Structured error for missing/unreachable Playwright MCP.

    Call sites (tool handlers, blueprint minions, MCP bridges) should return this
    dict rather than a synthetic success payload when browser automation cannot
    run.
    """
    out: dict[str, Any] = {
        "ok": False,
        "error": BROWSER_UNAVAILABLE,
    }
    if detail:
        out["detail"] = detail
    return out


def is_browser_unavailable_payload(payload: Any) -> bool:
    """True if *payload* looks like a :func:`browser_unavailable_error` result."""
    return (
        isinstance(payload, dict)
        and payload.get("ok") is False
        and payload.get("error") == BROWSER_UNAVAILABLE
    )

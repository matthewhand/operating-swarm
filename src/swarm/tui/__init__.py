"""REQ-111: os-cli TUI (API client, not a second runtime).

Interactive Textual chrome is a Wave 1 extra. This package lists rail seats
over the same REST the WebUI uses and renders a placeholder two-pane dump.
"""

from swarm.tui.client import (
    DEFAULT_BASE_URL,
    RailSeat,
    SwarmApiError,
    list_rail_agents,
    resolve_base_url,
    resolve_token,
)
from swarm.tui.layout import render_scaffold

__all__ = [
    "DEFAULT_BASE_URL",
    "RailSeat",
    "SwarmApiError",
    "list_rail_agents",
    "render_scaffold",
    "resolve_base_url",
    "resolve_token",
]

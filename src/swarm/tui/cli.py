"""``os-cli tui`` — REQ-111: Textual chrome with a --once CI dump."""

from __future__ import annotations

import json
import sys

import typer

from swarm.tui.client import (
    DEFAULT_BASE_URL,
    RailSeat,
    SwarmApiError,
    list_rail_agents,
    resolve_base_url,
    resolve_token,
    sectioned_seats,
)
from swarm.tui.layout import render_scaffold


def tui_cmd(
    once: bool = typer.Option(
        False,
        "--once/--interactive",
        help="Interactive Textual chrome (default, needs a terminal). "
        "--once dumps the ASCII rail + placeholder pane for CI.",
    ),
    base_url: str | None = typer.Option(
        None,
        "--base-url",
        help="swarm-api origin. Default: SWARM_API_BASE or http://127.0.0.1:8000.",
    ),
    agent: str | None = typer.Option(
        None,
        "--agent",
        help="Rail seat id to mark selected (must exist in the API list).",
    ),
    as_json: bool = typer.Option(
        False,
        "--json",
        help="Print the rail list as JSON instead of the ASCII chrome.",
    ),
) -> None:
    """Herdr-like TUI client of the same HTTP API the WebUI uses (REQ-111).

    Auth/base contract (env-var **names** only): SWARM_API_BASE for the origin,
    API_AUTH_TOKEN or SWARM_API_KEY for the Bearer token. 401/403 and API-down
    failures are named; no agents are invented when the API is down or empty.
    """
    if once or as_json:
        _non_interactive(as_json=as_json, base_url=base_url, agent=agent)
        return
    _interactive(base_url=base_url, agent=agent)


def _fetch_seats(base_url: str) -> list[RailSeat]:
    try:
        return list_rail_agents(base_url=base_url)
    except SwarmApiError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc


def _selected_seat_id(seats: list[RailSeat], agent: str | None) -> str | None:
    """Resolve ``--agent`` to a rail id. Unknown ids are an error, not a fallback."""
    if agent is None:
        return seats[0].id if seats else None
    for seat in seats:
        if seat.id == agent:
            return seat.id
    typer.echo(f"Unknown --agent {agent!r}: not in the rail.", err=True)
    raise typer.Exit(code=1)


def _interactive(*, base_url: str | None, agent: str | None) -> None:
    if not sys.stdout.isatty():
        typer.echo(
            "Interactive TUI needs a terminal. Use --once for the ASCII dump (CI).",
            err=True,
        )
        raise typer.Exit(code=2)
    # Guard only the optional dependency so a genuine bug inside swarm.tui.app
    # (bad import, missing symbol) still surfaces instead of masquerading as an
    # install hint.
    try:
        import textual  # noqa: F401
    except ImportError:
        typer.echo(
            "Interactive TUI needs the optional [tui] extra: "
            "install with `pip install -e '.[tui]'` or `uv sync --all-extras`.",
            err=True,
        )
        raise typer.Exit(code=2) from None
    from swarm.tui.app import run_tui_app

    resolved = resolve_base_url(base_url)
    seats = _fetch_seats(resolved)
    run_tui_app(seats, base_url=resolved, selected_id=_selected_seat_id(seats, agent))


def _non_interactive(
    *,
    as_json: bool,
    base_url: str | None,
    agent: str | None,
) -> None:
    resolved = resolve_base_url(base_url)
    seats = _fetch_seats(resolved)
    selected = _selected_seat_id(seats, agent)

    if as_json:
        payload = {
            "object": "tui.rail",
            "base_url": resolved,
            # Bearer is attached for /v1/* listing. GET /chat/thread/ is
            # login-gated; TUI v1 has no cookie jar (Wave 3b skipped).
            "auth": {
                "bearer": resolve_token() is not None,
                "chat": False,
            },
            "selected": selected,
            "data": [
                {
                    "id": seat.id,
                    "name": seat.name,
                    "kind": seat.kind,
                    "source": seat.source,
                }
                for seat in seats
            ],
            # Wave 1b: kind sections CLI / API / Blueprint / Remote (empty omitted).
            "sections": {
                label: [s.id for s in group]
                for label, group in sectioned_seats(seats)
            },
        }
        typer.echo(json.dumps(payload, indent=2))
        return

    typer.echo(render_scaffold(seats, selected_id=selected, base_url=resolved), nl=False)


def register_tui(app: typer.Typer) -> None:
    app.command(name="tui")(tui_cmd)
    app.command(name="chat")(tui_cmd)


# Re-export default for tests that assert we never bake :8001.
__all__ = ["DEFAULT_BASE_URL", "register_tui", "tui_cmd"]

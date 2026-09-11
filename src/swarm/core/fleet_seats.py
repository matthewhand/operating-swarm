"""Named fleet seats: agent id → matching tool → assigned project (Issue #162).

Mirrors Grok Bot / CLI-proxy fleet shape inside open-swarm instead of
parallel poly-seats. Reuses ``agent_settings`` folder binding and
``software_dev`` local workspace confinement. Deterministic invoke — no
LLM, no LiteLLM catalog, no secrets.

Seat id is either a fleet pattern ``<proj>-<cli>`` (e.g. ``openswarm-grok``)
or a software_dev talk-to short name (``cos`` / ``engineer`` / ``skeptic``).
The named tool string equals ``agent_id``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from swarm.core.agent_lifecycle import looks_like_secret, refuse_secrets, slugify_agent_id
from swarm.core.agent_settings import set_folder, stored_folder
from swarm.core.paths import ensure_swarm_directories_exist, get_user_config_dir_for_swarm
from swarm.blueprints.software_dev.workspace import LocalWorkspaceBackend, confine_local

logger = logging.getLogger(__name__)

SCHEMA = 1
ENV_SEATS_PATH = "SWARM_FLEET_SEATS_PATH"
PASS_MARKER = "_fleet_seat_pass.txt"

# Talk-to short names already used by software_dev (Issue #162 Success 1).
SHORT_SEATS: frozenset[str] = frozenset(
    {"cos", "engineer", "skeptic", "coding-requirements-gate"}
)

# ``<proj>-<cli>`` — both sides start with a letter; hyphens inside allowed via slug.
_FLEET_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}-[a-z][a-z0-9_]{0,31}$")

_cache: dict[str, Any] | None = None


class FleetSeatError(ValueError):
    """Invalid fleet seat id, workdir, or invoke."""


def seats_path() -> Path:
    env = (os.environ.get(ENV_SEATS_PATH) or "").strip()
    if env:
        return Path(env)
    ensure_swarm_directories_exist()
    return get_user_config_dir_for_swarm() / "fleet_seats.json"


def reset_fleet_seats_cache() -> None:
    global _cache
    _cache = None


def _empty_store() -> dict[str, Any]:
    return {"schema": SCHEMA, "seats": {}}


def _read_store() -> dict[str, Any]:
    global _cache
    if _cache is not None:
        return _cache
    path = seats_path()
    if not path.is_file():
        _cache = _empty_store()
        return _cache
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.debug("fleet_seats store unreadable: %s", path)
        _cache = _empty_store()
        return _cache
    seats = raw.get("seats") if isinstance(raw, dict) else None
    if not isinstance(seats, dict):
        seats = {}
    _cache = {"schema": SCHEMA, "seats": dict(seats)}
    return _cache


def _write_store(store: dict[str, Any]) -> None:
    global _cache
    path = seats_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps({"schema": SCHEMA, "seats": store.get("seats") or {}}, indent=2)
    fd, tmp = tempfile.mkstemp(prefix="fleet_seats.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    _cache = {"schema": SCHEMA, "seats": dict(store.get("seats") or {})}


def normalize_seat_id(value: Any) -> str:
    ident = slugify_agent_id(value)
    return ident


def is_fleet_seat_id(ident: str) -> bool:
    text = (ident or "").strip().lower()
    if text in SHORT_SEATS:
        return True
    return bool(_FLEET_ID.match(text))


def tool_name_for(agent_id: str) -> str:
    """Named tool string — equals the seat id (Success 2)."""
    return (agent_id or "").strip()


def _public(row: dict[str, Any]) -> dict[str, Any]:
    ident = str(row.get("agent_id") or "")
    workdir = str(row.get("workdir") or "")
    return {
        "agent_id": ident,
        "display": str(row.get("display") or ident),
        "tool_name": str(row.get("tool_name") or tool_name_for(ident)),
        "workdir": workdir,
        "role": str(row.get("role") or ""),
    }


def create_seat(
    name: str,
    workdir: str | os.PathLike[str],
    *,
    display: str | None = None,
    role: str = "",
) -> dict[str, Any]:
    """Create (or replace) a named seat bound to ``workdir``."""
    refuse_secrets(name, display, role, str(workdir))
    ident = normalize_seat_id(name)
    if not ident or not is_fleet_seat_id(ident):
        raise FleetSeatError(
            "seat id must match <proj>-<cli> (e.g. openswarm-grok) or a "
            "software_dev short name (cos, engineer, skeptic)."
        )
    if looks_like_secret(ident):
        raise FleetSeatError("seat id looks like a secret.")
    root = Path(str(workdir)).expanduser()
    if not root.is_absolute():
        root = Path.cwd() / root
    root.mkdir(parents=True, exist_ok=True)
    bound = str(root.resolve())
    set_folder(ident, bound)
    row = {
        "agent_id": ident,
        "display": (display or name or ident).strip() or ident,
        "tool_name": tool_name_for(ident),
        "workdir": bound,
        "role": (role or "").strip(),
    }
    store = _read_store()
    seats = dict(store.get("seats") or {})
    seats[ident] = row
    _write_store({"schema": SCHEMA, "seats": seats})
    return _public(row)


def list_seats() -> list[dict[str, Any]]:
    store = _read_store()
    seats = store.get("seats") or {}
    rows = [_public(dict(row, agent_id=ident)) for ident, row in seats.items() if isinstance(row, dict)]
    return sorted(rows, key=lambda item: item["agent_id"])


def get_seat(agent_id: str) -> dict[str, Any] | None:
    ident = normalize_seat_id(agent_id)
    store = _read_store()
    raw = (store.get("seats") or {}).get(ident)
    if not isinstance(raw, dict):
        return None
    return _public(dict(raw, agent_id=ident))


def bound_workdir(agent_id: str) -> str | None:
    seat = get_seat(agent_id)
    if seat and seat.get("workdir"):
        return str(seat["workdir"])
    folder = stored_folder(agent_id)
    return folder


def invoke_named_tool(
    agent_id: str,
    *,
    path: str = PASS_MARKER,
    content: str | None = None,
) -> dict[str, Any]:
    """Run the seat's named tool against its assigned project only.

    Writes a short PASS marker (or ``content``) under the bound workdir.
    Paths that escape the binding are refused.
    """
    ident = normalize_seat_id(agent_id)
    seat = get_seat(ident)
    if seat is None:
        raise FleetSeatError(f"unknown fleet seat: {ident}")
    tool = seat["tool_name"]
    if tool != ident:
        raise FleetSeatError(f"tool name {tool!r} does not match agent {ident!r}")
    root = Path(seat["workdir"])
    rel = (path or PASS_MARKER).strip() or PASS_MARKER
    target = confine_local(root, rel)
    if target is None:
        return {
            "ok": False,
            "error": "workdir_escape",
            "agent_id": ident,
            "tool_name": tool,
            "message": f"path escapes assigned project: {rel}",
        }
    body = content if content is not None else f"PASS {ident} tool={tool} workdir={root}\n"
    refuse_secrets(body)
    backend = LocalWorkspaceBackend(root)
    written = backend.write_file(rel, body)
    if written.startswith("ERROR:"):
        return {
            "ok": False,
            "error": "write_failed",
            "agent_id": ident,
            "tool_name": tool,
            "message": written,
        }
    return {
        "ok": True,
        "agent_id": ident,
        "display": seat["display"],
        "tool_name": tool,
        "workdir": str(root),
        "path": rel,
        "result": written,
        "evidence": body.strip().splitlines()[0] if body.strip() else "PASS",
    }


def named_tools() -> list[str]:
    return [row["tool_name"] for row in list_seats()]


def as_callables() -> list[Any]:
    """One callable per seat; ``fn.name`` equals the agent id."""
    tools: list[Any] = []
    for row in list_seats():
        ident = row["agent_id"]

        def _invoke(path: str = PASS_MARKER, content: str = "", *, _id: str = ident) -> dict[str, Any]:
            return invoke_named_tool(_id, path=path, content=content or None)

        _invoke.__name__ = ident.replace("-", "_")
        _invoke.name = ident  # type: ignore[attr-defined]
        _invoke.description = (  # type: ignore[attr-defined]
            f"Named tool for seat {ident}; writes only under its assigned project."
        )
        tools.append(_invoke)
    return tools

"""#1728 / #1729 — one normalized Herdr status vocabulary, one mapping rule.

Herdr's own lifecycle enum is four values, and it is published in the CLI's
own API schema (``herdr api schema --json`` → ``event.$defs.AgentStatus``):

    idle | working | blocked | done

Operating Swarm never invents a parallel vocabulary. It renames exactly two of
them for the UI and leaves the rest verbatim:

| Herdr ``agent_status`` | OS seat status   | Meaning in the rail          |
|---|---|---|
| ``working``            | ``working``      | busy — not silent (#1729 §4)  |
| ``blocked``            | ``waiting``      | a human question is pending  |
| ``done``               | ``finished``     | the turn ended with output   |
| ``idle``               | ``idle``         | nothing running              |
| *anything else/absent* | ``unknown``      | no positive evidence         |

``unknown`` is the **default**, not a fallback for a failure. A Herdr that is
down, slow, or missing from the payload must never be reported as ``idle`` —
that reads as "nothing is happening" when the truth is "we do not know". Every
consumer of Herdr status (the REST surface, the status watcher, the SPA
store) calls :func:`normalize_agent_status`, so the mapping can never drift into
a second divergent copy.

This module is deliberately dependency-free and has no Django import, so it is
safe to use from the CLI wrapper, the ORM-backed watcher, and tests alike.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

#: The four OS-facing seat states. ``unknown`` is the honest default.
HerdrSeatStatus = Literal["unknown", "idle", "working", "waiting", "finished"]

UNKNOWN_STATUS: HerdrSeatStatus = "unknown"

SEAT_STATUSES: tuple[HerdrSeatStatus, ...] = (
    "unknown",
    "idle",
    "working",
    "waiting",
    "finished",
)

#: Herdr's own enum, copied from the CLI's bundled API schema. Used for
#: documentation and for rejecting unknown states in ``--until`` style calls.
HERDR_AGENT_STATUSES: tuple[str, ...] = ("idle", "working", "blocked", "done")

#: ``agent_status`` value → OS seat status. The *only* mapping table.
SEAT_STATUS_FOR_HERDR: dict[str, HerdrSeatStatus] = {
    "idle": "idle",
    "working": "working",
    "blocked": "waiting",
    "done": "finished",
}

#: The inverse, for echoing what OS derived a row from. Derived from the one
#: table above — a second hand-written copy is how a mapping drifts.
HERDR_STATUS_FOR_SEAT: dict[HerdrSeatStatus, str] = {
    seat: raw for raw, seat in SEAT_STATUS_FOR_HERDR.items()
}

_STATUS_MAP = SEAT_STATUS_FOR_HERDR


def normalize_agent_status(raw: Any) -> HerdrSeatStatus:
    """Map one Herdr ``agent_status`` value onto an OS seat status.

    Accepts the raw CLI field, a whole agent record, or ``None``. Anything not
    in Herdr's published enum becomes ``unknown`` — a status OS cannot vouch
    for is never upgraded into a positive label.
    """
    value: Any = raw
    if isinstance(raw, Mapping):
        value = _record_status(raw)
    if isinstance(value, bool) or value is None:
        return UNKNOWN_STATUS
    if not isinstance(value, str):
        return UNKNOWN_STATUS
    return _STATUS_MAP.get(value.strip().lower(), UNKNOWN_STATUS)


def _record_status(record: Mapping[str, Any]) -> Any:
    """Pull ``agent_status`` (or a loose alias) out of one agent record."""
    for key in ("agent_status", "status", "state", "agent_state"):
        if key in record:
            value = record[key]
            # A nested ``{"agent": {...}}`` wrapper (agent get) recurses once.
            if isinstance(value, Mapping):
                return _record_status(value)
            return value
    for wrap in ("result", "agent", "data", "pane"):
        inner = record.get(wrap)
        if isinstance(inner, Mapping) and inner is not record:
            return _record_status(inner)
    return None


def pane_id_of(record: Any) -> str:
    """The routing target for one agent record (``w3:p1``), or ``""``.

    Wrappers are unwrapped **before** this level's own keys are read. The CLI
    answers ``{"id": "cli:agent:get", "result": {"agent": {...}}}``, so a
    flat key scan first would return the envelope's request id and route the
    status to a pane that does not exist.
    """
    if not isinstance(record, Mapping):
        return ""
    for wrap in ("result", "snapshot", "agent", "data", "pane"):
        inner = record.get(wrap)
        if isinstance(inner, (Mapping, list)) and inner is not record:
            found = pane_id_of(inner)
            if found:
                return found
    for key in ("pane_id", "pane", "target", "name", "id"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _iter_agent_records(payload: Any) -> Iterable[Mapping[str, Any]]:
    """Yield agent records from ``agent list`` / ``api snapshot`` JSON.

    Both shapes are unwrapped here so callers never re-implement the walk:
    ``{"result": {"agents": [...]}}`` (agent list) and
    ``{"result": {"snapshot": {"agents": [...]}}}`` (api snapshot).
    """
    seen: set[int] = set()

    def walk(node: Any, depth: int = 0) -> Iterable[Mapping[str, Any]]:
        if depth > 6 or not isinstance(node, (Mapping, list)):
            return
        if id(node) in seen:
            return
        seen.add(id(node))
        if isinstance(node, list):
            for item in node:
                if isinstance(item, Mapping):
                    yield item
                else:
                    yield from walk(item, depth + 1)
            return
        for key in ("agents", "items"):
            value = node.get(key)
            if isinstance(value, list):
                yield from walk(value, depth + 1)
                return
        for wrap in ("result", "snapshot", "data"):
            inner = node.get(wrap)
            if inner is not node:
                yield from walk(inner, depth + 1)

    yield from walk(payload)


class HerdrPaneStatus:
    """One pane's normalized status, as returned by the query surfaces."""

    __slots__ = ("target", "status", "state_change_seq", "agent", "workspace_id")

    def __init__(
        self,
        target: str,
        status: HerdrSeatStatus,
        *,
        state_change_seq: int | None = None,
        agent: str = "",
        workspace_id: str = "",
    ) -> None:
        self.target = target
        self.status = status
        self.state_change_seq = state_change_seq
        self.agent = agent
        self.workspace_id = workspace_id

    def as_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "status": self.status,
            # Herdr's own value, so a client can show what OS derived it from.
            "herdr_status": HERDR_STATUS_FOR_SEAT.get(self.status, ""),
            "state_change_seq": self.state_change_seq,
            "agent": self.agent,
            "workspace_id": self.workspace_id,
        }

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"HerdrPaneStatus({self.target!r}, {self.status!r})"


def extract_state_change_seq(record: Any) -> int | None:
    """``state_change_seq`` from one agent record, or ``None``.

    Herdr bumps this counter whenever a pane changes state, so it is the only
    ordering signal available for "did this update arrive late?". Reused here
    rather than re-parsed: the same reader already serves the session watcher.
    """
    if isinstance(record, list):
        for item in record:
            found = extract_state_change_seq(item)
            if found is not None:
                return found
        return None
    if not isinstance(record, Mapping):
        return None
    raw = record.get("state_change_seq")
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.strip().lstrip("-").isdigit():
        return int(raw.strip())
    return None


def pane_statuses(payload: Any) -> list[HerdrPaneStatus]:
    """Every pane's normalized status from one CLI payload.

    One ``herdr agent list`` (or ``herdr api snapshot``) call answers for the
    whole workspace, so this is O(panes) in one process — not one CLI call per
    pane. A pane Herdr reports with no recognizable status still appears, as
    ``unknown``: absent evidence is a state we report, not a pane we hide.
    """
    rows: list[HerdrPaneStatus] = []
    seen: set[str] = set()
    for record in _iter_agent_records(payload):
        target = pane_id_of(record)
        if not target or target in seen:
            continue
        seen.add(target)
        agent = record.get("agent")
        workspace = record.get("workspace_id")
        rows.append(
            HerdrPaneStatus(
                target,
                normalize_agent_status(record),
                state_change_seq=extract_state_change_seq(record),
                agent=agent.strip() if isinstance(agent, str) else "",
                workspace_id=workspace.strip() if isinstance(workspace, str) else "",
            )
        )
    return rows


def statuses_by_target(payload: Any) -> dict[str, HerdrSeatStatus]:
    """``pane id → status`` for the panes a payload mentions."""
    return {row.target: row.status for row in pane_statuses(payload)}


__all__ = [
    "HERDR_AGENT_STATUSES",
    "HERDR_STATUS_FOR_SEAT",
    "SEAT_STATUSES",
    "SEAT_STATUS_FOR_HERDR",
    "UNKNOWN_STATUS",
    "HerdrPaneStatus",
    "HerdrSeatStatus",
    "extract_state_change_seq",
    "normalize_agent_status",
    "pane_id_of",
    "pane_statuses",
    "statuses_by_target",
]

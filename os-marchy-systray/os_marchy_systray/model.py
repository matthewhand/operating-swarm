"""Normalize the OS API payloads into a tray view model.

Agents are grouped by **rig**:

* ``team`` — a *static* rig: one entry per ``/v1/team-rosters/`` roster, with
  its members placed underneath it.
* ``section`` — a *dynamic* rig: operator sections (passed in explicitly) and
  configured ``/v1/remotes/`` harnesses (their member agents).
* ``unassigned`` — anything no rig claims.

Status uses the same signals the SPA rail reads: an explicit
``status``/``state`` of ``running``/``working``/``error``/``offline``, a
``working: true`` flag (remotes), or an ``error`` field. A seat with none of
those is honestly ``idle`` — the thin client never invents liveness.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote

KIND_BADGES: dict[str, str] = {
    "cli": "CLI",
    "api": "API",
    "remote": "Remote",
    "remote_agent": "Remote",
    "team": "Team",
    "blueprint": "Blueprint",
    "design": "Design",
    "herdr": "Herdr",
    "section": "Section",
    "unassigned": "Unassigned",
    "unknown": "Agent",
}

STATUS_GLYPHS: dict[str, str] = {
    "working": "▶",
    "waiting": "…",
    "idle": "○",
    "error": "✕",
    "offline": "—",
}

_WORKING = {"working", "running", "busy", "active", "streaming", "executing", "in_progress", "in-progress"}
_ERROR = {"error", "failed", "failure", "crash", "crashed", "exception"}
_OFFLINE = {"offline", "down", "unreachable", "disconnected", "unhealthy"}
_WAITING = {"waiting", "blocked", "approval", "paused"}
_IDLE = {
    "idle", "ready", "finished", "done", "complete", "completed",
    "stopped", "online", "ok", "success", "healthy", "up",
}
_OBJECT_KIND = {
    "cli.agent": "cli",
    "blueprint": "blueprint",
    "team_roster": "team",
    "team": "team",
    "remote": "remote",
    "design": "design",
}
_KNOWN_KINDS = {"api", "cli", "remote", "team", "blueprint", "design", "herdr"}


@dataclass
class AgentView:
    """One seat/agent as the tray renders it."""

    id: str
    name: str
    kind: str
    badge: str
    status: str
    status_glyph: str
    rig_id: str
    rig_name: str
    chat_url: str
    description: str = ""
    icon: str = ""
    color: str = ""
    cli: str = ""
    role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "badge": self.badge,
            "status": self.status,
            "rig_id": self.rig_id,
            "chat_url": self.chat_url,
        }


@dataclass
class RigView:
    """A group of agents: a static team, a dynamic section, or unassigned."""

    id: str
    name: str
    kind: str  # team | section | unassigned
    agents: list[AgentView] = field(default_factory=list)
    source: str = ""

    @property
    def count(self) -> int:
        return len(self.agents)

    @property
    def is_static(self) -> bool:
        return self.kind == "team"

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for agent in self.agents:
            counts[agent.status] = counts.get(agent.status, 0) + 1
        return counts


@dataclass
class SwarmView:
    """The whole grouped view for one connected instance."""

    base_url: str = ""
    rigs: list[RigView] = field(default_factory=list)
    connection: str = "unknown"
    version: str | None = None

    @property
    def named_rigs(self) -> list[RigView]:
        return [rig for rig in self.rigs if rig.kind != "unassigned"]

    @property
    def unassigned(self) -> RigView | None:
        for rig in self.rigs:
            if rig.kind == "unassigned":
                return rig
        return None

    @property
    def agent_count(self) -> int:
        return sum(rig.count for rig in self.rigs)

    def all_agents(self) -> list[AgentView]:
        return [agent for rig in self.rigs for agent in rig.agents]

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for agent in self.all_agents():
            counts[agent.status] = counts.get(agent.status, 0) + 1
        return counts

    def rig_named(self, rig_id: str) -> RigView | None:
        for rig in self.rigs:
            if rig.id == rig_id:
                return rig
        return None


# ---------------------------------------------------------------------------
# Primitive derivations
# ---------------------------------------------------------------------------
def kind_of(row: Mapping[str, Any] | None) -> str:
    """Resolve a seat's kind from ``kind``/``agent_type``/``object``."""
    row = row or {}
    for key in ("kind", "agent_type", "object"):
        raw = str(row.get(key) or "").strip().lower()
        if not raw:
            continue
        if raw in _KNOWN_KINDS:
            return raw
        if raw in _OBJECT_KIND:
            return _OBJECT_KIND[raw]
    return "unknown"


def kind_badge(kind: str) -> str:
    return KIND_BADGES.get((kind or "").lower(), (kind or "Agent").title())


def status_glyph(status: str) -> str:
    return STATUS_GLYPHS.get((status or "").lower(), STATUS_GLYPHS["idle"])


def status_from_row(row: Mapping[str, Any] | None) -> str:
    """Map the rail's working/idle/error signals onto a tray status."""
    row = row if isinstance(row, Mapping) else {}
    if row.get("error") or row.get("error_message") or row.get("last_error"):
        return "error"
    raw = str(row.get("status") or row.get("state") or "").strip().lower()
    if raw in _WORKING:
        return "working"
    if raw in _ERROR:
        return "error"
    if raw in _OFFLINE:
        return "offline"
    if raw in _WAITING:
        return "waiting"
    if raw in _IDLE:
        return "idle"
    if row.get("working") is True:
        return "working"
    if row.get("online") is False:
        return "offline"
    health = str(row.get("health") or "").strip().lower()
    if health in _OFFLINE:
        return "offline"
    return "idle"


def chat_url(
    kind: str,
    agent_id: str,
    *,
    base_url: str = "",
    remote_id: str | None = None,
    team_id: str | None = None,
    cli: str | None = None,
) -> str:
    """Build the deep link that opens an agent's chat on the connected OS.

    Mirrors the SPA rail's own destinations:
    ``/chat?blueprint=`` (blueprint/api/cli seats), ``/chat?team=`` (+
    ``&session=`` for a roster member), ``/chat?remote=`` (+ ``&session=``),
    and ``/chat?blueprint=cli_agent&cli=`` for the generic CLI seat.
    """
    kind = (kind or "").lower()
    agent_id = (agent_id or "").strip()
    if not agent_id:
        raise ValueError("agent_id is required")

    if kind == "remote":
        path = f"/chat?remote={quote(agent_id)}"
    elif kind == "remote_agent":
        path = f"/chat?remote={quote(remote_id or agent_id)}&session={quote(agent_id)}"
    elif kind == "team":
        path = f"/chat?team={quote(agent_id)}"
    elif team_id and team_id != agent_id:
        path = f"/chat?team={quote(team_id)}&session={quote(agent_id)}"
    elif kind == "cli" and agent_id == "cli_agent" and cli:
        path = f"/chat?blueprint=cli_agent&cli={quote(cli)}"
    else:
        path = f"/chat?blueprint={quote(agent_id)}"

    base = (base_url or "").strip().rstrip("/")
    return f"{base}{path}" if base else path


# ---------------------------------------------------------------------------
# Payload extraction
# ---------------------------------------------------------------------------
def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _agent_rows(agents_payload: Any) -> list[dict[str, Any]]:
    if isinstance(agents_payload, list):
        return [row for row in agents_payload if isinstance(row, dict)]
    payload = _as_dict(agents_payload)
    if isinstance(payload.get("agents"), list):
        return [row for row in payload["agents"] if isinstance(row, dict)]
    nested = _as_dict(payload.get("data"))
    if isinstance(nested.get("agents"), list):
        return [row for row in nested["agents"] if isinstance(row, dict)]
    return []


def _roster_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    return [row for row in _as_dict(payload).get("data", []) if isinstance(row, dict)]


def _names(rows: Any) -> list[str]:
    """Accept ``["grok"]`` or ``[{"name": "grok"}]``."""
    out: list[str] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, str):
            name = row.strip()
        elif isinstance(row, dict):
            name = str(row.get("name") or row.get("cli") or row.get("id") or "").strip()
        else:
            continue
        if name:
            out.append(name)
    return out


def _cli_seats(cli_payload: Any) -> list[dict[str, Any]]:
    payload = _as_dict(cli_payload)
    seats: list[dict[str, Any]] = []
    covered: set[str] = set()
    rail = payload.get("rail")
    if isinstance(rail, list):
        for row in rail:
            if not isinstance(row, dict):
                continue
            seats.append(row)
            for key in ("id", "name", "cli"):
                value = row.get(key)
                if isinstance(value, str) and value.strip():
                    covered.add(value.strip().lower())
    derived = _names(payload.get("discovered")) + _names(payload.get("configured"))
    for name in derived:
        if name.lower() in covered:
            continue
        covered.add(name.lower())
        seats.append(
            {
                "id": f"{name}_agent",
                "name": name.replace("_", " ").replace("-", " ").title(),
                "kind": "cli",
                "agent_type": "cli",
                "cli": name,
                "description": f"Host {name} CLI",
            }
        )
    return seats


def _is_rail_remote(remote: Mapping[str, Any]) -> bool:
    if remote.get("configured") is True or remote.get("added") is True:
        return True
    source = str(remote.get("source") or "").strip().lower()
    if source and source not in ("default", "catalog"):
        return True
    agents = remote.get("agents")
    return isinstance(agents, list) and len(agents) > 0


def _remote_rows(payload: Any) -> list[dict[str, Any]]:
    payload = _as_dict(payload)
    rows = payload.get("configured")
    if not isinstance(rows, list) or not rows:
        rows = payload.get("data")
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict) and _is_rail_remote(row)]


def _remote_title(remote: Mapping[str, Any], remote_id: str) -> str:
    for key in ("title", "label", "name"):
        value = str(remote.get(key) or "").strip()
        if value:
            return value
    return remote_id


def _seat_id(row: Mapping[str, Any]) -> str:
    for key in ("agent_id", "id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _seat_name(row: Mapping[str, Any], seat_id: str) -> str:
    for key in ("name", "title", "label"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return seat_id


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------
def build_view(
    *,
    base_url: str = "",
    agents_payload: Any = None,
    rosters_payload: Any = None,
    cli_payload: Any = None,
    remotes_payload: Any = None,
    sections: Sequence[Mapping[str, Any]] | None = None,
    connection: str = "unknown",
    version: str | None = None,
) -> SwarmView:
    """Fold the raw OS payloads into a grouped :class:`SwarmView`.

    ``/v1/teams/`` LLM-profile aliases are intentionally *not* groups: they
    carry no membership, so listing them as rigs would be misleading.
    """
    rigs: list[RigView] = []
    by_id: dict[str, RigView] = {}
    membership: dict[str, str] = {}

    def add_rig(rig_id: str, name: str, kind: str, source: str = "") -> RigView:
        rig = RigView(id=rig_id, name=name, kind=kind, source=source)
        rigs.append(rig)
        by_id[rig_id] = rig
        return rig

    # Static rigs: one per team roster.
    for roster in _roster_rows(rosters_payload):
        rid = str(roster.get("id") or "").strip()
        if not rid or rid in by_id:
            continue
        add_rig(rid, str(roster.get("name") or rid).strip() or rid, "team")
        for member in roster.get("members") or []:
            if not isinstance(member, dict):
                continue
            mid = str(member.get("id") or "").strip()
            if mid:
                membership.setdefault(mid, rid)

    # Dynamic rigs: operator sections.
    for section in sections or []:
        if not isinstance(section, Mapping):
            continue
        sid = str(section.get("id") or "").strip()
        if not sid or sid in by_id:
            continue
        add_rig(sid, str(section.get("name") or sid).strip() or sid, "section")
        for agent_id in section.get("agents") or []:
            membership.setdefault(str(agent_id).strip(), sid)

    # Dynamic rigs: configured remotes (section-like harnesses).
    remotes = _remote_rows(remotes_payload)
    remote_rig_ids: dict[str, str] = {}
    for remote in remotes:
        rid = str(remote.get("id") or "").strip()
        if not rid:
            continue
        rig_id = f"remote:{rid}"
        remote_rig_ids[rid] = rig_id
        if rig_id not in by_id:
            add_rig(rig_id, _remote_title(remote, rid), "section", source="remote")

    unassigned = RigView(id="unassigned", name="Unassigned", kind="unassigned")
    seen: set[str] = set()

    def place(seat: Mapping[str, Any], rig_id: str | None = None, *, kind: str | None = None, remote_id: str | None = None) -> None:
        seat_id = _seat_id(seat)
        if not seat_id or seat_id in seen:
            return
        resolved_kind = kind or kind_of(seat)
        target_rig = by_id.get(rig_id) if rig_id else None
        if target_rig is None:
            target_rig = by_id.get(membership.get(seat_id, ""))
        target = target_rig or unassigned

        status = status_from_row(seat)
        if resolved_kind == "remote_agent":
            url = chat_url("remote_agent", seat_id, base_url=base_url, remote_id=remote_id)
        elif resolved_kind == "remote":
            url = chat_url("remote", seat_id, base_url=base_url)
        elif resolved_kind == "team":
            url = chat_url("team", seat_id, base_url=base_url)
        elif target.kind == "team" and target.id != seat_id:
            url = chat_url(resolved_kind, seat_id, base_url=base_url, team_id=target.id)
        elif target.kind == "section" and target.source == "remote":
            other_remote = target.id.split(":", 1)[-1]
            url = chat_url("remote_agent", seat_id, base_url=base_url, remote_id=other_remote)
        else:
            url = chat_url(resolved_kind, seat_id, base_url=base_url, cli=_seat_cli(seat))

        seen.add(seat_id)
        target.agents.append(
            AgentView(
                id=seat_id,
                name=_seat_name(seat, seat_id),
                kind=resolved_kind,
                badge=kind_badge(resolved_kind),
                status=status,
                status_glyph=status_glyph(status),
                rig_id=target.id,
                rig_name=target.name,
                chat_url=url,
                description=str(seat.get("description") or seat.get("specialty") or "").strip(),
                icon=str(seat.get("icon") or "").strip(),
                color=str(seat.get("color") or "").strip(),
                cli=_seat_cli(seat),
                role=str(seat.get("role") or "").strip(),
            )
        )

    # Seat rows from /v1/agents/.
    for row in _agent_rows(agents_payload):
        place(row)

    # Named/discovered CLI seats from /v1/cli-agents/.
    for row in _cli_seats(cli_payload):
        place(row)

    # Remote member agents (or the remote itself when it has no roster).
    for remote in remotes:
        rid = str(remote.get("id") or "").strip()
        rig_id = remote_rig_ids.get(rid)
        if not rig_id:
            continue
        members = remote.get("agents")
        if isinstance(members, list) and members:
            for member in members:
                if isinstance(member, dict):
                    place(member, rig_id, kind="remote_agent", remote_id=rid)
        else:
            place(remote, rig_id, kind="remote")

    all_rigs = list(rigs)
    if unassigned.agents:
        all_rigs.append(unassigned)
    return SwarmView(
        base_url=(base_url or "").strip().rstrip("/"),
        rigs=all_rigs,
        connection=connection,
        version=version,
    )


def _seat_cli(row: Mapping[str, Any]) -> str:
    return str(row.get("cli") or "").strip()

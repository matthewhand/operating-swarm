"""Qualified role addresses — ``role@rig`` (Issue #1224).

OpenRig-style topological identity: an agent may be addressed as
``<role>@<rig>`` (or ``<member>@<rig>``). Two rig families already exist in
Open Swarm and are reused here — no parallel topology is introduced:

* **Dynamic rigs** — operator-created sidepane **Sections**
  (:mod:`swarm.core.agent_sections`). The rig name is the section name.
* **Static rigs** — **Team Blueprints / team rosters**
  (:mod:`swarm.core.team_rosters`). The rig name is the roster name.

The ``@rig`` suffix is optional: a bare role resolves inside the active
rig. Resolution is honest — an unknown rig, an unknown role, or a role that
matches more than one seat in a rig is a distinct error code, never a guess.

The resolver is intentionally pure: build a :class:`RigCatalog` from live
stores (or inject one in tests) and resolve against it.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from swarm.core.agent_roles import CANONICAL_ROLES, normalize_agent_role
from swarm.core.agent_sections import (
    UNASSIGNED_SECTION_ID,
    is_unassigned_section,
    membership_map,
)
from swarm.core.team_isolation import teams_containing
from swarm.core.team_rosters import iter_normalized_rosters

RIG_KIND_DYNAMIC = "dynamic"
RIG_KIND_STATIC = "static"

UNASSIGNED_RIG = "unassigned"

ERROR_EMPTY = "empty_address"
ERROR_INVALID = "invalid_address"
ERROR_UNKNOWN_RIG = "unknown_rig"
ERROR_UNKNOWN_ROLE = "unknown_role"
ERROR_AMBIGUOUS_ROLE = "ambiguous_role"

ADDRESS_SEPARATOR = "@"


@dataclass(frozen=True)
class RigRef:
    """One addressable rig (a section or a team roster)."""

    id: str
    name: str
    kind: str
    blueprint_id: str | None = None

    def tokens(self) -> tuple[str, ...]:
        values = {self.id, self.name, self.name.lower()}
        slug = "".join(c.lower() if c.isalnum() else "-" for c in self.name).strip("-")
        if slug:
            values.add(slug)
        return tuple(v for v in values if v)


@dataclass(frozen=True)
class RigAgent:
    """One seat/agent with the rigs it belongs to."""

    id: str
    role: str
    name: str = ""
    rigs: tuple[RigRef, ...] = ()


@dataclass(frozen=True)
class RigCatalog:
    """Resolvable view of seats and their rig memberships."""

    agents: Mapping[str, RigAgent] = field(default_factory=dict)
    rigs: Mapping[str, RigRef] = field(default_factory=dict)

    def find_rig(self, token: Any) -> RigRef | None:
        key = str(token or "").strip()
        if not key:
            return None
        found = self.rigs.get(key) or self.rigs.get(key.lower())
        if found is not None:
            return found
        slug = "".join(c.lower() if c.isalnum() else "-" for c in key).strip("-")
        return self.rigs.get(slug) if slug else None

    def agents_in_rig(self, rig: RigRef) -> list[RigAgent]:
        return [a for a in self.agents.values() if any(r.id == rig.id for r in a.rigs)]


@dataclass(frozen=True)
class ParsedRigAddress:
    role: str
    rig: str | None
    raw: str


@dataclass(frozen=True)
class ResolvedRigAddress:
    ok: bool
    agent_id: str = ""
    role: str = ""
    rig: str | None = None
    rig_kind: str | None = None
    error: str | None = None
    message: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "agent_id": self.agent_id,
            "role": self.role,
            "rig": self.rig,
            "rig_kind": self.rig_kind,
            "error": self.error,
            "message": self.message,
        }


def _error(code: str, message: str) -> ResolvedRigAddress:
    return ResolvedRigAddress(ok=False, error=code, message=message)


def parse_rig_address(value: Any) -> ParsedRigAddress | None:
    """Split ``role@rig`` into its parts. ``None`` when malformed/empty.

    A bare ``role`` (no separator) is valid with ``rig=None``.
    """
    raw = str(value or "").strip()
    if not raw:
        return None
    if raw.count(ADDRESS_SEPARATOR) > 1:
        return None
    if ADDRESS_SEPARATOR in raw:
        role, rig = raw.split(ADDRESS_SEPARATOR, 1)
        role = role.strip()
        rig = rig.strip()
        if not role or not rig:
            return None
        return ParsedRigAddress(role=role, rig=rig, raw=raw)
    return ParsedRigAddress(role=raw, rig=None, raw=raw)


def format_rig_address(role: Any, rig: Any = None) -> str:
    """Render ``role@rig`` (or the bare role when no rig)."""
    base = str(role or "").strip()
    suffix = str(rig or "").strip()
    if not suffix:
        return base
    return f"{base}{ADDRESS_SEPARATOR}{suffix}"


def _iter_agent_rows(
    agents: Any,
) -> Iterable[tuple[str, str, str, set[str] | None, set[str] | None]]:
    """Yield ``(id, role, name, teams, sections)`` from agent-like input."""
    if agents is None:
        return
    if isinstance(agents, Mapping):
        for key, value in agents.items():
            aid = str(key or "").strip()
            if not aid:
                continue
            if value is None or isinstance(value, str):
                yield aid, str(value or ""), aid, None, None
                continue
            if isinstance(value, Mapping):
                yield (
                    aid,
                    str(value.get("role") or ""),
                    str(value.get("name") or aid),
                    _as_id_set(value.get("teams")),
                    _as_id_set(value.get("sections")),
                )
                continue
            yield (
                aid,
                str(getattr(value, "role", "") or ""),
                str(getattr(value, "name", "") or aid),
                _as_id_set(getattr(value, "teams", None)),
                _as_id_set(getattr(value, "sections", None)),
            )
        return
    for item in agents:
        if isinstance(item, (tuple, list)) and len(item) >= 2:
            yield str(item[0] or "").strip(), str(item[1] or ""), str(item[0] or ""), None, None
            continue
        if isinstance(item, Mapping):
            aid = str(item.get("id") or "").strip()
            if not aid:
                continue
            yield (
                aid,
                str(item.get("role") or ""),
                str(item.get("name") or aid),
                _as_id_set(item.get("teams")),
                _as_id_set(item.get("sections")),
            )
            continue
        aid = str(getattr(item, "id", "") or "").strip()
        if not aid:
            continue
        yield (
            aid,
            str(getattr(item, "role", "") or ""),
            str(getattr(item, "name", "") or aid),
            _as_id_set(getattr(item, "teams", None)),
            _as_id_set(getattr(item, "sections", None)),
        )


def _as_id_set(value: Any) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return {value.strip()} if value.strip() else set()
    return {str(v).strip() for v in value if str(v).strip()}


def _static_rigs(rosters: Any) -> list[RigRef]:
    refs: list[RigRef] = []
    for rid, roster in iter_normalized_rosters(rosters).items():
        blueprint_id = str(roster.get("blueprint_id") or "").strip() or None
        refs.append(
            RigRef(
                id=rid,
                name=str(roster.get("name") or rid),
                kind=RIG_KIND_STATIC,
                blueprint_id=blueprint_id,
            )
        )
    return refs


def _dynamic_rigs(sections: Any) -> list[RigRef]:
    payload = sections if isinstance(sections, dict) else {}
    refs: list[RigRef] = []
    for row in payload.get("sections") or []:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("id") or "").strip()
        if not sid or is_unassigned_section(sid) or row.get("archived") is True:
            continue
        refs.append(RigRef(id=sid, name=str(row.get("name") or sid), kind=RIG_KIND_DYNAMIC))
    return refs


def build_rig_catalog(
    agents: Any = None,
    *,
    rosters: Any = None,
    sections: Any = None,
) -> RigCatalog:
    """Assemble a :class:`RigCatalog` from live stores or injected fixtures."""
    static = _static_rigs(rosters)
    dynamic = _dynamic_rigs(sections)
    rigs: dict[str, RigRef] = {}
    for ref in [*static, *dynamic]:
        for token in ref.tokens():
            rigs.setdefault(token, ref)
    static_ids = {ref.id for ref in static}
    dynamic_ids = {ref.id for ref in dynamic}
    static_by_id = {ref.id: ref for ref in static}
    dynamic_by_id = {ref.id: ref for ref in dynamic}

    membership = membership_map(sections) if isinstance(sections, dict) else {}
    rows = list(_iter_agent_rows(agents))
    if not rows:
        rows = _rows_from_stores(rosters, membership)

    built: dict[str, RigAgent] = {}
    for aid, role, name, teams, agent_sections in rows:
        if not aid:
            continue
        if teams is None:
            teams = teams_containing(aid, rosters)
        if agent_sections is None:
            sid = membership.get(aid)
            agent_sections = {sid} if sid and sid in dynamic_ids else set()
        agent_rigs: list[RigRef] = []
        for tid in sorted(teams & static_ids):
            agent_rigs.append(static_by_id[tid])
        for sid in sorted(agent_sections & dynamic_ids):
            agent_rigs.append(dynamic_by_id[sid])
        existing = built.get(aid)
        canonical_role = normalize_agent_role(role or (existing.role if existing else None))
        built[aid] = RigAgent(
            id=aid,
            role=canonical_role,
            name=name or (existing.name if existing else aid),
            rigs=tuple(agent_rigs),
        )
    return RigCatalog(
        agents=MappingProxyType(dict(built)),
        rigs=MappingProxyType(rigs),
    )


def _rows_from_stores(
    rosters: Any,
    membership: Mapping[str, str],
) -> list[tuple[str, str, str, set[str] | None, set[str] | None]]:
    rows: dict[str, tuple[str, str, str, set[str] | None, set[str] | None]] = {}
    for _rid, roster in iter_normalized_rosters(rosters).items():
        for member in roster.get("members") or []:
            if not isinstance(member, dict) or member.get("kind") == "team":
                continue
            mid = str(member.get("id") or "").strip()
            if not mid:
                continue
            rows[mid] = (
                mid,
                str(member.get("role") or ""),
                str(member.get("name") or mid),
                None,
                None,
            )
    for aid in membership:
        rows.setdefault(aid, (aid, "", aid, None, None))
    return list(rows.values())


def rig_for_agent(
    agent_id: Any,
    *,
    rosters: Any = None,
    sections: Any = None,
) -> RigRef | None:
    """Active rig for *agent_id* — a Team Blueprint first, then a section."""
    catalog = build_rig_catalog(rosters=rosters, sections=sections)
    agent = catalog.agents.get(str(agent_id or "").strip())
    if agent is None:
        return None
    static = sorted(
        (ref for ref in agent.rigs if ref.kind == RIG_KIND_STATIC),
        key=lambda ref: (ref.blueprint_id is None, ref.id),
    )
    if static:
        return static[0]
    dynamic = [ref for ref in agent.rigs if ref.kind == RIG_KIND_DYNAMIC]
    if dynamic:
        return dynamic[0]
    return None


def qualified_rig_address(
    agent_id: Any,
    *,
    role: Any = None,
    rosters: Any = None,
    sections: Any = None,
    show_unassigned: bool = False,
) -> str:
    """Display address for *agent_id*: ``role@rig``, bare role, or ``@unassigned``."""
    aid = str(agent_id or "").strip()
    catalog = build_rig_catalog(rosters=rosters, sections=sections)
    agent = catalog.agents.get(aid)
    resolved_role = normalize_agent_role(role or (agent.role if agent else None))
    rig = rig_for_agent(aid, rosters=rosters, sections=sections)
    if rig is None:
        return format_rig_address(resolved_role, UNASSIGNED_RIG if show_unassigned else None)
    return format_rig_address(resolved_role, rig.name or rig.id)


def _agent_matches(agent: RigAgent, token: str) -> bool:
    value = token.strip()
    if not value:
        return False
    if agent.id == value or agent.name == value:
        return True
    canonical = normalize_agent_role(value)
    if canonical != "default" and canonical == agent.role:
        return True
    # A bare custom/unknown token that happens to equal the raw role string.
    return value.lower() == (agent.role or "").lower()


def _agent_in_rig(agent: RigAgent, rig: RigRef) -> bool:
    return any(ref.id == rig.id for ref in agent.rigs)


def resolve_rig_address(
    value: Any,
    *,
    active_rig: Any = None,
    catalog: RigCatalog | None = None,
    rosters: Any = None,
    sections: Any = None,
) -> ResolvedRigAddress:
    """Resolve ``role@rig`` (or a bare role inside *active_rig*) to one seat."""
    parsed = parse_rig_address(value)
    if parsed is None:
        raw = str(value or "").strip()
        code = ERROR_EMPTY if not raw else ERROR_INVALID
        return _error(code, f"{raw!r} is not a valid role address.")

    if catalog is None:
        catalog = build_rig_catalog(rosters=rosters, sections=sections)

    rig: RigRef | None = None
    if parsed.rig is not None:
        rig = catalog.find_rig(parsed.rig)
        if rig is None:
            return _error(ERROR_UNKNOWN_RIG, f"Unknown rig {parsed.rig!r}.")
        candidates = catalog.agents_in_rig(rig)
    elif active_rig is not None and str(active_rig).strip():
        rig = catalog.find_rig(active_rig)
        if rig is None:
            return _error(
                ERROR_UNKNOWN_RIG,
                f"Unknown active rig {str(active_rig).strip()!r}.",
            )
        candidates = catalog.agents_in_rig(rig)
    else:
        candidates = list(catalog.agents.values())

    matches = [agent for agent in candidates if _agent_matches(agent, parsed.role)]
    if not matches:
        scope = f" in rig {rig.name!r}" if rig is not None else ""
        return _error(ERROR_UNKNOWN_ROLE, f"No seat matches {parsed.role!r}{scope}.")
    if len(matches) > 1:
        ids = ", ".join(sorted(agent.id for agent in matches))
        scope = f" in rig {rig.name!r}" if rig is not None else ""
        return _error(
            ERROR_AMBIGUOUS_ROLE,
            f"{parsed.role!r}{scope} matches {len(matches)} seats: {ids}.",
        )
    agent = matches[0]
    return ResolvedRigAddress(
        ok=True,
        agent_id=agent.id,
        role=agent.role,
        rig=rig.id if rig is not None else None,
        rig_kind=rig.kind if rig is not None else None,
        message=f"Resolved to {agent.id}.",
    )


def active_rig_for_seat(
    agent_id: Any,
    *,
    rosters: Any = None,
    sections: Any = None,
) -> str | None:
    """Name/key of the active rig for display tooltips (or ``None``)."""
    rig = rig_for_agent(agent_id, rosters=rosters, sections=sections)
    if rig is None:
        return None
    return rig.name or rig.id


__all__ = [
    "ADDRESS_SEPARATOR",
    "CANONICAL_ROLES",
    "ERROR_AMBIGUOUS_ROLE",
    "ERROR_EMPTY",
    "ERROR_INVALID",
    "ERROR_UNKNOWN_RIG",
    "ERROR_UNKNOWN_ROLE",
    "ParsedRigAddress",
    "RIG_KIND_DYNAMIC",
    "RIG_KIND_STATIC",
    "ResolvedRigAddress",
    "RigAgent",
    "RigCatalog",
    "RigRef",
    "UNASSIGNED_RIG",
    "UNASSIGNED_SECTION_ID",
    "active_rig_for_seat",
    "build_rig_catalog",
    "format_rig_address",
    "parse_rig_address",
    "qualified_rig_address",
    "resolve_rig_address",
    "rig_for_agent",
]

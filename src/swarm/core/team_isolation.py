"""Team isolation and teams-of-teams (REQ-28).

Default: members of Team A cannot ``handoff`` / ``as_tool`` to Team B or B's
members.

Exceptions:

* The caller has role ``chief_of_staff`` (aliases ``cos``, ``chief``) — may
  target **any** team (and any member).
* Team B is a **direct child** of a team the caller belongs to
  (``kind=team`` + ``team_id`` on the parent roster). The parent talks to
  the child team **as one member** (send-to-all on the child's direct
  members). Grandchildren are not automatic targets.

Documented choice (do not change without updating ``docs/TEAM_ISOLATION.md``):

    Parent talks to the child team as one member (send-to-all on the child),
    not automatically every grandchild. CoS bypasses this and can target any
    team.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from swarm.core.agent_roles import ROLE_CHIEF_OF_STAFF, is_chief_of_staff, normalize_agent_role, role_from_agent
from swarm.core.team_rosters import iter_normalized_rosters

TargetKind = Literal["team", "member"]
Channel = Literal["handoff", "as_tool", "consult"]


@dataclass(frozen=True)
class IsolationDecision:
    """Allow / deny plus a stable reason code for tests and tools."""

    allowed: bool
    reason: str
    caller_id: str
    caller_role: str
    target_id: str
    target_kind: TargetKind
    channel: Channel

    def __bool__(self) -> bool:
        return self.allowed


def _rosters(rosters: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    return iter_normalized_rosters(rosters)


def teams_containing(member_id: str, rosters: dict[str, Any] | None = None) -> set[str]:
    """Roster ids that list *member_id* as a non-team member."""
    found: set[str] = set()
    want = str(member_id or "").strip()
    if not want:
        return found
    for rid, roster in _rosters(rosters).items():
        for member in roster.get("members") or []:
            if member.get("kind") == "team":
                continue
            if member.get("id") == want:
                found.add(rid)
    return found


def role_of_member(member_id: str, rosters: dict[str, Any] | None = None, *, fallback: Any = None) -> str:
    """Canonical role for *member_id*. CoS on any roster wins.

    Since #739 the CoS designation is roster-level (``chief_of_staff_id``);
    the member-level ``role: chief_of_staff`` stamp is legacy and demoted on
    write. Both sources resolve here so authority (mailbox scope, topology
    ACLs, isolation) is identical for pre- and post-#739 rosters.
    """
    if is_chief_of_staff(fallback):
        return ROLE_CHIEF_OF_STAFF
    want = str(member_id or "").strip()
    seen: list[str] = []
    for roster in _rosters(rosters).values():
        cos_id = str(roster.get("chief_of_staff_id") or "").strip()
        if want and cos_id and want == cos_id:
            return ROLE_CHIEF_OF_STAFF
        for member in roster.get("members") or []:
            if member.get("id") != member_id:
                continue
            role = normalize_agent_role(member.get("role"))
            if is_chief_of_staff(role):
                return ROLE_CHIEF_OF_STAFF
            seen.append(role)
    if fallback is not None:
        return normalize_agent_role(fallback)
    return seen[0] if seen else normalize_agent_role(None)


def child_team_ids(parent_id: str, rosters: dict[str, Any] | None = None) -> set[str]:
    """Direct ``kind=team`` children of *parent_id* (not grandchildren)."""
    roster = _rosters(rosters).get(parent_id)
    if not roster:
        return set()
    children: set[str] = set()
    for member in roster.get("members") or []:
        if member.get("kind") != "team":
            continue
        tid = str(member.get("team_id") or member.get("id") or "").strip()
        if tid and tid != parent_id:
            children.add(tid)
    return children


def descendant_team_ids(root_id: str, rosters: dict[str, Any] | None = None) -> set[str]:
    """All nested team ids under *root_id* (cycle-safe)."""
    seen: set[str] = set()
    stack = list(child_team_ids(root_id, rosters))
    while stack:
        tid = stack.pop()
        if tid in seen:
            continue
        seen.add(tid)
        stack.extend(child_team_ids(tid, rosters) - seen)
    return seen


def is_direct_child_team(parent_id: str, child_id: str, rosters: dict[str, Any] | None = None) -> bool:
    return child_id in child_team_ids(parent_id, rosters)


def resolve_target_kind(target_id: str, rosters: dict[str, Any] | None = None) -> TargetKind:
    """Treat a known roster id as a team; otherwise a member."""
    if target_id in _rosters(rosters):
        return "team"
    return "member"


def team_member_ids(team_id: str, rosters: dict[str, Any] | None = None, *, include_nested_teams: bool = False) -> list[str]:
    """Direct members of *team_id*.

    By default ``kind=team`` slots are included as the child team id (the
    parent talks to that unit) but **grandchild people are omitted**.
    """
    roster = _rosters(rosters).get(team_id)
    if not roster:
        return []
    ids: list[str] = []
    for member in roster.get("members") or []:
        if member.get("kind") == "team":
            tid = str(member.get("team_id") or member.get("id") or "").strip()
            if tid:
                ids.append(tid)
            if include_nested_teams:
                ids.extend(team_member_ids(tid, rosters, include_nested_teams=True))
            continue
        mid = str(member.get("id") or "").strip()
        if mid:
            ids.append(mid)
    return ids


def send_to_all_targets(team_id: str, rosters: dict[str, Any] | None = None) -> list[str]:
    """Direct child-team members for a send-to-all. No automatic grandchildren.

    People (api/cli/remote/herdr) on the child roster are included. Nested
    ``kind=team`` slots are included as the child team id only.
    """
    return team_member_ids(team_id, rosters, include_nested_teams=False)


def _caller_home_teams(caller_id: str, rosters: dict[str, Any] | None) -> set[str]:
    return teams_containing(caller_id, rosters)


def can_talk(
    *,
    caller_id: str,
    target_id: str,
    channel: Channel = "handoff",
    caller_role: Any = None,
    target_kind: TargetKind | None = None,
    rosters: dict[str, Any] | None = None,
) -> IsolationDecision:
    """Decide whether *caller_id* may ``handoff`` / ``as_tool`` / consult *target_id*.

    Rules (REQ-28):

    1. CoS → allow any team or member.
    2. Same team (caller and target are both people on the same roster) → allow.
    3. Target is a **direct child team** of a caller home team → allow
       (parent → child as one unit / send-to-all).
    4. Target is a member of another team, a sibling team, or a grandchild
       team / grandchild person → deny.
    """
    role = role_of_member(caller_id, rosters, fallback=caller_role)
    kind = target_kind or resolve_target_kind(target_id, rosters)
    base = dict(
        caller_id=caller_id,
        caller_role=role,
        target_id=target_id,
        target_kind=kind,
        channel=channel,
    )

    if not caller_id or not target_id:
        return IsolationDecision(allowed=False, reason="missing_id", **base)

    if caller_id == target_id:
        return IsolationDecision(allowed=True, reason="self", **base)

    if is_chief_of_staff(role):
        return IsolationDecision(allowed=True, reason="chief_of_staff", **base)

    homes = _caller_home_teams(caller_id, rosters)

    if kind == "team":
        if target_id in homes:
            return IsolationDecision(allowed=True, reason="own_team", **base)
        if any(is_direct_child_team(home, target_id, rosters) for home in homes):
            return IsolationDecision(allowed=True, reason="nested_child_team", **base)
        return IsolationDecision(allowed=False, reason="cross_team_denied", **base)

    target_homes = teams_containing(target_id, rosters)
    if homes and target_homes and homes & target_homes:
        return IsolationDecision(allowed=True, reason="same_team", **base)

    # Parent may *not* address child members (grandchildren of the parent
    # conversation). Only the child team unit is in scope.
    if any(
        target_id in team_member_ids(child, rosters) and child not in homes
        for home in homes
        for child in child_team_ids(home, rosters)
    ):
        return IsolationDecision(allowed=False, reason="grandchild_member_denied", **base)

    return IsolationDecision(allowed=False, reason="cross_team_denied", **base)


def can_handoff(**kwargs: Any) -> IsolationDecision:
    return can_talk(channel="handoff", **kwargs)


def can_as_tool(**kwargs: Any) -> IsolationDecision:
    return can_talk(channel="as_tool", **kwargs)


def consultable_team_ids(
    caller_id: str,
    *,
    caller_role: Any = None,
    rosters: dict[str, Any] | None = None,
) -> list[str]:
    """Team ids the caller may consult / hand off to.

    * CoS → every roster id.
    * Others → only **direct child** team ids (not own team as a consult
      target, not grandchildren). Default: no cross-team consult tools.
    """
    role = role_of_member(caller_id, rosters, fallback=caller_role)
    all_ids = sorted(_rosters(rosters))
    if is_chief_of_staff(role):
        return all_ids
    homes = _caller_home_teams(caller_id, rosters)
    children: set[str] = set()
    for home in homes:
        children.update(child_team_ids(home, rosters))
    return sorted(children)


def assert_talk_allowed(decision: IsolationDecision) -> IsolationDecision:
    """Raise ``PermissionError`` when isolation denies the channel."""
    if not decision.allowed:
        raise PermissionError(
            f"isolation deny ({decision.reason}): {decision.caller_id} "
            f"cannot {decision.channel} {decision.target_kind} {decision.target_id}"
        )
    return decision


def caller_from_agent(agent: Any, *, fallback_id: str = "") -> tuple[str, str]:
    """``(id, role)`` from an Agent / spec dict."""
    if isinstance(agent, dict):
        mid = str(agent.get("id") or agent.get("name") or fallback_id)
    else:
        mid = str(getattr(agent, "id", None) or getattr(agent, "name", None) or fallback_id)
    return mid, role_from_agent(agent)

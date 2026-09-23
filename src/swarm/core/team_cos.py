"""Team-scoped Chief of Staff selection and how-to-use-the-team brief (REQ-107).

A roster may optionally name **one** current member as Chief of Staff and store
written guidance for employing the rest of the roster. The brief is
**team-scoped**: the same agent id may sit on two teams with two different
briefs. Only the active team's CoS receives that team's brief.

Do not invent a CoS when none was chosen. Remotes / nested teams / Herdr
slots are omitted from the picker — runtime injects a system/developer
message for API and CLI seats only.
"""

from __future__ import annotations

from typing import Any

from swarm.core.agent_roles import ROLE_CHIEF_OF_STAFF, ROLE_DEFAULT, is_chief_of_staff, normalize_agent_role

# API + CLI can receive an injected system/developer brief. Remotes keep
# their own session and cannot be CoS until a later runtime slice.
COS_ELIGIBLE_KINDS: tuple[str, ...] = ("api", "cli")
COS_INELIGIBLE_KINDS: tuple[str, ...] = ("remote", "team", "herdr")

COS_BRIEF_ROLE = "developer"
COS_INSTRUCTIONS_MAX_LEN = 8000

# Generic starter (editable). Examples stay in helper text only.
DEFAULT_COS_STARTER = (
    "Coordinate this team's roster. Hand off or use-as-tool according to "
    "each member's strengths. Do not duplicate work. Report back.\n\n"
    "Add specifics for this team: …"
)

COS_INSTRUCTIONS_HELPER = (
    "Add specifics for this team — for example prefer grok_agent for "
    "revision control, use skeptic only after implement, Hermes for "
    "long-running host tasks. The same agent can sit on multiple teams; "
    "this team's CoS brief steers how members are used here."
)

COS_EMPTY_ROSTER_HINT = "Add agents first"

COS_REMOTE_REASON = (
    "Remote members cannot be Chief of Staff yet — pick an API or CLI "
    "agent that can hand off or use them as tools."
)

COS_NESTED_REASON = "Nested teams and Herdr slots cannot be Chief of Staff."

NO_COS_LABEL = "No Chief of Staff"


def is_cos_eligible_kind(kind: Any) -> bool:
    return str(kind or "").strip().lower() in COS_ELIGIBLE_KINDS


def is_cos_eligible_member(member: Any) -> bool:
    if not isinstance(member, dict):
        return False
    return is_cos_eligible_kind(member.get("kind"))


def cos_ineligible_reason(member: Any) -> str | None:
    """Why this roster row is omitted from the CoS picker, or None if eligible."""
    if is_cos_eligible_member(member):
        return None
    kind = str((member or {}).get("kind") or "").strip().lower()
    if kind == "remote":
        return COS_REMOTE_REASON
    if kind in {"team", "herdr"}:
        return COS_NESTED_REASON
    if kind:
        return COS_REMOTE_REASON
    return COS_EMPTY_ROSTER_HINT


def _member_id(member: Any) -> str:
    if not isinstance(member, dict):
        return ""
    return str(member.get("id") or "").strip()


def find_member(members: Any, member_id: str | None) -> dict[str, Any] | None:
    want = str(member_id or "").strip()
    if not want or not isinstance(members, list):
        return None
    for member in members:
        if isinstance(member, dict) and _member_id(member) == want:
            return member
    return None


def eligible_cos_members(members: Any) -> list[dict[str, Any]]:
    if not isinstance(members, list):
        return []
    return [m for m in members if is_cos_eligible_member(m)]


def normalize_cos_id(raw_id: Any, members: list[dict[str, Any]]) -> str | None:
    """Return a valid eligible member id, or None. Never invents a CoS."""
    want = str(raw_id or "").strip()
    if not want:
        return None
    member = find_member(members, want)
    if member is None:
        # Member left the roster — do not keep a dangling / fake CoS.
        return None
    if not is_cos_eligible_member(member):
        raise ValueError(
            "Chief of Staff must be an API or CLI member already on this roster."
        )
    return want


def normalize_cos_instructions(raw: Any, *, has_cos: bool) -> str:
    text = "" if raw is None else str(raw)
    if not has_cos:
        return ""
    if len(text) > COS_INSTRUCTIONS_MAX_LEN:
        raise ValueError(
            f"Chief of Staff instructions too long (max {COS_INSTRUCTIONS_MAX_LEN})."
        )
    return text


def restore_cos_id_from_roles(members: list[dict[str, Any]]) -> str | None:
    """Legacy-tag fallback: recover a CoS id from a pre-#739 stamped member.

    #739 retired the member-level CoS tag — new rosters carry ``chief_of_staff_id``
    only. This stays as a read-only migration path so an unstamped payload never
    silently loses its leader; it never stamps anything back.
    """
    tagged = [
        m
        for m in members
        if is_chief_of_staff(m.get("role")) and is_cos_eligible_member(m)
    ]
    if len(tagged) != 1:
        return None
    return _member_id(tagged[0]) or None


def stamp_cos_role(members: list[dict[str, Any]], cos_id: str | None) -> list[dict[str, Any]]:
    """Demote leftover CoS role tags (#739): leadership lives on ``chief_of_staff_id``.

    The member-level ``role: chief_of_staff`` stamp is retired — CoS is a
    roster-level designation, not a composable member role. New selections
    never write the tag; any legacy stamp is demoted to ``default`` (or the
    member's other assigned role) so old payloads converge to the new
    doctrine instead of carrying a second source of truth forever.
    """
    return [
        {**member, "role": ROLE_DEFAULT} if is_chief_of_staff(member.get("role")) else member
        for member in members
    ]


def apply_cos_fields(roster: dict[str, Any], raw: dict[str, Any]) -> dict[str, Any]:
    """Attach team-scoped CoS id + instructions. Raises ValueError on bad input."""
    members = list(roster.get("members") or [])
    explicit = "chief_of_staff_id" in raw
    raw_id = raw.get("chief_of_staff_id")
    if explicit:
        cos_id = normalize_cos_id(raw_id, members)
    else:
        cos_id = restore_cos_id_from_roles(members)
    if cos_id or explicit:
        # Selecting a CoS stamps the role. Explicit clear demotes leftovers
        # so we do not keep a fake CoS after the user chose "No CoS".
        members = stamp_cos_role(members, cos_id)
    instructions = normalize_cos_instructions(
        raw.get("chief_of_staff_instructions"),
        has_cos=bool(cos_id),
    )
    out = dict(roster)
    out["members"] = members
    out["chief_of_staff_id"] = cos_id
    out["chief_of_staff_instructions"] = instructions
    return out


def resolve_chief_of_staff(roster: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(roster, dict):
        return None
    return find_member(roster.get("members"), roster.get("chief_of_staff_id"))


def is_team_cos(roster: dict[str, Any] | None, member_id: str | None) -> bool:
    """True when *member_id* is this roster's selected CoS (not another team's)."""
    if not isinstance(roster, dict):
        return False
    want = str(member_id or "").strip()
    cos_id = str(roster.get("chief_of_staff_id") or "").strip()
    return bool(want and cos_id and want == cos_id)


def cos_brief_for_member(roster: dict[str, Any] | None, member_id: str | None) -> str | None:
    """Team-scoped brief for *member_id*, or None (non-CoS / no CoS / empty)."""
    if not is_team_cos(roster, member_id):
        return None
    text = str((roster or {}).get("chief_of_staff_instructions") or "").strip()
    return text or None


def runtime_brief_for_target(roster: dict[str, Any] | None, target: str | None) -> str | None:
    """Brief for a team send target.

    ``all`` (or blank) goes to the CoS when one is selected. A non-CoS
    member target never receives the CoS brief. No CoS → no brief.
    """
    if not isinstance(roster, dict):
        return None
    cos_id = str(roster.get("chief_of_staff_id") or "").strip()
    if not cos_id:
        return None
    dest = str(target or "").strip() or "all"
    if dest in {"all", "*", cos_id}:
        return cos_brief_for_member(roster, cos_id)
    return None


def messages_with_cos_brief(
    roster: dict[str, Any] | None,
    member_id: str | None,
    messages: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Prepend a developer/system brief for this team's CoS only."""
    out = list(messages or [])
    brief = cos_brief_for_member(roster, member_id)
    if not brief:
        return out
    return [{"role": COS_BRIEF_ROLE, "content": brief}, *out]


def team_run_context(
    roster: dict[str, Any] | None,
    target: str | None,
    messages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Runtime bag for a team turn. Empty brief when no CoS (today's behaviour)."""
    dest = str(target or "").strip() or "all"
    cos = resolve_chief_of_staff(roster)
    cos_id = _member_id(cos) if cos else None
    recipient = cos_id if dest in {"all", "*", ""} else dest
    brief = runtime_brief_for_target(roster, dest)
    applied = bool(brief)
    model_messages = list(messages or [])
    if applied and recipient:
        model_messages = messages_with_cos_brief(roster, recipient, model_messages)
    return {
        "team_id": str((roster or {}).get("id") or ""),
        "target": dest,
        "chief_of_staff_id": cos_id,
        "brief_applied": applied,
        "brief": brief,
        "recipient_id": recipient if applied else None,
        "model_messages": model_messages,
    }

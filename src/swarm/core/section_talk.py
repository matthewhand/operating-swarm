"""Section internal-only talk lock (Issue #163).

When a custom rail section is marked **internal-only**, members may message
only each other — including a team of one. Unassigned is never lockable.
Unlock restores normal mailbox / team reach.

SPA chrome persists this on ``swarm_rail_sections`` (REQ-209 localStorage SoT).
A chat turn may snapshot it as ``params.rail_sections`` so mailbox
``list_agents`` / ``send_message`` enforce the same rule without a second store.

This layer is **additive** on top of team isolation (REQ-28) and mailbox ACL
(REQ-162). CoS/Support allow-all does **not** bypass a locked section.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

REASON_SELF = "self"
REASON_SAME_SECTION = "same_section"
REASON_UNLOCKED = "section_unlocked"
REASON_INTERNAL_ONLY = "section_internal_only"
REASON_TARGET_LOCKED = "target_section_internal_only"
REASON_MISSING_ID = "missing_id"

UNASSIGNED_SECTION_ID = "unassigned"


@dataclass(frozen=True)
class RailSectionLock:
    id: str
    name: str = ""
    internal_only: bool = False


@dataclass(frozen=True)
class SectionTalkState:
    sections: tuple[RailSectionLock, ...] = ()
    membership: Mapping[str, str] | None = None

    def members(self) -> dict[str, str]:
        return dict(self.membership or {})


@dataclass(frozen=True)
class SectionTalkDecision:
    """Allow / deny plus a stable reason code for mailbox + UI."""

    allowed: bool
    reason: str
    caller_id: str
    target_id: str
    section_id: str = ""

    def __bool__(self) -> bool:
        return self.allowed


EMPTY_SECTION_TALK = SectionTalkState()


def _is_record(value: Any) -> bool:
    return isinstance(value, dict) and not isinstance(value, type(None))


def _truthy_flag(item: Mapping[str, Any], *keys: str) -> bool:
    for key in keys:
        if item.get(key) is True:
            return True
    return False


def is_unassigned_section(section_id: str | None) -> bool:
    return not section_id or section_id == UNASSIGNED_SECTION_ID


def parse_section_talk_state(raw: Any) -> SectionTalkState:
    """Parse SPA ``rail_sections`` JSON (camelCase or snake_case)."""
    if not _is_record(raw):
        return EMPTY_SECTION_TALK
    sections: list[RailSectionLock] = []
    seen: set[str] = set()
    raw_sections = raw.get("sections")
    if isinstance(raw_sections, list):
        for item in raw_sections:
            if not _is_record(item):
                continue
            ident = str(item.get("id") or "").strip()
            if not ident or ident == UNASSIGNED_SECTION_ID or ident in seen:
                continue
            seen.add(ident)
            name = item.get("name")
            sections.append(
                RailSectionLock(
                    id=ident,
                    name=str(name) if isinstance(name, str) else "",
                    internal_only=_truthy_flag(item, "internalOnly", "internal_only"),
                )
            )
    membership: dict[str, str] = {}
    raw_membership = raw.get("membership")
    if _is_record(raw_membership):
        known = {section.id for section in sections}
        for agent_id, section_id in raw_membership.items():
            aid = str(agent_id or "").strip()
            sid = str(section_id or "").strip()
            if not aid or not sid or sid == UNASSIGNED_SECTION_ID or sid not in known:
                continue
            membership[aid] = sid
    if not sections and not membership:
        return EMPTY_SECTION_TALK
    return SectionTalkState(sections=tuple(sections), membership=membership)


def section_id_for_agent(agent_id: str, state: SectionTalkState | None) -> str:
    if state is None:
        return UNASSIGNED_SECTION_ID
    assigned = state.members().get(str(agent_id or "").strip())
    if assigned and any(section.id == assigned for section in state.sections):
        return assigned
    return UNASSIGNED_SECTION_ID


def section_member_ids(section_id: str, state: SectionTalkState | None) -> set[str]:
    if state is None or is_unassigned_section(section_id):
        return set()
    return {aid for aid, sid in state.members().items() if sid == section_id}


def is_section_internal_only(section_id: str, state: SectionTalkState | None) -> bool:
    if state is None or is_unassigned_section(section_id):
        return False
    for section in state.sections:
        if section.id == section_id:
            return bool(section.internal_only)
    return False


def has_internal_only(state: SectionTalkState | None) -> bool:
    if state is None:
        return False
    return any(section.internal_only for section in state.sections)


def can_section_talk(
    caller_id: str,
    target_id: str,
    state: SectionTalkState | None = None,
) -> SectionTalkDecision:
    """Decide whether *caller_id* may message *target_id* under section lock.

    Rules (Issue #163):

    1. Missing ids → deny.
    2. Self → allow.
    3. Caller in an internal-only custom section → allow iff target is a
       member of that same section (team of one: nobody else).
    4. Target in an internal-only custom section the caller does not share
       → deny (inbound lock; members talk only among themselves).
    5. Otherwise → allow (other isolation/ACL still apply).
    """
    caller = str(caller_id or "").strip()
    target = str(target_id or "").strip()
    if not caller or not target:
        return SectionTalkDecision(
            allowed=False,
            reason=REASON_MISSING_ID,
            caller_id=caller,
            target_id=target,
        )
    if caller == target:
        return SectionTalkDecision(
            allowed=True,
            reason=REASON_SELF,
            caller_id=caller,
            target_id=target,
        )
    caller_section = section_id_for_agent(caller, state)
    target_section = section_id_for_agent(target, state)
    if is_section_internal_only(caller_section, state):
        if caller_section == target_section:
            return SectionTalkDecision(
                allowed=True,
                reason=REASON_SAME_SECTION,
                caller_id=caller,
                target_id=target,
                section_id=caller_section,
            )
        return SectionTalkDecision(
            allowed=False,
            reason=REASON_INTERNAL_ONLY,
            caller_id=caller,
            target_id=target,
            section_id=caller_section,
        )
    if is_section_internal_only(target_section, state):
        return SectionTalkDecision(
            allowed=False,
            reason=REASON_TARGET_LOCKED,
            caller_id=caller,
            target_id=target,
            section_id=target_section,
        )
    return SectionTalkDecision(
        allowed=True,
        reason=REASON_UNLOCKED,
        caller_id=caller,
        target_id=target,
    )


def filter_talk_targets(
    caller_id: str,
    target_ids: Iterable[str],
    state: SectionTalkState | None = None,
) -> set[str]:
    """Keep ids *caller_id* may message under the section lock."""
    if not has_internal_only(state):
        return {str(ident).strip() for ident in target_ids if str(ident).strip()}
    kept: set[str] = set()
    for ident in target_ids:
        tid = str(ident or "").strip()
        if tid and can_section_talk(caller_id, tid, state).allowed:
            kept.add(tid)
    return kept


__all__ = [
    "EMPTY_SECTION_TALK",
    "REASON_INTERNAL_ONLY",
    "REASON_MISSING_ID",
    "REASON_SAME_SECTION",
    "REASON_SELF",
    "REASON_TARGET_LOCKED",
    "REASON_UNLOCKED",
    "UNASSIGNED_SECTION_ID",
    "RailSectionLock",
    "SectionTalkDecision",
    "SectionTalkState",
    "can_section_talk",
    "filter_talk_targets",
    "has_internal_only",
    "is_section_internal_only",
    "is_unassigned_section",
    "parse_section_talk_state",
    "section_id_for_agent",
    "section_member_ids",
]

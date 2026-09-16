"""Issue #163 — section internal-only talk lock."""

from __future__ import annotations

from swarm.core.section_talk import (
    REASON_INTERNAL_ONLY,
    REASON_MISSING_ID,
    REASON_SAME_SECTION,
    REASON_SELF,
    REASON_TARGET_LOCKED,
    REASON_UNLOCKED,
    UNASSIGNED_SECTION_ID,
    can_section_talk,
    filter_talk_targets,
    has_internal_only,
    is_section_internal_only,
    parse_section_talk_state,
    section_id_for_agent,
    section_member_ids,
)


LOCKED = {
    "sections": [
        {"id": "sec_office", "name": "office", "internalOnly": True},
        {"id": "sec_open", "name": "open", "internalOnly": False},
    ],
    "membership": {
        "pat": "sec_office",
        "cos": "sec_office",
        "ada": "sec_open",
        "ivy": "sec_missing",
    },
}


def test_parse_skips_corrupt_and_unassigned():
    assert parse_section_talk_state(None).sections == ()
    assert parse_section_talk_state("{nope").sections == ()
    assert parse_section_talk_state({"sections": [1], "membership": {"x": 2}}).sections == ()
    parsed = parse_section_talk_state(
        {
            "sections": [
                {"id": "unassigned", "name": "nope", "internalOnly": True},
                {"id": "sec_a", "name": "alpha", "internal_only": True},
            ],
            "membership": {"pat": "unassigned", "cos": "sec_a", "ghost": "gone"},
        }
    )
    assert [s.id for s in parsed.sections] == ["sec_a"]
    assert parsed.sections[0].internal_only is True
    assert parsed.members() == {"cos": "sec_a"}


def test_lock_allows_same_section_and_self():
    state = parse_section_talk_state(LOCKED)
    assert can_section_talk("pat", "pat", state).reason == REASON_SELF
    same = can_section_talk("pat", "cos", state)
    assert same.allowed is True
    assert same.reason == REASON_SAME_SECTION
    assert same.section_id == "sec_office"


def test_lock_blocks_outbound_and_inbound():
    state = parse_section_talk_state(LOCKED)
    outbound = can_section_talk("pat", "ada", state)
    assert outbound.allowed is False
    assert outbound.reason == REASON_INTERNAL_ONLY
    inbound = can_section_talk("ada", "pat", state)
    assert inbound.allowed is False
    assert inbound.reason == REASON_TARGET_LOCKED


def test_team_of_one_blocks_everyone_until_unlock():
    solo = parse_section_talk_state(
        {
            "sections": [{"id": "sec_solo", "name": "solo", "internalOnly": True}],
            "membership": {"pat": "sec_solo"},
        }
    )
    assert can_section_talk("pat", "cos", solo).allowed is False
    assert can_section_talk("cos", "pat", solo).allowed is False
    assert filter_talk_targets("pat", ["cos", "support", "pat"], solo) == {"pat"}
    unlocked = parse_section_talk_state(
        {
            "sections": [{"id": "sec_solo", "name": "solo", "internalOnly": False}],
            "membership": {"pat": "sec_solo"},
        }
    )
    assert can_section_talk("pat", "cos", unlocked).reason == REASON_UNLOCKED
    assert can_section_talk("cos", "pat", unlocked).allowed is True


def test_unassigned_and_unlocked_are_not_locks():
    state = parse_section_talk_state(LOCKED)
    assert is_section_internal_only(UNASSIGNED_SECTION_ID, state) is False
    assert is_section_internal_only("sec_open", state) is False
    assert section_id_for_agent("ivy", state) == UNASSIGNED_SECTION_ID
    assert section_id_for_agent("ghost", state) == UNASSIGNED_SECTION_ID
    assert can_section_talk("ada", "ivy", state).allowed is True
    assert can_section_talk("", "pat", state).reason == REASON_MISSING_ID


def test_filter_is_noop_without_locks():
    unlocked = parse_section_talk_state(
        {
            "sections": [{"id": "sec_open", "name": "open", "internalOnly": False}],
            "membership": {"pat": "sec_open"},
        }
    )
    assert has_internal_only(unlocked) is False
    assert filter_talk_targets("pat", ["cos", "ada"], unlocked) == {"cos", "ada"}
    assert filter_talk_targets("pat", ["cos"], None) == {"cos"}


def test_members_of_locked_section():
    state = parse_section_talk_state(LOCKED)
    assert section_member_ids("sec_office", state) == {"pat", "cos"}
    assert section_member_ids(UNASSIGNED_SECTION_ID, state) == set()

"""REQ-28 isolation: deny cross-team, allow CoS, allow nested child team as a unit."""

import pytest

from swarm.core.team_consult import TeamConsultTool, build_cross_team_tools
from swarm.core.team_isolation import (
    ROLE_CHIEF_OF_STAFF,
    can_as_tool,
    can_handoff,
    can_talk,
    consultable_team_ids,
    role_of_member,
    send_to_all_targets,
)

OFFICE = {
    "office": {
        "id": "office",
        "name": "Office",
        "members": [
            {"id": "pat", "kind": "api", "role": "default", "source": "blueprint:pat"},
            {"id": "cos", "kind": "api", "role": "chief_of_staff", "source": "blueprint:cos"},
            {"id": "research", "kind": "team", "team_id": "research", "role": "default", "source": "team:research"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "research": {
        "id": "research",
        "name": "Research",
        "members": [
            {"id": "ada", "kind": "api", "role": "default", "source": "blueprint:ada"},
            {"id": "lab", "kind": "team", "team_id": "lab", "role": "default", "source": "team:lab"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "lab": {
        "id": "lab",
        "name": "Lab",
        "members": [
            {"id": "lee", "kind": "cli", "role": "default", "source": "cli:lee"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "ops": {
        "id": "ops",
        "name": "Ops",
        "members": [
            {"id": "kim", "kind": "remote", "role": "default", "source": "placeholder:remote:kim"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
}


def test_isolation_deny_sibling_team_and_foreign_members():
    """Members of Team A cannot handoff/as_tool to Team B or B's members."""
    deny_team = can_handoff(caller_id="pat", target_id="ops", rosters=OFFICE)
    deny_member = can_as_tool(caller_id="pat", target_id="kim", rosters=OFFICE)
    assert deny_team.allowed is False
    assert deny_team.reason == "cross_team_denied"
    assert deny_member.allowed is False
    assert deny_member.reason == "cross_team_denied"


def test_isolation_cos_allow_any_team():
    """Chief of Staff (cos / chief) may target any team."""
    for alias_role in ("chief_of_staff", "cos", "chief"):
        decision = can_talk(
            caller_id="someone",
            caller_role=alias_role,
            target_id="ops",
            target_kind="team",
            rosters=OFFICE,
        )
        assert decision.allowed is True
        assert decision.reason == "chief_of_staff"

    roster_cos = can_handoff(caller_id="cos", target_id="ops", rosters=OFFICE)
    assert roster_cos.allowed is True
    assert roster_cos.reason == "chief_of_staff"

    member = can_as_tool(caller_id="cos", target_id="kim", rosters=OFFICE)
    assert member.allowed is True


def test_isolation_nested_allow_child_team_as_unit_not_grandchildren():
    """Parent talks to the child team as one member — not every grandchild."""
    child = can_handoff(caller_id="pat", target_id="research", rosters=OFFICE)
    assert child.allowed is True
    assert child.reason == "nested_child_team"

    child_person = can_as_tool(caller_id="pat", target_id="ada", rosters=OFFICE)
    assert child_person.allowed is False
    assert child_person.reason == "grandchild_member_denied"

    grandchild_team = can_handoff(caller_id="pat", target_id="lab", rosters=OFFICE)
    assert grandchild_team.allowed is False
    assert grandchild_team.reason == "cross_team_denied"

    grandchild_person = can_as_tool(caller_id="pat", target_id="lee", rosters=OFFICE)
    assert grandchild_person.allowed is False


def test_same_team_members_can_talk():
    assert can_handoff(caller_id="pat", target_id="cos", rosters=OFFICE).allowed is True
    assert can_as_tool(caller_id="ada", target_id="ada", rosters=OFFICE).allowed is True


def test_send_to_all_is_direct_members_only():
    targets = send_to_all_targets("research", OFFICE)
    assert "ada" in targets
    assert "lab" in targets
    assert "lee" not in targets


def test_default_has_no_cross_team_consult_tools_cos_gets_every_team():
    pat_tools = build_cross_team_tools("pat", rosters=OFFICE)
    names = {t.name for t in pat_tools}
    assert "consult_team_research" in names
    assert "handoff_team_research" in names
    assert "consult_team_ops" not in names
    assert "consult_team_lab" not in names

    stranger_tools = build_cross_team_tools("lee", rosters=OFFICE)
    assert stranger_tools == []

    cos_ids = consultable_team_ids("cos", rosters=OFFICE)
    assert cos_ids == ["lab", "office", "ops", "research"]
    cos_tools = build_cross_team_tools("cos", rosters=OFFICE)
    assert {t.target_team_id for t in cos_tools} == set(cos_ids)
    assert any(t.kind == "consult" for t in cos_tools)
    assert any(t.kind == "handoff" for t in cos_tools)


def test_consult_tool_invokes_send_to_all_and_denies_strangers():
    tool = TeamConsultTool(
        name="consult_team_research",
        description="x",
        kind="consult",
        target_team_id="research",
        caller_id="pat",
        rosters=OFFICE,
    )
    result = tool("brief the squad")
    assert result["ok"] is True
    assert result["send_to_all"] is True
    assert "ada" in result["recipients"]
    assert "lee" not in result["recipients"]
    assert "sessions" in result
    assert any(row["agent_id"] == "ada" for row in result["sessions"])

    blocked = TeamConsultTool(
        name="consult_team_ops",
        description="x",
        kind="consult",
        target_team_id="ops",
        caller_id="pat",
        rosters=OFFICE,
    )
    with pytest.raises(PermissionError, match="cross_team_denied"):
        blocked("nope")


def test_role_of_member_honors_roster_level_chief_of_staff_id():
    """#739 — CoS authority resolves from chief_of_staff_id without a role stamp."""
    rosters = {
        "ops": {
            "id": "ops",
            "chief_of_staff_id": "jeeves",
            "members": [
                {"id": "jeeves", "kind": "api", "role": "default", "source": "blueprint:jeeves"},
                {"id": "grok", "kind": "cli", "role": "skeptic", "source": "cli:grok"},
            ],
        }
    }
    assert role_of_member("jeeves", rosters) == ROLE_CHIEF_OF_STAFF
    # Legacy stamped tag (no explicit chief_of_staff_id key) is recovered into
    # the roster-level designation during normalization — the migration path.
    legacy = {
        "ops": {
            "id": "ops",
            "members": [
                {"id": "jeeves", "kind": "api", "role": "chief_of_staff", "source": "blueprint:jeeves"},
            ],
        }
    }
    assert role_of_member("jeeves", legacy) == ROLE_CHIEF_OF_STAFF
    # An explicit clear (chief_of_staff_id: None) demotes and yields no CoS.
    cleared = {
        "ops": {
            "id": "ops",
            "chief_of_staff_id": None,
            "members": [
                {"id": "jeeves", "kind": "api", "role": "chief_of_staff", "source": "blueprint:jeeves"},
            ],
        }
    }
    assert role_of_member("jeeves", cleared) != ROLE_CHIEF_OF_STAFF
    # Non-CoS members are unaffected.
    assert role_of_member("grok", rosters) == "skeptic"

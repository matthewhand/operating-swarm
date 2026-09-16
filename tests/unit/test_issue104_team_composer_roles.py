"""Issue #104: team composer adds agents first, then unlocks a Roles pane."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
TEAM_ROSTER = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"
COMPOSER_TEST = (
    REPO / "webui" / "frontend" / "src" / "components" / "__tests__" / "TeamComposer.test.tsx"
)
ROSTER_TEST = REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "teamRoster.test.ts"


def test_roles_pane_is_agents_first_with_distinct_drag_mime():
    src = COMPOSER.read_text(encoding="utf-8")
    helpers = TEAM_ROSTER.read_text(encoding="utf-8")
    assert "team-roles-drop-zone" in src
    assert "team-roles-pane" in src
    assert "ROLE_DRAG_MIME" in src
    assert "drop roles here" in src
    assert "COS_EMPTY_ROSTER_HINT" in src
    assert 'name="team-chief-of-staff"' not in src
    assert "Role for {member.id}" not in src
    assert "TEAM_MEMBER_ROLES.filter" not in src
    assert "application/x-swarm-team-role" in helpers
    assert "application/x-swarm-team-agent" in helpers
    assert "COMPOSABLE_TEAM_ROLES" in helpers
    assert "unassignedMembers" in helpers
    assert "assignableMembersForSlot" in helpers
    for role in ("support", "gate", "skeptic", "chief_of_staff", "suggestions", "engineer"):
        assert f"'{role}'" in helpers
    assert "First agent" not in src
    assert "handoff" in src and "as_tool" in src


def test_roles_pane_covered_by_frontend_tests():
    test = COMPOSER_TEST.read_text(encoding="utf-8")
    roster = ROSTER_TEST.read_text(encoding="utf-8")
    assert "team-roles-drop-zone" in test
    assert "ROLE_DRAG_MIME" in test
    assert "team-role-assign-skeptic" in test
    assert "team-role-assign-chief_of_staff" in test
    assert "assignableMembersForSlot" in roster
    assert "COMPOSABLE_TEAM_ROLES" in roster

"""Issue #105: Team lead picker (First agent) and numbered reorderable roster."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
TEAM_ROSTER = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"
COMPOSER_TEST = (
    REPO / "webui" / "frontend" / "src" / "components" / "__tests__" / "TeamComposer.test.tsx"
)
ROSTER_TEST = REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "teamRoster.test.ts"


def test_team_lead_picker_uses_first_agent_and_numbered_roster():
    src = COMPOSER.read_text(encoding="utf-8")
    helpers = TEAM_ROSTER.read_text(encoding="utf-8")
    assert "First agent" in src
    assert "FIRST_AGENT_VALUE" in src
    assert "ROSTER_DRAG_MIME" in src
    assert "roster-index" in src
    assert "reorderMembers" in src
    assert 'No Chief of Staff' in src
    assert src.count("Chief of Staff") >= 2
    assert "team-roles-pane" in src
    assert "handoff" in src and "as_tool" in src
    legend = src[src.find("team-cos-fieldset") :]
    assert "Team" in legend[:400]
    assert "No Chief of Staff" not in legend[:800]
    assert "reorderMembers" in helpers
    assert "firstAgentLeadId" in helpers
    assert "FIRST_AGENT_VALUE" in helpers
    assert "application/x-swarm-team-roster-index" in helpers


def test_team_lead_picker_covered_by_frontend_tests():
    test = COMPOSER_TEST.read_text(encoding="utf-8")
    roster = ROSTER_TEST.read_text(encoding="utf-8")
    assert "First agent" in test
    assert "roster-index" in test
    assert "ROSTER_DRAG_MIME" in test
    assert "reordering member 2" in test
    assert "team-roles-drop-zone" in test
    assert "firstAgentLeadId" in roster
    assert "reorderMembers" in roster

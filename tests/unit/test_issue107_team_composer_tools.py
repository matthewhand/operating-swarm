"""Issue #107: Team composer Tools pane (handoff/as_tool/MCP)."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
TEAM_ROSTER = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"
ROSTERS = REPO / "src" / "swarm" / "core" / "team_rosters.py"
COMPOSER_TEST = (
    REPO / "webui" / "frontend" / "src" / "components" / "__tests__" / "TeamComposer.test.tsx"
)
ROSTER_TEST = REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "teamRoster.test.ts"


def test_tools_pane_replaces_wires_fieldset():
    src = COMPOSER.read_text(encoding="utf-8")
    helpers = TEAM_ROSTER.read_text(encoding="utf-8")
    backend = ROSTERS.read_text(encoding="utf-8")
    assert "team-tools-drop-zone" in src
    assert "team-tools-pane" in src
    assert "drop tools here" in src
    assert "TOOL_DRAG_MIME" in src
    assert "Per-team openai-agents wiring" not in src
    assert "gate is unwired" not in src
    assert 'toggle toggle-sm' not in src
    assert "team-roles-pane" in src
    assert "First agent" in src
    assert "AVAILABLE_AGENT_KINDS" in src
    assert "type TeamTool" in helpers
    assert "application/x-swarm-team-tool" in helpers
    assert "deriveWiresFromTools" in helpers
    assert "SECRET_MCP_TOOL_KEYS" in helpers
    assert "normalize_tool" in backend
    assert "derive_wires_from_tools" in backend
    assert "secret-shaped" in backend


def test_tools_pane_covered_by_frontend_and_helper_tests():
    test = COMPOSER_TEST.read_text(encoding="utf-8")
    roster = ROSTER_TEST.read_text(encoding="utf-8")
    assert "team-tools-drop-zone" in test
    assert "team-tool-handoff-to" in test
    assert "lock github to jeeves" in test
    assert "derived wires" in test
    assert "parseTeamTool" in roster
    assert "secret MCP" in roster

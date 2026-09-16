"""Issue #106: Team composer tabs agent types; no per-row kind badges."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
COMPOSER_TEST = (
    REPO / "webui" / "frontend" / "src" / "components" / "__tests__" / "TeamComposer.test.tsx"
)


def test_available_agents_use_kind_tabs_without_row_badges():
    src = COMPOSER.read_text(encoding="utf-8")
    assert "AVAILABLE_AGENT_KINDS" in src
    assert "AVAILABLE_AGENT_KIND_LABEL" in src
    assert "defaultAvailableAgentKind" in src
    assert "activeAgentKind" in src
    assert "<Tabs" in src
    assert "{KIND_LABEL" not in src
    assert "kindBadgeType" not in src
    assert "(['api', 'cli', 'remote'] as const).map" not in src
    assert "os-scrollable-picker-list" in src
    assert "available-agents-scroller" in src
    assert "max-h-[22rem]" in src
    available = src.split('aria-label="Available agents list"', 1)[1].split("</section>", 1)[0]
    assert "max-h-40 overflow-y-auto" not in available
    assert "os-scrollable-picker-list" not in available
    assert "First agent" in src
    assert "team-roles-pane" in src
    assert "handoff" in src and "as_tool" in src
    assert "TeamTool" not in src


def test_kind_tabs_covered_by_frontend_tests():
    test = COMPOSER_TEST.read_text(encoding="utf-8")
    assert "tabs available agents by kind without per-row KIND_LABEL badges" in test
    assert "defaults to the first non-empty kind tab when API is empty" in test
    assert "selectAgentKindTab" in test
    assert "queryByText('API')" in test
    assert "First agent" in test
    assert "ROSTER_DRAG_MIME" in test
    assert "team-roles-drop-zone" in test

"""REQ-149: Long agent/blueprint form lists — max-height + scroll."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
SETTINGS_SHEET_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
TEAM_COMPOSER_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
REMOTES_SETTINGS_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "RemotesSettings.tsx"
AGENT_EDITOR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentEditor.tsx"


def test_index_css_scrollable_picker_utility():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-scrollable-picker-list" in css
    assert ".os-capped-list" in css
    assert "overflow-y: auto;" in css
    assert "18rem" in css  # ~288px / 8-10 rows


def test_settings_sheet_lists_are_capped():
    tsx = SETTINGS_SHEET_TSX.read_text(encoding="utf-8")
    # Blueprints list
    assert 'aria-label="Blueprints"' in tsx
    assert 'os-scrollable-picker-list' in tsx
    # Configured remotes list
    assert 'aria-label="Configured remotes"' in tsx
    # Configured LLM profiles list
    assert 'aria-label="Configured LLM profiles"' in tsx


def test_team_composer_roster_and_agents_are_capped():
    tsx = TEAM_COMPOSER_TSX.read_text(encoding="utf-8")
    assert 'aria-label="Roster members"' in tsx
    assert 'os-scrollable-picker-list' in tsx
    assert 'aria-label="Available agents list"' in tsx
    assert "max-h-[22rem]" in tsx
    assert "overflow-y-auto" in tsx
    # Issue #100: kind groups share the pane scroller; no inner overflow-y.
    available = tsx.split('aria-label="Available agents list"', 1)[1]
    available = available.split("</section>", 1)[0]
    assert "os-scrollable-picker-list" not in available
    assert "overflow-y-auto" not in available.split(">", 1)[1]
    assert "max-h-40" not in available


def test_remotes_settings_bots_list_is_capped():
    tsx = REMOTES_SETTINGS_TSX.read_text(encoding="utf-8")
    assert 'os-scrollable-picker-list' in tsx


def test_agent_editor_has_internal_scroll():
    tsx = AGENT_EDITOR_TSX.read_text(encoding="utf-8")
    assert 'id="os-agent-editor"' in tsx
    assert 'overflow-y-auto' in tsx

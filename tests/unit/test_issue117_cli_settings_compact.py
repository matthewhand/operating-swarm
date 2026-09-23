"""#117 — CLI agents Settings compact list + hover settings popup."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
PANE = REPO / "webui" / "frontend" / "src" / "components" / "CliAgentsSettingsPane.tsx"
TEST = REPO / "webui" / "frontend" / "src" / "components" / "__tests__" / "CliAgentsSettingsPane.test.tsx"
CSS = REPO / "webui" / "frontend" / "src" / "index.css"
HELPERS = REPO / "webui" / "frontend" / "src" / "lib" / "cliAgents.ts"


def test_pane_keeps_rate_limit_fields_behind_settings_popup():
    pane = PANE.read_text(encoding="utf-8")
    css = CSS.read_text(encoding="utf-8")
    helpers = HELPERS.read_text(encoding="utf-8")

    assert "os-cli-agent-row" in pane
    assert "os-cli-settings-btn" in pane
    assert "Settings for ${row.name}" in pane or "Settings for ${" in pane
    assert "Show unavailable" in pane
    assert "os-cli-hop-prefs" in pane
    assert "<details" in pane
    assert "ProviderRateLimitFields" in pane
    # Mounted only after the row's settings popover is open.
    assert "{open ? (" in pane
    assert "not-detected" in pane
    assert "compactCliRows" in helpers
    assert "focusedCliName" in helpers

    assert ".os-cli-settings-btn" in css
    assert "@media (hover: hover) and (pointer: fine)" in css
    assert ".os-cli-agent-row:hover .os-cli-settings-btn" in css
    assert ".os-cli-agent-row:focus-within .os-cli-settings-btn" in css

    for blob in (pane, helpers):
        assert ":8001" not in blob
        assert "sk-" not in blob
        assert "ghp_" not in blob
        assert "Discord" not in blob
        assert "Omarchy" not in blob
    assert "Discord" not in css
    assert "Omarchy" not in css


def test_frontend_covers_hover_undetected_and_focus_provider():
    test = TEST.read_text(encoding="utf-8")
    assert "keeps rpm/tpm inputs out of the document until settings open" in test
    assert "Settings for grok" in test
    assert "not-detected" in test
    assert "cli:grok" in test
    assert "Show unavailable" in test

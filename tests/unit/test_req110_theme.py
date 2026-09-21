"""REQ-110: Theme — Settings light/dark/system + optional navbar toggle (Fixes #479)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
THEME_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "theme.ts"
THEME_TOGGLE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "ThemeToggle.tsx"
SETTINGS_SHEET_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
APP_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "App.tsx"


def test_theme_module_contracts():
    ts = THEME_TS.read_text(encoding="utf-8")
    assert "'system'" in ts
    assert "'swarm_theme_navbar'" in ts
    assert "resolveSystemTheme" in ts
    assert "resolveTheme" in ts
    assert "subscribeSystemTheme" in ts
    assert "nextTheme" in ts
    assert "initialNavbarThemeVisible" in ts


def test_app_theme_never_sets_data_theme_to_system():
    app = APP_TSX.read_text(encoding="utf-8")
    assert "applyDocumentTheme(resolveTheme(initialTheme()))" in app
    assert "theme === 'dark' ? 'dark' : 'light'" in app
    assert "data-theme" in app
    assert "themePreference" in app
    assert "resolvedTheme" in app


def test_settings_sheet_has_general_visuals_and_navbar_toggle():
    settings = SETTINGS_SHEET_TSX.read_text(encoding="utf-8")
    assert "'general'" in settings
    assert "Visuals" in settings
    assert 'value="system"' in settings
    assert "Show theme control in top bar" in settings
    assert "THEME_NAVBAR_SET_EVENT" in settings


def test_theme_toggle_respects_navbar_visibility_and_cycles():
    toggle = THEME_TOGGLE_TSX.read_text(encoding="utf-8")
    assert "THEME_NAVBAR_SET_EVENT" in toggle
    # #847: the visibility helper is named for the navbar-mode axis now —
    # same contract (the toggle returns null when not visible).
    assert "!isNavbarThemeToggleVisible(mode, theme)" in toggle
    assert "nextTheme" in toggle

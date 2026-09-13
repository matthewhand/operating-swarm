"""REQ-72 chrome contracts already on main (overlays, remotes panes, roles).

Tests only. Locks shipped Grok rail / settings / remotes / roles behavior
from #322 / #320 / #318 / #334 / #364 so a regression fails CI. Does not
rewrite product code, CI workflows, or golden-journey.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SPA_APP = REPO / "webui" / "frontend" / "src" / "App.tsx"
SETTINGS_SHEET = REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
REMOTES_LIB = REPO / "webui" / "frontend" / "src" / "lib" / "remotes.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
PLUGINS_POPUP = REPO / "webui" / "frontend" / "src" / "components" / "PluginsPopup.tsx"
SEARCH = REPO / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"
DJANGO_SETTINGS = REPO / "src" / "swarm" / "templates" / "settings_dashboard.html"
DJANGO_SIDEBAR = REPO / "src" / "swarm" / "static" / "js" / "agent_sidebar.js"


def test_spa_mounts_overlays_as_siblings_of_chat_routes():
    """#364 / #322 / #320: Settings + Search overlay chat; ChatPage stays routed."""
    app = SPA_APP.read_text(encoding="utf-8")
    assert "<SearchPalette" in app
    assert "<SettingsSheet" in app
    assert 'path="/chat"' in app
    assert "element={<ChatPage />}" in app
    # Overlays are not route replacements — chat is not unmounted for settings.
    assert 'path="/settings"' not in app
    assert "Navigate to=\"/settings\"" not in app


def test_settings_remotes_are_opt_in_not_live_lan():
    """REQ-59: remotes are opt-in; no default kind cards; no live LAN hosts in the sheet."""
    sheet = SETTINGS_SHEET.read_text(encoding="utf-8")
    assert "Add remote" in sheet
    assert "fetchRemotes" in sheet
    assert "RemoteOperatePane" in sheet
    assert "OpenMousBot" in REMOTES_LIB.read_text(encoding="utf-8")
    assert "placeholder remote" not in sheet
    assert "remotes API has not landed" not in sheet
    assert "label: 'OMB'" not in sheet
    assert ":8001" not in sheet
    assert "198.51.100.30" not in sheet


def test_rail_plugins_overlay_is_empty_honest():
    """#805: Plugins is a search overlay with honest empty copy, not a live LAN catalog."""
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    popup = PLUGINS_POPUP.read_text(encoding="utf-8")
    assert "<PluginsPopup" in sidebar
    assert "pluginsOpen" in sidebar
    assert 'data-testid="os-plugins-overlay"' in popup
    assert 'aria-label="Plugins"' in popup
    assert "No tools." in popup
    assert "Connect a server in Manage…" in popup
    assert "Showing the shipped catalog until MCP servers are connected." in popup
    assert "No plugins installed." not in sidebar
    assert "No plugins installed." not in popup
    assert 'aria-labelledby="os-plugins-title"' not in sidebar
    assert 'aria-labelledby="os-plugins-title"' not in popup
    assert ":8001" not in popup


def test_search_palette_has_bots_and_actions_tabs():
    """REQ-17 / #322: Search overlay tabs include Bots + Actions."""
    search = SEARCH.read_text(encoding="utf-8")
    for tab in ("All", "Messages", "Bots", "Groups", "Files", "Links", "Routines", "Actions"):
        assert f"'{tab}'" in search
    assert "Toggle theme" in search
    assert "overlay: 'blueprints'" in search
    assert "overlay: 'teams'" in search


def test_django_operator_dump_is_not_the_spa_remotes_sheet():
    """Django /settings/ stays the operator dump; remotes sheet is SPA-only."""
    html = DJANGO_SETTINGS.read_text(encoding="utf-8")
    assert "modal-end" not in html
    assert "remotes API has not landed" not in html
    js = DJANGO_SIDEBAR.read_text(encoding="utf-8")
    assert "No plugins installed." not in js
    assert "chief_of_staff" in js

"""REQ-72 (#417) chrome contracts for shipped Grok rail / remotes stub / settings.

Tests only. Locks merged-on-main behavior (PRs #318, #319, #320, #322, #331, #342)
so a later SPA rewrite cannot silently drop the stub split or dual hostname keys.
Does not cover in-flight PRs (344, 370, 383, 400, 403, …).
"""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO = Path(__file__).resolve().parents[2]
SETTINGS_SHEET = REPO / "webui" / "frontend" / "src" / "components" / "SettingsSheet.tsx"
REMOTES_CATALOG_PANE = (
    REPO / "webui" / "frontend" / "src" / "components" / "settings" / "panes" / "RemotesCatalogPane.tsx"
)
REMOTES_LIB = REPO / "webui" / "frontend" / "src" / "lib" / "remotes.ts"
SEARCH_PALETTE = REPO / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
APP = REPO / "webui" / "frontend" / "src" / "App.tsx"
HOSTNAME = REPO / "webui" / "frontend" / "src" / "lib" / "hostname.ts"
SETTINGS_PREFS = REPO / "webui" / "frontend" / "src" / "lib" / "settingsPrefs.ts"
TEAM_ROSTERS = REPO / "webui" / "frontend" / "src" / "lib" / "teamRosters.ts"


def test_settings_remotes_are_opt_in_not_default_kind_cards():
    """REQ-59/62: empty remotes catalog + Add remote; OpenMousBot operate; never OMB."""
    src = SETTINGS_SHEET.read_text(encoding="utf-8") + REMOTES_CATALOG_PANE.read_text(encoding="utf-8")
    labels = REMOTES_LIB.read_text(encoding="utf-8")
    assert "Add remote" in src
    assert "fetchRemotes" in src
    assert "RemoteOperatePane" in src
    assert "placeholder remote" not in src
    assert "remotes API has not landed" not in src
    assert "OpenMousBot" in labels
    assert "label: 'OMB'" not in src
    assert "name: 'OMB'" not in src


def test_search_palette_bot_rows_spa_navigate_chat():
    """#322: choosing a bot uses navigate('/chat?blueprint='); Django actions assign()."""
    src = SEARCH_PALETTE.read_text(encoding="utf-8")
    assert "href: `/chat?blueprint=${encodeURIComponent(agent.id)}`" in src
    assert "if (row.href.startsWith('/chat')) navigate(row.href)" in src
    assert "window.location.assign(row.href)" in src
    assert "dispatchToggleTheme()" in src


def test_chat_page_support_default_and_manage_teams():
    """#322 Support default URL; #331/#755 Manage Teams assigns /teams/#<id>."""
    src = chat_surface()
    assert "next.set('blueprint', SUPPORT_AGENT_ID)" in src
    assert "${MANAGE_TEAMS_HREF}#${encodeURIComponent(teamFromUrl)}" in src
    assert "Nothing to compact yet" in src
    assert "Compact failed" in src


def test_sidebar_team_hide_id_and_plugins_popup():
    """#342 team hide uses teamHideId; #805 Plugins mounts PluginsPopup; REQ-82 menu labels."""
    src = SIDEBAR.read_text(encoding="utf-8")
    menu = RAIL_MENU.read_text(encoding="utf-8")
    assert "teamHideId(team.id)" in src
    assert "<PluginsPopup" in src
    assert "pluginsOpen" in src
    assert "No plugins installed." not in src
    assert 'aria-label="Open agents sidebar"' not in src  # REQ-54: hamburger removed
    # Unpin / Delete / Edit live in the menu builder, not inline rail JSX.
    assert "id: 'unpin', label: 'Unpin'" in menu
    assert "if (opts.pinned)" in menu
    assert "id: 'delete'" in menu
    assert "label: 'Delete'" in menu
    assert "danger: true" in menu
    assert "label: 'Edit Profile'" in menu
    assert "opts.kind === 'cli'" in menu
    assert "id: 'edit'" in menu


def test_app_mobile_rail_and_settings_event():
    """REQ-54 tucked rail + #334 hover-edit opens settings via OPEN_SETTINGS_EVENT."""
    src = APP.read_text(encoding="utf-8")
    assert "OPEN_SETTINGS_EVENT" in src
    assert "setSettingsDetail" in src
    assert "useLeftEdgeSwipe" in src
    assert "SwipeHint" in src
    assert 'aria-label="Open agents sidebar"' not in src


def test_hostname_rail_and_settings_keys_are_distinct():
    """#322 rail `swarm_hostname` vs #320 settings `swarm_hostname_override`."""
    rail = HOSTNAME.read_text(encoding="utf-8")
    sheet = SETTINGS_PREFS.read_text(encoding="utf-8")
    assert "swarm_hostname" in rail
    assert "swarm_hostname_override" in sheet
    assert "HOSTNAME_STORAGE_KEY = 'swarm_hostname'" in rail
    assert "HOSTNAME_OVERRIDE_KEY = 'swarm_hostname_override'" in sheet


def test_manage_teams_href_is_django_teams():
    src = TEAM_ROSTERS.read_text(encoding="utf-8")
    assert "MANAGE_TEAMS_HREF = '/teams/'" in src
    assert "MANAGE_TEAMS_VALUE = '__manage__'" in src
    assert "def teamHideId" not in src
    assert "export function teamHideId" in src

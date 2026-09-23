"""REQ-130 and REQ-152 unit tests.

REQ-130 (#520):
- Left-click on local team or remote with configured Chief of Staff opens chat directly.
- Fallback: if no CoS marked, opens first/primary member.
- Right-click context menu provides "Select Agent" which opens member picker dialog.

REQ-152 (#560):
- Team dropdown in chat header has disabled visual separator + "Manage Team" option.
- Navigates to /teams/#<team_id> (or /teams/ if no team).
- SessionPicker for teams renders "Manage Team →" footer link targeting /teams/#<team_id>.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SIDEBAR = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_MENU = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
CHAT_PAGE = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
SESSION_PICKER_COMPONENT = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SessionPicker.tsx"
SESSION_PICKER_LIB = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "sessionPicker.ts"

# #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx;
# these pins read the union so the doctrine spans both homes.
_ROWS_RENDER = SIDEBAR.parent / "sidebar" / "rowsRender.tsx"


def _sidebar_text():
    return "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR, _ROWS_RENDER))




def test_req130_session_picker_default_session_helpers():
    """REQ-130: defaultSessionForTeam and defaultSessionForRemote prioritize CoS then first member."""
    src = SESSION_PICKER_LIB.read_text(encoding="utf-8")
    assert "export function defaultSessionForTeam" in src
    assert "export function defaultSessionForRemote" in src
    assert "chief_of_staff" in src
    assert "s.memberId === 'cos'" in src


def test_req130_sidebar_primary_click_direct_nav_no_picker():
    """REQ-130: primary click on team or remote navigates to default session href directly."""
    src = _sidebar_text()
    assert "defaultSessionForTeam(team)" in src
    assert "defaultSessionForRemote(remote)" in src
    assert "def ? navigate(def.href)" in src or "if (def) {\n            navigate(def.href)" in src or "if (def) {" in src


def test_req130_sidebar_context_menu_select_agent():
    """REQ-130: right-click rail menu offers Select Agent and opens the group picker."""
    sidebar = _sidebar_text()
    menu = RAIL_MENU.read_text(encoding="utf-8")
    assert "rowMenuHandlers(hideId, name, hidden, 'team', sessions, team.id)" in sidebar
    assert "rowMenuHandlers(hideId, name, hidden, 'remote', sessions, remote.id)" in sidebar
    assert "onContextMenu" in sidebar
    assert "id: 'select-agent', label: 'Select Agent'" in menu
    assert "id === 'select-agent'" in sidebar
    assert "openGroupPicker(title, sessions)" in sidebar
    # REQ-82 retired the old openMenu(event, hideId, …) call-shape lock.
    assert "openMenu(event, hideId, name, hidden, 'team', sessions)" not in sidebar
    assert "openMenu(event, hideId, name, hidden, 'remote', sessions)" not in sidebar


def test_req152_chat_page_team_dropdown_separator_and_manage():
    """REQ-152 via #755: the composer picker's footer navigates to /teams/#<id>."""
    src = CHAT_PAGE.read_text(encoding="utf-8")
    assert "MANAGE_TEAMS_VALUE" in src
    assert "label: 'Manage teams'" in src
    assert "${MANAGE_TEAMS_HREF}#${encodeURIComponent(teamFromUrl)}" in src


def test_req152_session_picker_manage_team_footer():
    """REQ-152: session picker displays Manage Team link for team groups."""
    src = SESSION_PICKER_COMPONENT.read_text(encoding="utf-8")
    assert "groupKind === 'team'" in src
    assert "Manage Team →" in src
    assert "/teams/#${encodeURIComponent" in src

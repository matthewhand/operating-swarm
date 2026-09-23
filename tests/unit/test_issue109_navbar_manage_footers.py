"""Issue #109: navbar pickers end with a divider then title-case Manage <kind>."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT_PAGE = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
PICKER = REPO / "webui" / "frontend" / "src" / "components" / "NavbarRoutingPicker.tsx"
SESSION_PICKER = REPO / "webui" / "frontend" / "src" / "components" / "CliSessionPicker.tsx"
SESSION_SWITCHER = REPO / "webui" / "frontend" / "src" / "components" / "CliSessionSwitcher.tsx"


def test_routing_picker_renders_manage_divider_and_skips_footer_flyout():
    """#504/#681 moved the Manage action into the shared surfaces' footers
    (palette footer + two-stage dialog footer) — the picker passes the
    footerAction through instead of rendering its own divider flyout."""
    src = PICKER.read_text(encoding="utf-8")
    assert "onManageSettings={footerAction?.onSelect}" in src
    assert "onManage={footerAction?.onSelect}" in src
    assert "manageLabel" in src


def test_chat_page_manage_labels_are_title_case():
    src = CHAT_PAGE.read_text(encoding="utf-8")
    # #836: the picker footers converge on one unified hub label.
    assert "label: 'Manage providers'" in src
    assert "Manage Cli" not in src
    assert "openSettingsSheet({ section: 'providers' })" in src
    # #755: the team seat's picker footer manages teams.
    assert "label: 'Manage teams'" in src
    assert "MANAGE_TEAMS_HREF" in src


def test_session_switcher_has_divider_and_manage_session():
    picker = SESSION_PICKER.read_text(encoding="utf-8")
    switcher = SESSION_SWITCHER.read_text(encoding="utf-8")
    assert 'data-testid="manage-surface-divider"' in picker
    assert 'role="separator"' in picker
    assert "Manage Session" in picker
    assert "onManageSession" in switcher
    assert "openSettingsSheet({ section: 'cli-agents' })" in switcher

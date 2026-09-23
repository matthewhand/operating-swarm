"""REQ-105 chrome contracts: rail Select / New session, shared picker chrome."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
PICKER = REPO / "webui" / "frontend" / "src" / "components" / "SessionPicker.tsx"
SESSIONS = REPO / "webui" / "frontend" / "src" / "lib" / "agentSessions.ts"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"


def test_rail_menu_has_select_and_new_session_for_agents():
    src = SIDEBAR.read_text(encoding="utf-8")
    menu = RAIL_MENU.read_text(encoding="utf-8")
    assert "Select session" in menu
    assert "New session" in menu
    assert "'new-session'" in menu
    # #580: one declared capability (seatCapabilities.seatHasSessions) drives
    # the rail menu AND the navbar — the per-kind booleans were folded away.
    assert "seatHasSessions" in src
    assert "hasSelectSession: seatHasSessions(menu)" in src
    assert "hasNewSession: seatHasSessions(menu)" in src
    assert "openAgentSessionPicker" in src
    # Teams/remotes keep Select Agent; do not pretend we own remote stores.
    assert "Select Agent" in menu
    assert "hasSelectAgent" in src
    assert "openCliSessionPicker" in src
    assert "startNew: true" in src


def test_session_picker_keeps_shared_chrome_and_new_session():
    src = PICKER.read_text(encoding="utf-8")
    assert "os-session-picker" in src
    assert "onNewSession" in src
    assert "New session" in src
    assert "sessionRelativeLabel" in src
    assert "no sessions yet" in src
    # #468 may reuse chrome; this file must not list CLI provider sessions.
    assert "provider" not in src.lower() or "CLI provider" not in src


def test_django_session_client_does_not_list_cli_providers():
    src = SESSIONS.read_text(encoding="utf-8")
    assert "/v1/agents/" in src
    assert "sessions/" in src
    assert "new: true" in src
    assert "cli-agents" not in src
    assert "provider" not in src.lower() or "does not browse CLI provider" in src

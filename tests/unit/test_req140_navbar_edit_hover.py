"""REQ-140: Navbar Edit icon — desktop hide until hover; rail pencils stay retired."""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
AGENT_SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"


def test_index_css_navbar_edit_desktop_hover_and_mobile_visible():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-navbar-edit-btn" in css
    # Default visible for mobile / touch (coarse pointer, hover: none)
    assert "opacity: 1;" in css

    # Desktop hover-reveal query
    assert "@media (hover: hover) and (pointer: fine)" in css
    assert ".os-chat-header__identity .os-navbar-edit-btn" in css
    assert "opacity: 0;" in css
    assert ".os-chat-header__identity:hover .os-navbar-edit-btn" in css


def test_chat_page_navbar_edit_button_classes():
    # #1055: shared chat surface — the edit button lives in ChatHeader now.
    tsx = chat_surface()
    assert "os-chat-header__identity" in tsx
    assert "os-navbar-edit-btn" in tsx
    assert 'aria-label="Edit agent"' in tsx


def test_rail_row_pencils_remain_retired():
    tsx = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    # Rail rows do NOT have edit pencil buttons
    assert "os-agent-row__edit" not in tsx
    assert "Edit row pencil" not in tsx

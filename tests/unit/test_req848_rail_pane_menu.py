"""REQ-848 / #173 — right-click the rail background to create a section.

Right-clicking empty rail space offers "New section"; the new empty section
opens in inline rename. The section-header menu also gains New section. Agents
and pins drag onto section headers to move in (dropOnSection). Behaviour spec
of record (vitest): webui/frontend/src/components/__tests__/RailSections.test.tsx
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "components" / "RailContextMenu.tsx"


def test_req848_pane_menu_creates_empty_section():
    menu = MENU.read_text(encoding="utf-8")
    assert "export function paneMenuItems" in menu
    assert "{ id: 'section-create', label: 'New section', group: 0 }" in menu


def test_req848_section_menu_also_creates():
    menu = MENU.read_text(encoding="utf-8")
    section_block = menu.split("export function sectionMenuItems", 1)[1]
    assert "'section-create'" in section_block


def test_req848_sidebar_wires_context_menu():
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "openPaneMenuAt" in sidebar
    assert "handlePaneMenuSelect" in sidebar
    assert "[data-rail-id], .os-rail-section, .os-pin" in sidebar
    assert "paneMenuItems()" in sidebar


def test_req848_menu_icon_renders():
    menu = RAIL_MENU.read_text(encoding="utf-8")
    assert "'section-create': FolderPlus" in menu
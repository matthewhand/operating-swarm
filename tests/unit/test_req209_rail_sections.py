"""REQ-209 / #689 — sidepane sections are SPA chrome with localStorage persistence.

Source-lock so Move to / Unassigned / collapse / section menu stay on the rail,
not a live :8001 dump, and not a secrets-bearing prefs API for v1.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SECTIONS = REPO / "webui" / "frontend" / "src" / "lib" / "railSections.ts"
MENU = REPO / "webui" / "frontend" / "src" / "lib" / "railContextMenu.ts"
SIDEBAR = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_MENU = REPO / "webui" / "frontend" / "src" / "components" / "RailContextMenu.tsx"
CI = REPO / ".github" / "workflows" / "req209-rail-sections.yml"


def test_sections_persist_locally_and_keep_unassigned():
    text = SECTIONS.read_text(encoding="utf-8")
    assert "swarm_rail_sections" in text
    assert "UNASSIGNED_SECTION_ID" in text
    assert "Unassigned" in text
    assert "Drag agents here" in text
    assert ":8001" not in text
    assert "WAVE" not in text
    assert "ghp_" not in text


def test_rail_menu_has_move_to_and_section_items():
    menu = MENU.read_text(encoding="utf-8")
    assert "'move-to'" in menu
    assert "Move to" in menu
    assert "section-rename" in menu
    assert "section-move-up" in menu
    assert "section-delete" in menu
    rail = RAIL_MENU.read_text(encoding="utf-8")
    # The menu builds per-item testids from the spec id — for 'move-to' this
    # renders data-testid="rail-menu-move-to" at runtime.
    assert "data-testid={`rail-menu-${spec.id}`}" in rail
    sidebar = SIDEBAR.read_text(encoding="utf-8")
    assert "partitionRowsBySection" in sidebar
    assert "createSectionWithAgent" in sidebar
    assert "agent-fav-grid" in sidebar
    fav = sidebar.index("agent-fav-grid")
    sections = sidebar.index("os-rail-sections")
    assert fav < sections


def test_own_diff_ci_exists():
    text = CI.read_text(encoding="utf-8")
    assert "req209" in text.lower() or "REQ-209" in text
    assert "vitest" in text
    assert "pytest" in text
    assert ":8001" not in text

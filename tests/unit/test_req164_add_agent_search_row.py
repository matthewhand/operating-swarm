"""REQ-164: Move Add-agent + up beside Search (free favourites row).

Intent: Keep one-tap Add agent without crowding the favourites / pin row.
Success:
1. + (accessible name "Add agent") sits on the Search row (trailing/right of Search field).
   Not on the favourites/pin grid row.
2. Favourites / pin region uses full width again (no reserved slot for + beside tiles).
3. Click/+ opens the same Add-agent wizard (#478 behaviour).
4. Tap target still usable (~>=44px).
5. Tests verify Search-row + and favourites row has no +.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SIDEBAR_TSX_ROWS = SIDEBAR_TSX.parent / "sidebar" / "RailSections.tsx"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_add_agent_button_in_search_row():
    content = "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TSX, SIDEBAR_TSX_ROWS))

    # Button is inside os-rail-search-row
    assert "os-rail-search-row" in content
    assert "os-search-add-btn" in content
    assert 'aria-label="Add agent"' in content
    assert 'data-testid="add-agent-button"' in content

    # Search row contains both search input and add-agent-button
    search_row_idx = content.find("os-rail-search-row")
    fav_grid_idx = content.find('data-testid="agent-fav-grid"')
    add_btn_idx = content.find('data-testid="add-agent-button"')

    assert search_row_idx != -1
    assert fav_grid_idx != -1
    assert add_btn_idx != -1

    # Add button appears in search row before the fav grid
    assert search_row_idx < add_btn_idx < fav_grid_idx


def test_favourites_row_has_no_add_button():
    content = "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TSX, SIDEBAR_TSX_ROWS))

    # Old favourites button class and section wrapper are gone
    assert "os-fav-add-btn" not in content
    assert "os-fav-section" not in content

    # Favourites grid is unencumbered
    fav_grid_start = content.find('data-testid="agent-fav-grid"')
    nav_list_start = content.find('aria-label="Agent list"')
    fav_grid_section = content[fav_grid_start:nav_list_start]

    assert "add-agent-button" not in fav_grid_section
    assert "setAddWizardOpen" not in fav_grid_section


def test_css_search_add_btn_and_fav_grid_styling():
    css = INDEX_CSS.read_text(encoding="utf-8")

    assert ".os-search-add-btn {" in css
    assert "min-width: 44px;" in css
    assert "min-height: 44px;" in css
    assert ".os-fav-section" not in css
    assert ".os-fav-add-btn" not in css

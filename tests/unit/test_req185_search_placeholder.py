"""REQ-185: Search placeholder is just "Search" (no Ctrl/⌘ in the text)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SEARCH_BAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar" / "SearchBar.tsx"
SEARCH_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"


def test_sidebar_search_placeholder_is_exactly_search():
    sidebar = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    # #705 moved the rail search field into AgentSidebar/SearchBar.tsx; the
    # sidebar keeps no inline placeholder of its own.
    assert 'placeholder="Search"' not in sidebar
    assert "Search Ctrl" not in sidebar
    assert "Search ⌘" not in sidebar
    assert "Search Cmd" not in sidebar
    search_bar = SEARCH_BAR_TSX.read_text(encoding="utf-8")
    assert 'placeholder="Search"' in search_bar
    assert "Search Ctrl" not in search_bar
    assert "Search ⌘" not in search_bar
    assert "Search Cmd" not in search_bar


def test_search_components_placeholder_clean():
    search_bar = SEARCH_BAR_TSX.read_text(encoding="utf-8")
    assert 'placeholder="Search"' in search_bar

    palette = SEARCH_PALETTE_TSX.read_text(encoding="utf-8")
    assert 'placeholder="Search"' in palette

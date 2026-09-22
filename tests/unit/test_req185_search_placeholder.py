"""REQ-185: Search placeholder is just "Search" (no Ctrl/⌘ in the text)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AGENT_SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SEARCH_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"

# #974 deleted the sub-dir SearchBar.tsx; the rail's search affordance lives
# inline in AgentSidebar.tsx as the `os-rail-search` row. Its visible text
# must still be exactly "Search" — shortcut hints belong in the kbd sibling.
RAIL_SEARCH_SNIPPET = 'os-rail-search__placeholder">Search<'


def test_sidebar_search_placeholder_is_exactly_search():
    sidebar = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    assert "Search Ctrl" not in sidebar
    assert "Search ⌘" not in sidebar
    assert "Search Cmd" not in sidebar
    # The rail search affordance renders the bare "Search" text...
    assert RAIL_SEARCH_SNIPPET in sidebar
    # ...with the shortcut in the kbd chip, not in the label.
    kbd_line = next(
        (line for line in sidebar.splitlines() if "os-rail-search__kbd" in line),
        "",
    )
    assert "Ctrl" in kbd_line or "⌘" in kbd_line or "searchShortcut" in kbd_line


def test_search_components_placeholder_clean():
    sidebar = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    assert RAIL_SEARCH_SNIPPET in sidebar

    palette = SEARCH_PALETTE_TSX.read_text(encoding="utf-8")
    assert 'placeholder="Search"' in palette

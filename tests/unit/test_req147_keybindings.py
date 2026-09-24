"""REQ-147: Discoverable keybinding tips & Grok-Bot search parity."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "App.tsx"
FLAGS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "experimental" / "flags.ts"
CMD_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "experimental" / "CommandPalette.tsx"
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SIDEBAR_TSX_ROWS = SIDEBAR_TSX.parent / "sidebar" / "RailSections.tsx"
SEARCH_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
_DOCK = CHAT_PAGE_TSX.parent.parent / "features" / "chat" / "ChatBottomDock.tsx"
KEYBINDING_TIPS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "keybindingTips.ts"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_app_binds_global_cmd_k_search():
    content = APP_TSX.read_text(encoding="utf-8")
    assert "e.key.toLowerCase() === 'k'" in content
    assert "setSearchOpen((prev) => !prev)" in content
    assert "window.addEventListener('keydown', onKey)" in content


def test_command_palette_demoted_and_no_collision():
    flags = FLAGS_TS.read_text(encoding="utf-8")
    # command_palette must default to false unless explicitly turned on
    assert "flag === 'command_palette'" in flags
    assert "raw === 'on' || raw === 'true'" in flags
    assert "return flag !== 'command_palette'" in flags

    cmd_palette = CMD_PALETTE_TSX.read_text(encoding="utf-8")
    # Must require shiftKey or not intercept bare ⌘K / Ctrl+K
    assert "e.shiftKey" in cmd_palette


def test_sidebar_alt_pins_and_tips():
    sidebar = "\n".join(x.read_text(encoding="utf-8") for x in (SIDEBAR_TSX, SIDEBAR_TSX_ROWS))
    # #1088: Alt+Up / Alt+Down sequential navigation — the Alt+1..9 slot model
    # is gone (it collided with native browser tab switching).
    assert "event.altKey" in sidebar
    assert "/^[1-9]$/.test(event.key)" not in sidebar
    assert "computeRailNavSequence" in sidebar
    assert "stepRailNav" in sidebar

    # #1088: the hover digit badge on favourite tiles is retired — the
    # sequential Alt+↑/↓ model has no per-row slot. The CSS class remains
    # only as dead style, so the honest assertion is its absence in markup.
    assert "os-fav-tile__shortcut" not in sidebar

    # Single in-field ⌘K / Ctrl+K chip — do not also append it to the Search label
    assert "searchShortcutLabel" in sidebar
    assert "os-rail-search__kbd" in sidebar
    assert 'placeholder="Search"' not in sidebar  # #705: search lives in SearchBar.tsx
    assert "Search Ctrl" not in sidebar
    assert "Search ⌘" not in sidebar
    assert "Search Cmd" not in sidebar
    assert "first-load-tips" not in sidebar
    assert "os-keybinding-tips alert" not in sidebar


def test_search_palette_footer_tips():
    palette = SEARCH_PALETTE_TSX.read_text(encoding="utf-8")
    assert "os-search-palette__footer" in palette
    assert "os-search-tip" in palette
    assert "Navigate" in palette
    assert "Select" in palette
    assert "Close" in palette
    assert "os-search-palette__kbd" in palette


def test_in_field_unfocused_hints_replace_overlay():
    chat = "\n".join(x.read_text(encoding="utf-8") for x in (CHAT_PAGE_TSX, _DOCK))
    labels = KEYBINDING_TIPS_TS.read_text(encoding="utf-8")
    palette = SEARCH_PALETTE_TSX.read_text(encoding="utf-8")
    css = INDEX_CSS.read_text(encoding="utf-8")

    # #1093 (4): the ↵ send hint is retired (the queued pill carries the
    # enter-interrupt hint); the Esc-to-clear hint stays for typed drafts.
    assert "composer-send-hint" not in chat
    assert "composer-clear-hint" in chat
    assert "KeybindingTips" not in chat
    assert "first-load-tips" not in chat
    assert "searchShortcutLabel" in labels
    assert "!query.trim()" in palette
    assert "os-search-palette__kbd" in palette
    assert ".os-rail-search:hover .os-rail-search__kbd" in css
    assert ".os-rail-search:focus-within .os-rail-search__kbd" not in css
    assert ".os-composer:hover .os-composer__hint" in css
    assert ".os-composer:focus-within .os-composer__hint" in css
    assert ".os-search-palette__field:hover .os-search-palette__kbd" in css

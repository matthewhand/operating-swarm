"""REQ-147: Discoverable keybinding tips & Grok-Bot search parity."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "App.tsx"
FLAGS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "experimental" / "flags.ts"
CMD_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "experimental" / "CommandPalette.tsx"
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
SEARCH_PALETTE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "SearchPalette.tsx"
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
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
    sidebar = SIDEBAR_TSX.read_text(encoding="utf-8")
    # Alt/⌥+1…9 navigation
    assert "event.altKey" in sidebar
    assert "/^[1-9]$/.test(event.key)" in sidebar
    # REQ-172 replaced direct pin indexing with spill-aware targets; the
    # Alt+1…9 navigation is asserted via the current contract.
    assert "hotkeyTargets[idx]" in sidebar
    assert "computeRailHotkeyTargets" in sidebar

    # Hover shortcut badge on favourite tiles
    assert "os-fav-tile__shortcut" in sidebar

    # Single in-field ⌘K / Ctrl+K chip — do not also append it to the Search label
    assert "searchShortcutLabel" in sidebar
    assert "os-rail-search__kbd" in sidebar
    assert 'placeholder="Search"' in sidebar
    assert "Search ${searchShortcut}" not in sidebar
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
    chat = CHAT_PAGE_TSX.read_text(encoding="utf-8")
    labels = KEYBINDING_TIPS_TS.read_text(encoding="utf-8")
    palette = SEARCH_PALETTE_TSX.read_text(encoding="utf-8")
    css = INDEX_CSS.read_text(encoding="utf-8")

    assert "composer-send-hint" in chat
    assert "composer-clear-hint" in chat
    assert "KeybindingTips" not in chat
    assert "first-load-tips" not in chat
    assert "searchShortcutLabel" in labels
    assert "!query.trim()" in palette
    assert "os-search-palette__kbd" in palette
    assert ".os-rail-search:hover .os-rail-search__kbd" in css
    assert ".os-rail-search:focus-within .os-rail-search__kbd" in css
    assert ".os-composer:hover .os-composer__hint" in css
    assert ".os-composer:focus-within .os-composer__hint" in css
    assert ".os-search-palette__field:hover .os-search-palette__kbd" in css

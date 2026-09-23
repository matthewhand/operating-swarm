"""REQ-172: Alt+1–9 spill into top unpinned when favourites < 10."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_HOTKEYS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railHotkeys.ts"
RAIL_HOTKEYS_TEST = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "__tests__" / "railHotkeys.test.ts"


def test_rail_hotkeys_lib_exists_and_exports_spill_logic():
    assert RAIL_HOTKEYS_TS.exists(), "railHotkeys.ts must exist"
    code = RAIL_HOTKEYS_TS.read_text(encoding="utf-8")
    assert "export function computeRailHotkeyTargets" in code
    assert "visiblePins" in code
    assert "orderedRows" in code
    assert "targets.push" in code


def test_rail_hotkeys_unit_tests_cover_all_cases():
    assert RAIL_HOTKEYS_TEST.exists(), "railHotkeys.test.ts must exist"
    code = RAIL_HOTKEYS_TEST.read_text(encoding="utf-8")
    # Must explicitly test 0, 3, and 10 favourites per REQ-172 success criteria
    assert "case 0 favourites" in code
    assert "case 3 favourites" in code
    assert "case 10 favourites" in code


def test_sidebar_integrates_spill_hotkeys():
    sidebar = SIDEBAR_TSX.read_text(encoding="utf-8")
    # Must import and compute hotkey targets
    assert "computeRailHotkeyTargets" in sidebar
    assert "hotkeyTargets" in sidebar

    # Index the spill-aware target list, which itself walks visiblePins in order
    assert "hotkeyTargets[idx]" in sidebar
    assert "visiblePins," in sidebar

    # Must navigate via target.href
    assert "target.href" in sidebar

    # Must pass spillSlot into unpinned rows
    assert "spillSlot" in sidebar
    assert "data-hotkey" in sidebar

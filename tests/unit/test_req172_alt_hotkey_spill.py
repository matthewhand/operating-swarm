"""REQ-172 rail navigation — superseded in form by #1088 (Alt+Up/Alt+Down).

The original REQ-172 contract was Alt+1..9 slot indexing with spill into the
top unpinned rows. #1088 replaced that model (it collided with native browser
tab switching on Linux/Windows) with sequential Alt+Up/Alt+Down over the
rail's visual order. These pins track the surviving intent: a pure nav
sequence module, imported by AgentSidebar, that walks visible pins first.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
RAIL_HOTKEYS_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "railHotkeys.ts"
RAIL_HOTKEYS_TEST = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "__tests__" / "railHotkeys.test.ts"


def test_rail_hotkeys_lib_exists_and_exports_nav_logic():
    assert RAIL_HOTKEYS_TS.exists(), "railHotkeys.ts must exist"
    code = RAIL_HOTKEYS_TS.read_text(encoding="utf-8")
    # #1088: the sequence builder replaced computeRailHotkeyTargets.
    assert "export function computeRailNavSequence" in code
    assert "visiblePins" in code
    assert "orderedRows" in code


def test_rail_hotkeys_unit_tests_cover_all_cases():
    assert RAIL_HOTKEYS_TEST.exists(), "railHotkeys.test.ts must exist"
    code = RAIL_HOTKEYS_TEST.read_text(encoding="utf-8")
    # #1088: sequence construction + boundary clamping (no spill, no wrap).
    assert "computeRailNavSequence" in code
    assert "stepRailNav" in code
    assert "clamps at the boundaries" in code


def test_sidebar_integrates_nav_hotkeys():
    # #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx;
    # #1088: AgentSidebar computes the nav sequence and wires Alt+Up/Down.
    sidebar = "\n".join(
        p.read_text(encoding="utf-8")
        for p in (SIDEBAR_TSX, SIDEBAR_TSX.parent / "sidebar" / "rowsRender.tsx")
    )
    # Must import and compute the nav sequence
    assert "computeRailNavSequence" in sidebar
    assert "hotkeyTargets" in sidebar

    # The listener consumes step targets and navigates via target.href
    assert "stepRailNav" in sidebar
    assert "target.href" in sidebar

    # #1088: slot chrome is retired — no per-row spill slot or digit hotkeys.
    assert "spillSlot" not in sidebar
    assert "data-hotkey" not in sidebar

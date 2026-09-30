"""REQ-172 rail navigation — superseded in form by #1088 (Alt+Up/Alt+Down).

The original REQ-172 contract was Alt+1..9 slot indexing with spill into the
top unpinned rows. #1088 replaced that model (it collided with native browser
tab switching on Linux/Windows) with sequential Alt+Up/Alt+Down over the rail's
visual order.

What this file used to assert, and why none of it survived contact with a
refactor:

* ``test_rail_hotkeys_unit_tests_cover_all_cases`` read
  ``railHotkeys.test.ts`` and asserted ``"clamps at the boundaries" in code`` —
  a test asserting that another test *exists by name*. That is the rotted
  family one layer down: reword a test title and the gate goes red without a
  behaviour change, and delete the test body while keeping the title and it
  stays green. It is gone.
* ``test_rail_hotkeys_lib_exists_and_exports_nav_logic`` asserted
  ``"export function computeRailNavSequence" in code``. Strictly weaker than
  what already exists: ``lib/__tests__/railHotkeys.test.ts`` *imports* the
  function, so a rename or a signature change breaks the vitest suite at
  collection time, whereas the substring keeps passing. Gone.
* ``test_sidebar_integrates_nav_hotkeys`` asserted ``"target.href" in sidebar``
  — the implementation detail of one refactor's variable naming. The refactor
  it broke was an improvement, not a regression. Gone.

What replaced them
------------------
The behaviour is asserted by driving real key events and reading the URL, which
is the only way to tell sequential navigation from slot arithmetic:

* ``webui/frontend/src/lib/__tests__/railHotkeys.test.ts`` imports
  ``computeRailNavSequence`` / ``stepRailNav`` / ``activeRailNavIndex`` and
  asserts the sequence is the rail's visual order with pins first, that there
  is no 9-slot cap, that movement clamps at both boundaries instead of
  wrapping, and that a pinned id is not emitted twice. The clamp case the old
  meta-test looked for by title is there as a real assertion.
* ``webui/frontend/src/components/__tests__/AgentSidebar.test.tsx`` mounts
  ``AgentSidebar``, dispatches a real ``Alt+ArrowDown``, asserts the rail called
  ``preventDefault`` (so the browser does not also scroll), asserts the URL
  moved to the first *pinned* tile rather than the unpinned row, and asserts
  no ``Alt+N`` slot badge renders anywhere — which is the negative half of
  #1088, the retirement of the model this file's name refers to.
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAIL_HOTKEYS_TS = REPO / "webui" / "frontend" / "src" / "lib" / "railHotkeys.ts"
SIDEBAR_TSX = REPO / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"


def test_rail_hotkeys_module_exists():
    """The sequence builder is a real module, not a leftover file.

    The only thing left here that is honest as a source read: the module the
    nav sequence is built in still exists at all. Its exports, its ordering,
    and its boundary behaviour are asserted by importing and calling it in
    ``lib/__tests__/railHotkeys.test.ts``, which fails at collection time on a
    rename and fails on a behaviour change at run time.
    """
    assert RAIL_HOTKEYS_TS.exists(), "lib/railHotkeys.ts is gone"
    assert SIDEBAR_TSX.exists(), "components/AgentSidebar.tsx is gone"

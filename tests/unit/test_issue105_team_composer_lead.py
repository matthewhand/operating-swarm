"""Issue #105: Team lead picker (First agent) and numbered reorderable roster.

The old file's fatal pin was a *copy* check:

    legend = src[src.find("team-cos-fieldset") :]
    assert "Rig Lead" in legend[:400]

Two ways to be wrong at once. It is a window of 400 characters starting at a
marker, so it goes red for any edit that shifts the markup inside that window
and stays green for any edit outside it — including renaming the fieldset. And
it is a literal, so the copy change #1222 brought ("Group chat lead") failed
the suite even though the fieldset still has a legend, still labels itself,
and still explains what the picker does.

The behaviour is asserted by rendering, in
``webui/frontend/src/components/__tests__/TeamComposer.test.tsx``:

* ``labels the coordinator fieldset "Group chat lead" with explanatory copy`` —
  finds the fieldset by testid and asserts both the legend and the hint.
* ``keeps the Team lead picker disabled until agents are added and defaults to
  First agent`` — the sentinel default, by its displayed label *and* its value.
* ``numbers roster members and reordering member 2 to first updates First agent``
  — drops roster member 2 onto position 1 with a real HTML5 drop and asserts
  the numbering, the resulting order, and that the sentinel follows.
* ``keeps an explicit named lead when the roster is reordered`` — the
  regression that motivated it.
* ``shows the 👑 Lead badge on the first roster member only``.

What is left here are the module facts a render cannot see: the roster helper
still owns the reorder maths, the drag payload's MIME type is declared once
rather than spelled at both ends, and the composer consumes the sentinels
instead of re-declaring them.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
COMPOSER = REPO / "webui" / "frontend" / "src" / "components" / "TeamComposer.tsx"
TEAM_ROSTER = REPO / "webui" / "frontend" / "src" / "lib" / "teamRoster.ts"


def _exports(source: str) -> set[str]:
    """Names exported from a TS module — an export, not a substring anywhere."""
    return set(
        re.findall(
            r"export\s+(?:async\s+)?(?:function|const|let|var|class|type|interface)\s+(\w+)",
            source,
        )
    ) | {
        name.strip()
        for group in re.findall(r"export\s*\{([^}]*)\}", source)
        for name in group.split(",")
        if name.strip()
    }


def test_roster_helper_owns_the_reorder_and_the_drag_payload():
    """The roster maths and the drag MIME type live in ``lib/teamRoster.ts``.

    Read as exports and a declared constant. The old pin
    (``assert "application/x-swarm-team-roster-index" in helpers``) is
    satisfied by the same string appearing anywhere in the file, so a rename on
    one side of the drag — which is the actual bug a MIME mismatch is — would
    not have failed it.
    """
    helpers = TEAM_ROSTER.read_text(encoding="utf-8")
    exported = _exports(helpers)
    for name in ("reorderMembers", "firstAgentLeadId", "FIRST_AGENT_VALUE", "NO_COS_VALUE"):
        assert name in exported, (
            f"lib/teamRoster.ts no longer exports {name}; the composer's roster "
            "ordering and its pick sentinels have no single source of truth"
        )

    # The MIME type is declared exactly once, as a named constant.
    mime_constants = re.findall(
        r"(?:const|let)\s+(\w+)\s*(?::[^=]+)?=\s*'application/x-swarm-team-roster-index'",
        helpers,
    )
    assert mime_constants, (
        "the roster drag MIME type is no longer a named constant in teamRoster.ts; "
        "the drag producer and the drop consumer can drift apart"
    )
    assert len(set(mime_constants)) == 1, (
        f"the roster drag MIME type is declared {len(mime_constants)} times"
    )


def test_composer_consumes_the_sentinels_rather_than_redeclaring_them():
    """The composer imports the sentinels; it does not re-spell them.

    #979 replaced the "No Chief of Staff" literal with a ``NO_COS_VALUE``
    sentinel option. What matters is that the picker's value and its label come
    from the one declaration, so a change to either cannot leave the other
    behind. That is a module fact, and it is checked as an import plus a
    redeclaration guard.
    """
    composer = COMPOSER.read_text(encoding="utf-8")
    assert re.search(r"from\s+'[^']*lib/teamRoster'", composer), (
        "TeamComposer no longer imports lib/teamRoster"
    )

    imported = set()
    for group in re.findall(r"import\s*\{([^}]*)\}\s*from\s*'[^']*lib/teamRoster'", composer):
        imported |= {name.strip() for name in group.split(",") if name.strip()}
    for sentinel in ("FIRST_AGENT_VALUE", "NO_COS_VALUE", "ROSTER_DRAG_MIME"):
        assert sentinel in imported, (
            f"TeamComposer does not import {sentinel} from teamRoster; the "
            "picker's value and the drag payload have two owners"
        )
        assert not re.search(rf"(?:const|let)\s+{sentinel}\s*=", composer), (
            f"TeamComposer redeclares {sentinel}; there must be exactly one owner"
        )


def test_composer_keeps_its_roster_and_role_panes():
    """The panes and the delegation toggles are still rendered by the composer.

    Presence checks on stable, non-copy hooks. The user-facing copy ("First
    agent", "Chief of Staff", "Rig Lead") is deliberately *not* pinned here: it
    is rebranded on its own schedule and it is asserted where it is
    user-visible, by the render tests cited in the module docstring.
    """
    composer = COMPOSER.read_text(encoding="utf-8")
    for hook in ("team-roles-pane", "team-cos-fieldset", "roster-index"):
        assert hook in composer, f"the composer's {hook} surface is gone"
    # Delegation wiring is the roster's whole point.
    assert "handoff" in composer and "as_tool" in composer
    # The picker's accessible name survives (#979 kept it when the literal
    # "No Chief of Staff" became a sentinel option).
    assert 'aria-label="Chief of Staff"' in composer

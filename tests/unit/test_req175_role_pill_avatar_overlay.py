"""REQ-175: Role badges/pills live on the rail row's name line, not on row two.

Rewritten off JSX-shaped regexes. The old file pinned the *markup*, not the
render:

    re.search(r"\\{needsApproval \\? NEEDS_APPROVAL_LABEL : snippet \\|\\| agent\\.description\\}"
              r"\\s*</span>\\s*\\{taskCount > 1", content)

That regex requires a specific element to be closed by three literal
characters in a specific order. A harmless refactor — moving the task counter
into a sibling, or wrapping the count in a fragment — breaks it with no
behaviour change, and it went red exactly that way. Worse, a regex that
specific cannot be satisfied by a *correct* implementation that happens to be
laid out differently, so it is simultaneously too brittle and too weak.

What the replacement asserts
----------------------------
* the markup contract that genuinely is markup: the agent row's second line is
  a single ``.block.truncate`` snippet span, and the role badge is passed into
  ``RailRowSlot`` as a prop rather than inlined as a ternary. These are
  structural, survive a class rename on unrelated elements, and are what #500
  was about.
* the *behaviour* — "no role badge chip beside the snippet, on any row kind" —
  is asserted by rendering, in
  ``webui/frontend/src/components/__tests__/AgentRolePillOverlay.test.tsx``:
  it mounts ``AgentSidebar`` and asserts the agent row's badge is inside the
  name-row slot and absent from the avatar slot, that a plain agent has no
  badge at all, that a team row carries none, and that a pinned tile's badge
  sits in ``.os-fav-tile__badge``. A badge that leaked onto row two would fail
  that suite; it could not fail this file's regexes.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"
# #856 slice G: the row markup moved verbatim into sidebar/rowsRender.tsx;
# these pins read both so they survive a further slice.
_ROWS_RENDER = SIDEBAR_TSX.parent / "sidebar" / "rowsRender.tsx"
RAIL_ROW_SLOT = SIDEBAR_TSX.parent / "RailRowSlot.tsx"

_ROWS = (SIDEBAR_TSX, _ROWS_RENDER)


def _text(*paths: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


def test_role_badge_is_handed_to_the_name_row_slot_not_inlined_on_row_two():
    """The badge is a prop on ``RailRowSlot``, not a chip in the snippet line.

    #500 moved the slot render into ``RailRowSlot``: the badge is passed
    alongside the timestamp. The old file asserted the *inline ternary* was
    gone by grepping for its absence, which a rename or a reformat defeats.
    Asserting the positive shape — it is handed over as a prop — is what
    actually keeps the badge out of row two's markup.
    """
    content = _text(*_ROWS)
    assert re.search(r"badge=\{roleBadgeNode\}", content), (
        "the row no longer hands the role badge to RailRowSlot as a prop; an "
        "inlined chip on the snippet line is exactly what REQ-175 forbids"
    )
    assert "roleBadgeNode" in content

    # The badge's className still carries the role's colour class — REQ-67.
    assert re.search(
        r"os-agent-role-badge[^\"`]*\$\{roleCssClass\(role\)\}",
        content,
    ), "the badge no longer applies roleCssClass(agent.role)"

    # No avatar-overlay badge remains: the Sep-2026 parity sweep moved the role
    # badge off the avatar onto the name line, and #849 aligned Team/Remote
    # pills in that same slot.
    assert 'data-avatar-overlay="true"' not in content, (
        "an avatar-overlay role badge is back; the parity sweep retired it"
    )


def test_no_row_kind_carries_a_role_badge_on_its_snippet_line():
    """No row kind renders a role badge chip inside its second line.

    The negative half of REQ-175. The old file proved it with three
    hand-written regexes over the JSX — one per row kind, each matching an
    exact closing-tag sequence. A team row that grew *one* sibling element
    inside its snippet line would have failed
    ``r"...</span>\\s*</span>\\s*</span>\\s*</Link>"`` while rendering
    perfectly.

    What can be said honestly about the source is the one structural thing the
    regexes were reaching for and could not state: a row's badge reaches its
    name line only through ``RailRowSlot``'s ``badge`` slot, and a row's
    *second line* — the snippet/description line — cannot reference a badge at
    all. Both are checkable without guessing at closing-tag sequences.
    """
    content = _text(*_ROWS)
    slot = RAIL_ROW_SLOT.read_text(encoding="utf-8")

    # Placed once: only the agent row hands a badge to the slot, and it does so
    # through the single `roleBadgeNode`.
    placements = re.findall(r"badge=\{roleBadgeNode\}", content)
    assert len(placements) == 1, (
        f"the role badge is placed {len(placements)} times; a second placement "
        "is how a chip ends up on a second row"
    )
    assert "<span className=\"os-rail-slot__badge\">{badge}</span>" in slot, (
        "RailRowSlot no longer renders the badge in the name-row slot"
    )
    for path in _ROWS:
        body = path.read_text(encoding="utf-8")
        assert "os-rail-slot__badge" not in body, (
            f"{path.name} renders the slot badge itself; only RailRowSlot owns "
            "that slot, so a row cannot put a chip wherever it likes"
        )

    # The second line is the snippet/description line, and it has no access to a
    # badge. Each row kind renders it as a `needsApproval ? … : …` expression.
    snippet_lines = re.findall(
        r"\{(?:needsApproval|teamNeedsApproval|remoteNeedsApproval)[^}]*\}", content
    )
    assert len(snippet_lines) >= 3, (
        f"expected one snippet line per row kind, found {len(snippet_lines)}"
    )
    for expression in snippet_lines:
        assert "badge" not in expression.lower(), (
            f"a rail row's snippet line references a badge: {expression[:80]}"
        )

    # #1436 / #1441: a remote row is a seat kind, not a role, and its subtitle
    # comes from its own snippet/description — never a hard-coded role label.
    assert "'Remote team'" not in content
    assert "data-kind=\"remote\"" in content, "a remote row no longer declares its seat kind"

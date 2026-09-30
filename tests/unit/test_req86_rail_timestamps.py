"""REQ-86 rail timestamps: a recency stamp beside the name, snippet on row two.

The stylesheet half is read as parsed rules; the component half is delegated to
the render tests that assert what the user actually sees, because a JSX
substring cannot tell a stamp that renders from one that is merely present in
the file.

What used to rot here
---------------------
``assert "snippet || agent.description" in content`` broke the moment the rail
row grew a needs-approval conditional in front of the snippet — no behaviour
changed. And ``assert "tabular-nums" or "nowrap" in css`` was not an assertion
at all: ``or`` returns its first operand, and ``"tabular-nums"`` is a
non-empty string, so the expression was *always* true. It had been passing
unconditionally since it was written. That is the clearest example in this file
of the family's second failure mode — a check that cannot fail.

Where the component behaviour is asserted instead
------------------------------------------------
* ``webui/frontend/src/lib/chatTime.test.ts`` imports ``formatRailTimestamp``
  and asserts its return values (Today / Yesterday / weekday / null for epoch).
  An ``assert "export function formatRailTimestamp(" in content`` pin is
  strictly weaker: it passes on an exported function that always returns
  ``None``.
* ``webui/frontend/src/components/__tests__/railSectionsIntegration.test.tsx``
  reads the rendered rail, asserts ``getAllByTestId('rail-row-timestamp')`` is
  non-empty and that the first stamp reads as a date or clock time.
* ``webui/frontend/src/components/__tests__/AgentRolePillOverlay.test.tsx``
  renders agent and team rows and asserts row two carries the description /
  team snippet, with no role badge painted beside it.
* ``webui/frontend/src/components/__tests__/RailUnreadDot.test.tsx`` asserts
  the unread dot *replaces* the stamp rather than stacking with it.
"""

from pathlib import Path

from helpers.css_rules import declaration, read_css

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui/frontend/src/index.css"


def test_css_defines_rail_timestamp_as_a_nowrapping_secondary_line():
    """The stamp is a nowrap, smaller, muted line beside the row name.

    Scoped to the rule that owns it. The old check was
    ``assert "tabular-nums" or "nowrap" in css`` — always true, and therefore
    never able to fail. The disjunction it meant ("figures don't jitter, or it
    doesn't wrap") now has to actually hold, and it is read off the rule rather
    than off the whole 6,400-line sheet, where a ``nowrap`` on some unrelated
    selector would have satisfied it.
    """
    css = read_css(INDEX_CSS)
    white_space = declaration(css, ".os-rail-timestamp", "white-space")
    assert white_space is not None, (
        ".os-rail-timestamp has no rule at all, so the row's recency is unstyled"
    )
    assert white_space == "nowrap", f"the rail stamp wraps: white-space: {white_space!r}"

    # Secondary to the name: the stamp must read smaller than the row name
    # (.os-rail-row-name is text-sm = 0.875rem) or it competes with it.
    size = declaration(css, ".os-rail-timestamp", "font-size")
    assert size is not None, "the rail stamp sets no font-size"
    assert size.endswith("rem") and float(size.removesuffix("rem")) < 0.875, (
        f"the rail stamp is {size}, not smaller than the 0.875rem row name"
    )
    assert declaration(css, ".os-rail-timestamp", "color"), "the stamp sets no colour"


def test_rail_stamp_does_not_animate():
    """A ticking relative timestamp must not animate.

    The stamp is a `Just now` / `N min ago` / `Today 7:21 AM` label; animating
    it re-flows the rail on every tick. This is a real property the removed
    tautology was standing in for, and it can only be read from the sheet.
    """
    assert declaration(read_css(INDEX_CSS), ".os-rail-timestamp", "animation") is None, (
        "the rail stamp animates; a ticking timestamp re-flows the rail"
    )

"""REQ-140: Navbar Edit icon — desktop hide until hover; rail pencils stay retired.

What rotted here
----------------
This test read ``index.css`` as one flat string and asked whether four
literals appeared anywhere in a ~6,400-line global sheet:

    assert ".os-chat-header__identity .os-navbar-edit-btn" in css
    assert "opacity: 0;" in css
    assert "opacity: 1;" in css

Three ways that is the wrong shape, all of which had already bitten this repo:

1. **It is not scoped.** ``index.css`` declares ``opacity: 1`` in at least
   three unrelated rules. A sheet-wide substring cannot tell the navbar
   pencil's rule from any other, so the assertion could pass with the
   navbar rule deleted.
2. **It pins the selector, not the behaviour.** #1676 moved the pencil out
   of the left lead slot and into the centered agent pill, so the reveal
   correctly re-parented from ``.os-chat-header__identity`` to
   ``.os-agent-pill``. The hover-reveal contract was intact and the test
   went red on a correct refactor — the exact rotted-assertion defect.
3. **It cannot see a value change.** The rule could carry
   ``opacity: 0.4`` and the bare ``"opacity: 0;"`` needle would stop
   matching, but so would a reformat to ``opacity:0``.

So the rule is read now as a *parsed* rule, scoped to the selector, via
``helpers.css_rules`` — the same helper ``test_issue117_cli_settings_compact.py``
uses. The assertion names the property (touch-visible, pointer-hidden until
hover or keyboard focus) and not the container the control happens to sit in.

What the old form could not catch
---------------------------------
* a hover-reveal that had been deleted outright from the sheet, as long as
  some other rule still contained the token ``opacity: 0;``
* ``.os-agent-pill:hover`` losing its reveal while the base rule kept
  ``opacity: 0`` — i.e. a pencil that is invisible on desktop with no pointer
* the transition being dropped

The behavioural half — that the control is reachable by keyboard, not only by
hover — is asserted by rendering in
``webui/frontend/src/pages/__tests__/NavbarIdentityHoverCard.test.tsx`` and
``webui/frontend/src/features/chat/__tests__/ChatHeader.agentPill1676.test.tsx``.
"""

from pathlib import Path

from helpers.css_rules import declaration, declaration_in, read_css, rule_bodies
from helpers.source_surface import chat_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
AGENT_SIDEBAR_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "AgentSidebar.tsx"

DESKTOP_REVEAL = "@media (hover: hover) and (pointer: fine)"
# #1676 re-parented the reveal onto the pill that actually contains the pencil.
PEN = "os-navbar-edit-btn"
CONTAINERS = (".os-agent-pill", ".os-chat-header__identity")


def test_index_css_navbar_edit_desktop_hover_and_mobile_visible():
    """The pencil is always visible on touch, and hover/focus-revealed on pointer.

    Read as parsed rules scoped to the pencil's own selector, so a value
    change fails and an unrelated rule elsewhere in the sheet cannot satisfy
    the assertion.
    """
    css = read_css(INDEX_CSS)

    # Base rule: visible. This is the touch / coarse-pointer case.
    base = declaration(css, f".{PEN}", "opacity")
    assert base is not None, f".{PEN} has no base opacity rule; the pencil is unstyled"
    assert base == "1", f".{PEN} base opacity is {base!r}; touch users must always see it"

    # A transition is part of the contract (a hard toggle is not a reveal).
    assert declaration(css, f".{PEN}", "transition"), (
        f".{PEN} lost its opacity transition, so the reveal no longer animates"
    )

    # Pointer-fine reveal: hidden at rest, shown on hover AND on focus.
    # Scoped to whichever container now holds the pencil.
    hidden_in = [
        c for c in CONTAINERS
        if declaration_in(css, f"{c} .{PEN}", "opacity", within=DESKTOP_REVEAL) == "0"
    ]
    assert hidden_in, (
        "no pointer-fine rule hides the navbar pencil at rest. Either the reveal "
        "was deleted (the pencil is now permanently visible on desktop) or the "
        "pencil moved to a container not listed in CONTAINERS -- update this test "
        "with the new parent rather than re-adding a bare substring check."
    )

    shown = [
        c for c in CONTAINERS
        if declaration_in(css, f"{c}:hover .{PEN}", "opacity", within=DESKTOP_REVEAL) == "1"
        or declaration_in(css, f"{c}:focus-within .{PEN}", "opacity", within=DESKTOP_REVEAL) == "1"
    ]
    assert shown, (
        "the pointer-fine rule hides the pencil but nothing reveals it again on "
        "hover or focus -- it is unreachable without a pointer"
    )


def test_chat_page_navbar_edit_button_classes():
    """#1055: shared chat surface — the edit button lives in ChatHeader now."""
    tsx = chat_surface()
    assert "os-chat-header__identity" in tsx
    assert "os-navbar-edit-btn" in tsx
    assert 'aria-label="Edit agent"' in tsx


def test_rail_row_pencils_remain_retired():
    """Rail rows carry no per-row edit pencil — the rail edits from the header."""
    tsx = AGENT_SIDEBAR_TSX.read_text(encoding="utf-8")
    assert "os-agent-row__edit" not in tsx
    assert "Edit row pencil" not in tsx

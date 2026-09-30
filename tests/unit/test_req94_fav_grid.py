"""REQ-94 favourite grid: 2-up named large tiles, move not copy.

Rewritten off substring pins onto parsed stylesheet reads plus the behavioural
frontend tests that actually assert the rail's pin behaviour.

Two properties are real here, and neither of them is a literal:

1. **The pinned grid is multi-column.** The old pin was
   ``grid-template-columns: repeat(2, minmax(0, 1fr))`` — a *value*, not the
   property. #1262 deliberately replaced the fluid 1fr tracks with fixed
   ``repeat(auto-fill, 5.25rem)`` tracks so a rail resize no longer re-flows the
   tiles; the doctrine (2-up, named, large-avatar) survived, the value did not.
   The pin went red for a no-op change. What matters is that the container
   declares more than one column, anchors the track set so a tile's position
   depends on its index and not on the container width (see the `justify-content`
   assertion below — #1683), and that the tile itself carries no fill of its own.
2. **A pin is a move, not a copy.** That was asserted by
   ``assert "move, not a copy" in pinnedAgents.ts`` — matching a *comment*.
   The behaviour is asserted by ``lib/__tests__/pinnedAgents.test.ts``
   ("drops favourited ids from the rail list (move, not copy)") and by the
   drag tests in ``components/__tests__/AgentSidebar.test.tsx``, which fire real
   drop events and check the pin grid owns the row.
"""

import re
from pathlib import Path

from helpers.css_rules import declaration, read_css

REPO = Path(__file__).resolve().parents[2]
SPA_CSS = REPO / "webui/frontend/src/index.css"
DJANGO_CSS = REPO / "src/swarm/static/css/rest_mode_style.css"

_TRACK = re.compile(r"repeat\(\s*(?P<count>auto-fill|auto-fit|\d+)\s*,")


def _column_capacity(value: str | None) -> int:
    """How many columns a ``grid-template-columns`` value can produce.

    ``repeat(2, …)`` → 2. ``repeat(auto-fill, …)`` → unbounded, which is only
    ever 1 at the container's narrowest. Returns 0 when the declaration is
    missing or a single fixed track.
    """
    if not value:
        return 0
    match = _TRACK.search(value)
    if not match:
        return 1 if "none" not in value else 0
    count = match.group("count")
    return 99 if count in ("auto-fill", "auto-fit") else int(count)


def test_spa_fav_grid_is_multi_up_with_transparent_tiles():
    # The container owns the column count; it must never collapse to one track.
    for selector in (".os-fav-grid",):
        value = declaration(read_css(SPA_CSS), selector, "grid-template-columns")
        assert value, f"{selector} declares no grid-template-columns"
        assert _column_capacity(value) > 1, (
            f"{selector} is single-column ({value!r}) — REQ-94 is a 2-up grid"
        )
    css = read_css(SPA_CSS)
    # #1683: the anchoring is `start`, not `center`, and this assertion used to
    # pin `center` — which is exactly the value that caused the bug this repo
    # keeps rediscovering. With centring, a tile's x is a function of the
    # CONTAINER width: x(i) = (W - tracksWidth)/2 + i*(track+gap). Every pixel
    # of rail resize therefore slid the tiles sideways, and every 1->2->3 column
    # change jumped them — the #1262 "wobble", and the reason #1683's rail can
    # only free-track above the topmost column detent if the grid is left-
    # anchored. With `start`, x(i) = margin + i*(track+gap) depends on the tile's
    # index alone, so a column change appends tracks at the trailing edge and
    # tiles 1 and 2 never move.
    #
    # The old assertion could not catch this: it named a literal, not a
    # property, and `center` was a perfectly reasonable-looking value. The
    # behaviour it should have pinned is measured in a real renderer by
    # `webui/frontend/scripts/measure-pinned-grid.mjs`, which fails if any
    # pinned tile's x moves across a 88-420px sweep, and asserted arithmetically
    # in `RailDetentByPinCount1683.test.ts` (which recomputes the column
    # detents from these very declarations).
    assert declaration(css, ".os-fav-grid", "justify-content") == "start"

    # Scoped to the tile's own rule. The old `"background: transparent" in
    # tile_block` split on `.os-fav-tile {` and `}`, which matched whichever
    # variant came first in the file.
    assert declaration(css, ".os-fav-tile", "background") == "transparent"

    # The hover/active/drop fill is a separate rule, so a base-tile fill and a
    # selected-tile fill cannot be confused for one another.
    assert declaration(css, ".os-fav-grid--active", "border-color")
    assert declaration(css, ".os-fav-grid--bare", "height") == "0"
    assert declaration(css, ".os-fav-grid--bare .os-fav-grid__hint", "display") == "none"

    # The tile's name is clamped to two lines: a single nowrap line hard-clipped
    # every name longer than ~5 characters at tile width (#934).
    assert declaration(css, ".os-fav-tile__name", "-webkit-line-clamp") == "2"
    # Role colour on a pin is held by the badge corner, not the tile body.
    assert declaration(css, ".os-fav-tile__badge", "position") == "absolute"


def test_spa_rail_collapses_the_grid_to_one_column_in_avatar_only_mode():
    """REQ-116: below the avatar-only threshold the grid is a single column.

    This is the one place a 1-column grid is correct, so it is asserted as its
    own scoped rule rather than being defeated by the multi-column check above.
    """
    value = declaration(
        read_css(SPA_CSS), ".os-agent-sidebar--avatar-only .os-fav-grid", "grid-template-columns"
    )
    assert value, "avatar-only mode declares no .os-fav-grid track"
    assert _column_capacity(value) == 1


def test_django_mirror_keeps_two_up_named_tiles():
    """The legacy static sidebar keeps the literal 2-up grid REQ-94 named."""
    css = read_css(DJANGO_CSS)
    value = declaration(css, ".os-agent-pin-grid", "grid-template-columns")
    assert value, "the Django sheet declares no track for the pinned tile grid"
    assert _column_capacity(value) == 2, f"Django mirror is not 2-up ({value!r})"
    # A 2.5rem round avatar on a named tile: the two properties the old
    # substring test was reaching for, read off their own rules.
    assert declaration(css, ".os-agent-tile__name", "white-space") == "nowrap"
    assert declaration(css, ".os-agent-tile__link .os-agent-dot", "border-radius") == "999px"

    js = (REPO / "src/swarm/static/js/agent_pin_grid.js").read_text(encoding="utf-8")
    assert re.search(r"dropEffect\s*=\s*[\"']move[\"']", js)
    assert "swarm_pinned_agents" in (
        REPO / "src/swarm/static/js/agent_sidebar.js"
    ).read_text(encoding="utf-8")
    assert "Favourites" not in css
    assert "Favourites" not in js

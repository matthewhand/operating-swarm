"""REQ-28 chrome contracts: CoS rail is not support/gate/skeptic; team badge exists.

Rewritten off substring pins onto parsed stylesheet reads.

The old test asserted two hex literals — ``"#4f8ec9"`` for CoS and
``"#3d8f8a"`` for support — anywhere in two stylesheets. That is wrong twice
over:

* it is a *palette* pin, not a *property* pin. Those hexes were already
  replaced once (the D3 WCAG sweep moved the SPA set to ``#90b8dd`` /
  ``#6fc2bc``) with no behaviour change, which is why this file was red.
* it cannot express the actual REQ-28 rule. ``"#4f8ec9" in css and
  "#3d8f8a" in css`` is satisfied by two unrelated declarations anywhere in a
  700-line file. The doctrine is "the CoS badge is a colour the operator
  cannot mistake for support, gate, or skeptic" — which is a statement about
  the *resolved colours of the badge rules*, not about two strings.

What the replacement catches that the old one could not: a CoS badge that
silently adopts support's colour (or gate's, or skeptic's) still passes the old
test as long as both hexes appear somewhere; it fails here. Equally, a palette
retune that keeps every role distinct is no longer a false failure.
"""

import re
from pathlib import Path

from helpers.css_rules import declaration, read_css

REPO = Path(__file__).resolve().parents[2]
SPA_CSS = REPO / "webui/frontend/src/index.css"
DJANGO_CSS = REPO / "src/swarm/static/css/rest_mode_style.css"
SIDEBAR_JS = REPO / "src/swarm/static/js/agent_sidebar.js"

# The roles REQ-28 requires a reader to tell apart at a glance. ``gate`` and
# ``belay`` share one rule by design (a gatekeeper seat is a belay seat), so
# they are one *group*, not two: the distinctness rule is across groups, never
# within one. ``remote`` is a seat *kind* rather than a role, but it is painted
# through the same badge channel, so it joins the comparison.
ROLE_GROUPS = (
    ("chief_of_staff",),
    ("support",),
    ("admin",),
    ("gate", "belay"),
    ("skeptic",),
    ("advisor",),
    ("suggestions",),
    ("engineer",),
    ("remote",),
)

_ROLE_RULE = re.compile(r'\.os-agent-role-badge\[data-(?:role|kind)="([^"]+)"\]')


def _badge_colours(css: str, *, light: bool = False) -> dict[str, str]:
    """``{role: colour}`` for the badge rules, split by theme."""
    prefix = '[data-theme="light"] ' if light else ""
    out: dict[str, str] = {}
    for match in _ROLE_RULE.finditer(css):
        role = match.group(1)
        selector = f"{prefix}.os-agent-role-badge[data-role=\"{role}\"]"
        kind_selector = f"{prefix}.os-agent-role-badge[data-kind=\"{role}\"]"
        colour = declaration(css, selector, "color") or declaration(
            css, kind_selector, "color"
        )
        if colour:
            out[role] = colour
    return out


def _group_colour(colours: dict[str, str], group: tuple[str, ...]) -> str | None:
    for role in group:
        if role in colours:
            return colours[role]
    return None


def test_cos_badge_colour_is_distinct_from_every_other_role():
    """REQ-28: every role badge is its own colour; CoS is not a support twin."""
    for label, path in (("SPA", SPA_CSS), ("Django", DJANGO_CSS)):
        colours = _badge_colours(read_css(path))
        for role in ("chief_of_staff", "support", "gate", "skeptic", "advisor"):
            assert role in colours, f"{label}: no badge colour declared for {role}"
        seen: dict[str, tuple[str, ...]] = {}
        for group in ROLE_GROUPS:
            colour = _group_colour(colours, group)
            if colour is None:
                continue  # the legacy static sheet never painted this seat kind
            twins = [g for g, c in seen.items() if c == colour]
            assert not twins, (
                f"{label}: {list(group)} share the badge colour {colour} with {twins} — "
                "an operator cannot tell the two roles apart"
            )
            seen[colour] = group
        assert _group_colour(colours, ("chief_of_staff",)) != _group_colour(
            colours, ("support",)
        )


def test_spa_badge_palette_is_defined_for_both_themes():
    """The SPA ships a dark and a light role set; both must be complete.

    A missing light-theme override renders the dark-theme colour on the light
    rail, which the single-theme pin could not see. The dark rule is the
    default theme, so a missing *dark* rule falls back to the base badge
    colour and every role looks identical.
    """
    dark = _badge_colours(read_css(SPA_CSS))
    light = _badge_colours(read_css(SPA_CSS), light=True)
    for group in ROLE_GROUPS:
        for role in group:
            if role == "remote":
                continue  # painted late, light override exists but is checked below
            assert role in dark, f"no dark-theme badge colour for {role}"
            assert role in light, f"no light-theme badge colour for {role}"
            assert dark[role] != light[role], (
                f"{role} uses the same colour in both themes; the light rail cannot "
                "clear WCAG AA with the dark-theme value"
            )
    assert dark.get("remote"), "no dark-theme badge colour for remote seats"
    assert light.get("remote"), "no light-theme badge colour for remote seats"


def test_role_colour_stays_on_the_badge_only():
    """AGENTS.md: role colour belongs only to ``.os-agent-role-badge``.

    Scoped read: the only selectors that may scope a colour by ``data-role``
    are badge selectors. The old whole-file substring could not tell a badge
    rule from a rail-row rule that had grown role colouring.
    """
    for label, path in (("SPA", SPA_CSS), ("Django", DJANGO_CSS)):
        css = read_css(path)
        offenders = [
            prelude.strip()
            for prelude in re.findall(r"([^{}]+)\{", css)
            if "data-role" in prelude and ".os-agent-role-badge" not in prelude
        ]
        assert not offenders, f"{label}: role colour leaked off the badge into {offenders}"


def test_django_sidebar_fetches_rosters_and_badges_cos():
    """The legacy static sidebar still reads team rosters and paints CoS."""
    js = SIDEBAR_JS.read_text(encoding="utf-8")
    assert "/v1/team-rosters/" in js
    assert "chief_of_staff" in js
    assert "Team" in js
    # Word-bounded: the roster listing endpoint replaced the team listing, and
    # a bare substring would also match the rosters path itself.
    assert not re.search(r"['\"]/v1/teams/", js)

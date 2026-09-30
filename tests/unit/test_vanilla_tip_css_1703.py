"""The CSS this work appended must survive concurrent appends (#1699/#1700/#1703).

`src/index.css` is appended to by several agents at once, so a mid-file edit is a
merge hazard and a plain grep for a selector is the wrong check — this repo has
four different `white-space: pre-wrap` declarations in that one file. The
assertions below use ``tests/helpers/css_rules.py``, which brace-matches a rule
body and rejects a prefix match (``.os-vanilla-tip`` inside
``.os-vanilla-tip .child``), so a rewritten or truncated rule fails rather than
half-matching.

The second half is the concurrency check: the rules another agent appended in the
same commit window must still parse after this block landed, so "my append did not
land on top of theirs" is a test and not a hope.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from helpers.css_rules import declarations, read_css, rule_bodies  # noqa: E402

CSS = Path(__file__).resolve().parents[2] / "webui/frontend/src/index.css"


def _bodies(selector: str) -> list[str]:
    return rule_bodies(read_css(CSS), selector)


def test_the_vanilla_tip_wrapper_rule_exists_and_is_its_own_rule():
    bodies = _bodies(".os-vanilla-tip")
    assert len(bodies) == 1, f"expected one .os-vanilla-tip rule, got {len(bodies)}"
    assert "padding" in bodies[0]


def test_the_wrapper_padding_matches_the_neighbouring_tip_slots():
    # `.os-role-agent-tip` / `.os-runtime-banner-wrap` are the tips this one sits
    # beside, so it has to line up with them or the stack reads as broken.
    assert declarations(_bodies(".os-vanilla-tip")[0]) == declarations(
        _bodies(".os-role-agent-tip")[0]
    )
    assert declarations(_bodies(".os-vanilla-tip__alert")[0]) == declarations(
        _bodies(".os-role-agent-tip__alert")[0]
    )


#: The namespaced selectors this work owns. Pinned here rather than scraped out
#: of the component: scanning a ``.tsx`` for a literal is the rotted assertion
#: this repo keeps replacing. Renaming a class means editing both places, and the
#: rendered-DOM assertions in
#: ``components/__tests__/VanillaSetupTip.test.tsx`` are what prove the component
#: actually uses them.
VANILLA_SELECTORS = (
    ".os-vanilla-tip",
    ".os-vanilla-tip__alert",
    ".os-vanilla-tip__title",
    ".os-vanilla-tip__body",
    ".os-vanilla-tip__cta",
)


def test_every_owned_selector_has_a_rule():
    for selector in VANILLA_SELECTORS:
        assert _bodies(selector), f"{selector} has no CSS rule"


def test_the_cta_underline_reset_is_present():
    # The CTA is a real link, so it must not carry a text underline competing
    # with the button styling.
    assert "text-decoration" in _bodies(".os-vanilla-tip__cta")[0]


def test_no_raw_hex_in_the_vanilla_block():
    """AGENTS.md §3: theme tokens only. A hex literal here would be the one
    thing in this block a dark-mode proof could not rescue."""
    for selector in VANILLA_SELECTORS:
        body = _bodies(selector)[0]
        assert "#" not in body, f"{selector} has a raw colour literal: {body}"


def test_rules_another_agent_appended_are_still_parseable():
    """#1678's block landed in the same commit window and sits directly above this
    one. A truncated file (a half-written append, a bad merge) shows up here as a
    missing rule, which is the point: the append must not be able to clobber a
    neighbour."""
    for selector in (".os-agent-media-item", ".os-agent-media-thumb"):
        assert _bodies(selector), f"{selector} was lost — the append damaged the file"


def test_the_file_still_ends_with_a_complete_rule():
    """A truncated append leaves an unclosed brace, which `read_css` would happily
    return. Cheap structural guard on the very thing this work did to the file."""
    text = read_css(CSS)
    assert text.count("{") == text.count("}"), "unbalanced braces in index.css"
    assert text.rstrip().endswith("}")

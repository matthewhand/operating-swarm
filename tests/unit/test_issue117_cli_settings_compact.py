"""#117 — CLI agents Settings compact list + hover settings popup.

What rotted here is the clearest example in the repo of the defect class's
*second* failure mode: an assertion that reads comment text.

    assert "Omarchy" not in css

``index.css`` is a 6,400-line global stylesheet. ``Omarchy`` appears in it
once, at line 123, inside a comment explaining that #1227 made the JetBrains
Mono Nerd Font stack the default because "Omarchy/Arch hosts ship that font"
— i.e. a deliberate, documented, *shipped* product decision. The check was
banning a word from a file it has no business policing, and it fired the moment
a font comment was added. A ban that is defeated by an explanatory comment is
not a ban; it is a tripwire.

The rule the author actually meant is "no private, machine-specific detail
leaks into the UI", and that is a *shaped* property: a private LAN address, a
local filesystem path, a home directory. Those are asserted here, on the two
files this test is about, with patterns that cannot match prose.

The behavioural half — that the rate-limit fields are not in the document until
the row's settings popover is open — is asserted by rendering, in
``webui/frontend/src/components/__tests__/CliAgentsSettingsPane.test.tsx``:
it renders the pane, asserts the rpm/tpm inputs are absent from the DOM before
the settings button is pressed, finds the button by its accessible name
"Settings for grok", presses it, and then asserts the fields appear along with
the "not-detected" affordance and the "Show unavailable" toggle.

The CSS half — that the settings button is revealed on hover *and* on keyboard
focus, so it is reachable without a pointer — is a stylesheet property, read
below as parsed rules rather than as substrings.
"""

import re
from pathlib import Path

from helpers.css_rules import declaration, declaration_in, read_css, rule_bodies

REPO = Path(__file__).resolve().parents[2]
PANE = REPO / "webui" / "frontend" / "src" / "components" / "CliAgentsSettingsPane.tsx"
CSS = REPO / "webui/frontend/src/index.css"
HELPERS = REPO / "webui/frontend/src/lib" / "cliAgents.ts"

# Machine-specific facts, not vocabulary. Each is a real leak shape; none of
# them matches an English sentence or a comment explaining a decision.
LEAK_PATTERNS = (
    (r"\b(?:10\.\d{1,3}|192\.168\.|172\.(?:1[6-9]|2\d|3[01])\.)\d{1,3}\.\d{1,3}\b", "a private LAN address"),
    (r"\bubuntu-(?:gtx|max)\b", "a private hostname"),
    (r"(?<![\w.])/(?:home|Users)/[\w.-]+", "a local home directory path"),
    (r"\b(?:sk-(?:proj-|ant-)?[A-Za-z0-9_-]{32,}|gh[pousr]_[A-Za-z0-9]{30,})\b", "a credential"),
)


def _assert_no_machine_specifics(text: str, where: str) -> None:
    for pattern, label in LEAK_PATTERNS:
        match = re.search(pattern, text)
        assert match is None, f"{where} leaks {label}: {match.group(0)}"


def test_settings_pane_ships_no_machine_specific_detail():
    """The pane and its helper carry no private addresses, paths, or secrets.

    Scoped to the two files this feature owns. The old check ran the same
    vocabulary ban over ``index.css``, a global sheet where the word appears in
    a shipped font comment, and over a *comment* in the pane — which is the
    failure mode: a ban defeated by prose.
    """
    _assert_no_machine_specifics(PANE.read_text(encoding="utf-8"), "CliAgentsSettingsPane.tsx")
    _assert_no_machine_specifics(HELPERS.read_text(encoding="utf-8"), "lib/cliAgents.ts")


def test_rate_limit_fields_stay_behind_the_row_popover():
    """The pane has the popover surface the render test drives.

    A structural check on the component's own hooks — the row class, the
    settings button, the per-row popover, the rate-limit field component, and
    the "not-detected" affordance. What the *behaviour* is (those fields absent
    from the document until the button is pressed) is asserted by rendering in
    ``components/__tests__/CliAgentsSettingsPane.test.tsx``; a substring pin can
    only ever prove the tokens exist, not that the gating works.
    """
    pane = PANE.read_text(encoding="utf-8")
    for token in (
        "os-cli-agent-row",
        "os-cli-settings-btn",
        "os-cli-hop-prefs",
        "ProviderRateLimitFields",
        "not-detected",
    ):
        assert token in pane, f"the settings pane no longer has its {token!r} surface"
    # The button carries a per-row accessible name, so it is distinguishable in
    # a list of rows — asserted by the render test as "Settings for grok".
    assert re.search(r"Settings for \$\{", pane), (
        "the settings button's accessible name is no longer per-row"
    )


def test_settings_button_is_reachable_by_hover_and_by_keyboard():
    """Hover *and* focus reveal the button; a pointer must not be required.

    Read as parsed rules. The old checks were four independent substrings, all
    satisfiable by any one of them appearing anywhere in the sheet, and none of
    them able to distinguish "hidden until hover" from "always visible".
    """
    css = read_css(CSS)
    FINE_POINTER = "@media (hover: hover) and (pointer: fine)"

    # Always visible where there is no hover to reveal it (touch rails).
    assert rule_bodies(css, FINE_POINTER), "no fine-pointer media block in the sheet"
    base = declaration(css, ".os-cli-settings-btn", "opacity")
    assert base is not None, "the settings button has no rule of its own"

    # Hidden by default on a fine pointer …
    idle = declaration_in(
        css, ".os-cli-agent-row .os-cli-settings-btn", "opacity", within=FINE_POINTER
    )
    assert idle == "0", (
        f"on a fine pointer the settings button is opacity {idle!r} at rest; it "
        "should be hidden until the row is hovered or focused"
    )
    # … revealed on hover …
    hover = declaration_in(
        css,
        ".os-cli-agent-row:hover .os-cli-settings-btn",
        "opacity",
        within=FINE_POINTER,
    )
    assert hover not in (None, "0"), (
        f"hovering a CLI row does not reveal its settings button (opacity: {hover!r})"
    )
    # … and on focus, so it is reachable from the keyboard alone. This is the
    # half the old substring set could not state: `:focus-within` may be absent
    # while `:hover` is present, and every one of the four original assertions
    # would still pass.
    focus = declaration_in(
        css,
        ".os-cli-agent-row:focus-within .os-cli-settings-btn",
        "opacity",
        within=FINE_POINTER,
    )
    assert focus not in (None, "0"), (
        f"focusing a CLI row does not reveal its settings button (opacity: {focus!r}); "
        "the control is pointer-only"
    )


def test_compact_row_helpers_are_owned_by_the_lib():
    """``lib/cliAgents.ts`` owns the compact-row and focused-row selectors."""
    helpers = HELPERS.read_text(encoding="utf-8")
    for token in ("compactCliRows", "focusedCliName"):
        assert token in helpers, f"lib/cliAgents.ts no longer owns {token}"

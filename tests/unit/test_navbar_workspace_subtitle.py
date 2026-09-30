"""Navbar workspace/folder/branch subtitle under the agent name (#65)."""

from pathlib import Path

from helpers.css_rules import declaration, declarations, read_css, rule
from helpers.source_surface import chat_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
WORKSPACE_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "agentWorkspace.ts"


def test_subtitle_renders_under_agent_name():
    # #1055: shared chat surface — the identity block lives in ChatHeader now.
    tsx = chat_surface()
    assert "os-navbar-identity-text" in tsx
    assert "os-navbar-identity-subtitle" in tsx
    assert "os-navbar-identity-label" in tsx
    assert "navbarWorkspaceSubtitle" in tsx
    assert 'className="os-navbar-identity-subtitle"' in tsx


def test_name_label_is_shrinkable_and_faded_not_hard_truncated():
    """The #255 contract: the name FADES at the right edge, it is not clipped.

    This used to be pinned as the literal class string
    ``"os-navbar-identity-label min-w-0 flex-1"``, which is the canonical
    rotted assertion: it broke on #1715's deliberate swap of ``flex-1`` for
    ``w-full`` (a pre-existing red on main, not a regression from any change
    here) while the behaviour it was proxying — "the label may shrink, and the
    card's width governs it" — stayed intact, and it could not see a *wrong*
    flex value at all, only a differently spelled right one.

    So the claim is now made on the two facts themselves, read from the
    brace-matched rule that sets them:

    * the flex shorthand's SHRINK factor is at least 1, so a long name may
      give way inside the card rather than pushing the controls off the band;
    * the label fills the card's cross axis, so it is not a content-width
      sliver the mask would cut to nothing.

    Both are numbers, so re-tuning them is a deliberate change rather than a
    lucky string match. The rendered class list is owned by the DOM suite
    (``ChatPage.navbarResponsive.test.tsx``), which can actually see it.
    """
    css = read_css(INDEX_CSS)

    label = declarations(rule(css, ".os-navbar-identity-label"))
    assert label.get("min-width") == "0", "a label that cannot shrink overflows the card"
    # `truncate` is Tailwind's hard-clip; the fade mask is the #255 behaviour, so
    # the ellipsis/overflow pair must not be declared on the label itself.
    assert "text-overflow" not in label
    assert "white-space" in label and label["white-space"] == "nowrap"

    card_label = declarations(
        rule(css, ".os-navbar-identity-card .os-navbar-identity-label")
    )
    # `flex: <grow> <shrink> <basis>` — the shorthand #1715 introduced.
    flex = card_label.get("flex", "")
    parts = flex.split()
    assert len(parts) == 3, f"expected a flex shorthand, got {flex!r}"
    shrink = parts[1]
    assert shrink != "0", f"the name may not shrink: {flex!r}"
    assert card_label.get("width") == "100%", (
        "the label must fill the card's cross axis; #1715 dropped flex-grow for "
        "exactly this reason"
    )


def test_subtitle_css_truncates_with_ellipsis_and_keeps_name_fade():
    css = read_css(INDEX_CSS)
    assert ".os-navbar-identity-subtitle" in css
    # The SUBTITLE is the row that ellipsises; the label above it fades.
    assert declaration(css, ".os-navbar-identity-subtitle", "text-overflow") == "ellipsis"
    # The fade is ATTRIBUTE-gated: the identity observer sets
    # `data-truncated="true"` only when scrollWidth exceeds clientWidth, so a
    # label that fits is not faded at its right edge. The old check was a bare
    # `assert "mask-image: linear-gradient(...)" in css`, which could not tell
    # this rule from any other rule carrying the same gradient — and would have
    # passed on an unconditional mask, which is the regression.
    fade = "linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)"
    truncated = ".os-navbar-identity-label[data-truncated='true']"
    assert declaration(css, truncated, "mask-image") == fade
    assert (
        declaration(css, truncated, "-webkit-mask-image") == fade
    ), "Safari needs the prefixed mask or the name hard-edges there"
    assert (
        declaration(css, ".os-navbar-identity-label", "mask-image") is None
    ), "an unconditional mask fades a name that fits; the gate must stay"


def test_subtitle_formatter_uses_folder_emdash_branch():
    src = WORKSPACE_TS.read_text(encoding="utf-8")
    assert "formatNavbarWorkspaceSubtitle" in src
    assert "${path} — branch: ${branch}" in src
    assert "navbarWorkspaceSubtitle" in src

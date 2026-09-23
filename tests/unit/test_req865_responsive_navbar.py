"""REQ-865: Responsive navbar element prioritization (#255)."""

from pathlib import Path

from helpers.source_surface import chat_surface

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_index_css_fades_identity_label_and_protects_controls():
    css = INDEX_CSS.read_text(encoding="utf-8")
    assert ".os-navbar-identity-label" in css
    assert "mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)" in css
    assert "-webkit-mask-image: linear-gradient(to right, black calc(100% - 1.5rem), transparent 100%)" in css
    assert "overflow: hidden;" in css
    assert ".os-chat-header__controls" in css
    assert "flex-wrap: nowrap;" in css
    assert "flex-shrink: 0;" in css


def test_chat_page_navbar_priority_classes():
    # #1055: shared chat surface — the header markup lives in ChatHeader now.
    tsx = chat_surface()
    # #445: the header clips nothing. Its `overflow: hidden` (class and CSS rule)
    # cropped the routing flyout — an absolutely-positioned child of the picker
    # inside this header — to its first row. The REQ-865 width behaviour is
    # asserted above, on the label that owns the title, and still holds.
    assert 'className="os-chat-header gap-1.5 sm:gap-3"' in tsx
    assert "os-chat-header overflow-hidden" not in tsx
    assert "os-chat-header__identity" in tsx
    assert "os-navbar-identity-label" in tsx
    assert "os-chat-header__controls" in tsx
    # #752: the theme toggle is the first control hidden on narrow viewports;
    # the identity edit buttons keep the hidden-sm:flex priority too.
    assert 'className="hidden sm:inline-flex"' in tsx
    assert "shrink-0 hidden sm:flex" in tsx
    assert 'aria-label="Open agent list"' in tsx
    assert "btn btn-ghost btn-sm btn-square shrink-0" in tsx

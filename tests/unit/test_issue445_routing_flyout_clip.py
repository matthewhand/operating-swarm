"""#445: the chat header must not clip the routing flyout.

Intent: the Agents flyout is an absolutely-positioned child of
`.os-routing-picker`, which sits inside `header.os-chat-header`. When the header
clipped its overflow, everything past the first row was painted outside the clip
and could not be clicked. The header keeps no clip; the title it used to protect
is clamped by the label that holds it.

Behaviour is covered in a real browser by
`webui/frontend/e2e/navbar-routing-picker.spec.ts` — *"the routing flyout is not
clipped by the chat header (#445)"*, which hit-tests every menu row. These
assertions are the negative control: they fail if the clip comes back.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def _chat_page() -> str:
    return CHAT_PAGE_TSX.read_text(encoding="utf-8")


def _css_block(selector: str) -> str:
    """The declarations of one rule, with comments stripped.

    Comments are removed because these assertions are about declarations: a
    comment that names `overflow: hidden` while explaining its removal is not a
    clip.
    """
    css = INDEX_CSS.read_text(encoding="utf-8")
    pattern = "^" + re.escape(selector) + r"\s*\{(.*?)\}"
    match = re.search(pattern, css, re.S | re.M)
    assert match, f"{selector} block is missing from index.css"
    return re.sub(r"/\*.*?\*/", "", match.group(1), flags=re.S)


def test_header_carries_no_clipping_utility():
    tsx = _chat_page()
    assert 'className="os-chat-header gap-1.5 sm:gap-3"' in tsx
    assert "os-chat-header overflow-hidden" not in tsx


def test_header_css_sets_no_overflow():
    block = _css_block(".os-chat-header")
    assert not re.search(r"\boverflow(-[xy])?\s*:", block), block


def test_no_clipping_ancestor_sits_above_the_flyout():
    """The children that would clip it directly must not re-introduce a clip."""
    tsx = _chat_page()
    assert "os-routing-picker" in tsx or "NavbarRoutingPicker" in tsx, "the picker still lives in the header"
    block = _css_block(".os-routing-picker")
    assert "position: relative" in block, "the flyout positions against the picker"
    assert not re.search(r"\boverflow(-[xy])?\s*:", block), block


def test_the_title_still_clamps_on_the_label():
    """The requirement the header clip used to serve, kept where it belongs."""
    label = _css_block(".os-navbar-identity-label")
    assert re.search(r"\boverflow\s*:\s*hidden", label), label
    assert "white-space: nowrap" in label
    # #678: the fade is truncation-gated — the mask moved to the
    # [data-truncated='true'] variant so a fitting name renders unfaded.
    truncated = _css_block(".os-navbar-identity-label[data-truncated='true']")
    assert "mask-image" in truncated, truncated

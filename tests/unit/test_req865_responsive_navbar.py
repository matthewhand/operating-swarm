"""REQ-865: Responsive navbar element prioritization (#255)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INDEX_CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"
CHAT_PAGE_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"


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
    tsx = CHAT_PAGE_TSX.read_text(encoding="utf-8")
    assert 'className="os-chat-header overflow-hidden gap-1.5 sm:gap-3"' in tsx
    assert "os-chat-header__identity" in tsx
    assert "os-navbar-identity-label" in tsx
    assert "os-chat-header__controls" in tsx
    assert "hidden sm:flex shrink-0" in tsx
    assert 'aria-label="Open agent list"' in tsx
    assert "btn btn-ghost btn-sm btn-square shrink-0" in tsx

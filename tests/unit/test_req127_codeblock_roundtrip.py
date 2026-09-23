"""REQ-127: Codeblock copy/paste keeps newlines; user fences render (Fixes #517)."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CHAT_PAGE = REPO_ROOT / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
_DOCK = CHAT_PAGE.parent.parent / "features" / "chat" / "ChatBottomDock.tsx"
MARKDOWN = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "markdown.ts"
CLIPBOARD = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "clipboard.ts"
BUBBLE = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "ChatMessageBubble.tsx"
CSS = REPO_ROOT / "webui" / "frontend" / "src" / "index.css"


def test_composer_is_textarea_that_keeps_pre_wrap():
    page = "\n".join(x.read_text(encoding="utf-8") for x in (CHAT_PAGE, _DOCK))
    assert "<textarea" in page
    assert 'aria-label="Chat message"' in page
    assert "Shift+Enter" in page or "shiftKey" in page
    css = CSS.read_text(encoding="utf-8")
    assert "white-space: pre-wrap" in css
    assert "resize: none" in css


def test_markdown_and_clipboard_preserve_fences():
    md = MARKDOWN.read_text(encoding="utf-8")
    assert "renderSafeMarkdown" in md
    assert "<pre" in md
    clip = CLIPBOARD.read_text(encoding="utf-8")
    assert "navigator.clipboard?.writeText" in clip
    bubble = BUBBLE.read_text(encoding="utf-8")
    assert "renderSafeMarkdown" in bubble
    assert "code-copy" in bubble

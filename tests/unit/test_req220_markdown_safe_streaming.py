"""#220 — optional streaming, theme-gated markdown-safe partial rendering.

Behaviour spec of record (vitest):
  webui/frontend/src/lib/__tests__/markdownSafe.test.ts
  webui/frontend/src/lib/__tests__/streamReplies.test.ts
Python helper (TUI): tests/unit/test_markdown_safe.py
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BUBBLE_THEME = REPO / "webui" / "frontend" / "src" / "lib" / "bubbleTheme.ts"
MARKDOWN_SAFE = REPO / "webui" / "frontend" / "src" / "lib" / "markdownSafe.ts"
STREAM_REPLIES = REPO / "webui" / "frontend" / "src" / "lib" / "streamReplies.ts"
BUBBLE = REPO / "webui" / "frontend" / "src" / "components" / "ChatMessageBubble.tsx"
TUI_APP = REPO / "src" / "swarm" / "tui" / "app.py"
TUI_HELPER = REPO / "src" / "swarm" / "tui" / "markdown_safe.py"
VITEST = REPO / "webui" / "frontend" / "src" / "lib" / "__tests__" / "markdownSafe.test.ts"
DIAGRAM = REPO / "docs" / "diagrams" / "bubble-themes.md"


def test_theme_gate_declares_supports_streaming_and_affordance():
    text = BUBBLE_THEME.read_text(encoding="utf-8")
    assert "supportsStreaming" in text
    assert "renderStreamingAffordance" in text
    assert "bubbleThemeSupportsStreaming" in text
    assert "BUBBLE_THEME_STREAMING" in text


def test_render_markdown_safe_helper_exists():
    text = MARKDOWN_SAFE.read_text(encoding="utf-8")
    assert "export function renderMarkdownSafe" in text
    assert "export function markdownSafePartial" in text
    assert "complete" in text


def test_user_and_seat_toggle_sits_on_theme_gate():
    text = STREAM_REPLIES.read_text(encoding="utf-8")
    assert "streamingPartialEnabled" in text
    assert "loadStreamReplies" in text
    assert "loadSeatStreamReplies" in text
    assert "bubbleThemeSupportsStreaming" in text
    assert "STREAM_REPLIES_STORAGE_KEY = 'os.streamReplies'" in text


def test_chat_bubble_uses_safe_prefix_when_streaming():
    text = BUBBLE.read_text(encoding="utf-8")
    assert "renderMarkdownSafe" in text
    assert "streamingPartialEnabled" in text
    assert "renderStreamingAffordance" in text


def test_tui_reuses_sse_plumbing_with_safe_partial():
    app = TUI_APP.read_text(encoding="utf-8")
    helper = TUI_HELPER.read_text(encoding="utf-8")
    assert "render_markdown_safe" in app
    assert "iter_assistant" in app
    assert "def render_markdown_safe" in helper
    assert "complete" in helper


def test_vitest_covers_ticket_edge_cases():
    text = VITEST.read_text(encoding="utf-8")
    for needle in (
        "nested",
        "inline code",
        "language",
        "list items",
        "stream end",
        "#220",
    ):
        assert needle in text, needle


def test_diagram_names_streaming_hooks():
    text = DIAGRAM.read_text(encoding="utf-8")
    assert "supportsStreaming" in text
    assert "renderStreamingAffordance" in text
    assert "renderMarkdownSafe" in text

"""REQ-845 / #167 — the composer never locks on a closed/connecting socket.

Typed drafts stay editable; sends queue per-conversation and drain on reopen.
A visible .os-conn-status banner explains the offline state. Behaviour spec of
record (vitest): webui/frontend/src/pages/__tests__/ChatComposerResilience.test.tsx
"""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CHAT = REPO / "webui" / "frontend" / "src" / "pages" / "ChatPage.tsx"
CSS = REPO / "webui" / "frontend" / "src" / "index.css"


def test_req845_offline_sends_are_queued_not_dropped():
    text = CHAT.read_text(encoding="utf-8")
    assert "queued.enqueue(trimmed)" in text
    assert "status !== 'open'" in text
    assert "Chat is reconnecting" in text


def test_req845_composer_stays_editable_with_visible_status():
    text = CHAT.read_text(encoding="utf-8")
    assert "os-conn-status" in text
    assert 'data-testid="chat-conn-status"' in text
    assert "keep typing" in text
    css = CSS.read_text(encoding="utf-8")
    assert ".os-conn-status" in css
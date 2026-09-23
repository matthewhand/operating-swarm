"""#744 — user-pasted terminal control sequences are sanitized at the send boundary.

``sanitize_model_text`` already strips ANSI/CSI junk (including ESC-stripped
leftovers like ``[13;28;13;1;0;1_``) from *model* output — but a user message
pasted from a terminal transcript went into ``consumer.messages`` and the
persisted conversation raw. Rendered markdown then carries cursor-position
fragments, and copy/paste re-injects them.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

from swarm.consumers import DjangoChatConsumer

PASTED = "BA → Engineer → Tester[13;28;13;1;0;1_hey[13;28;13;0;0;1_sup"


def _consumer() -> DjangoChatConsumer:
    consumer = DjangoChatConsumer()
    consumer.messages = []
    consumer.ui_events = []
    consumer.user = MagicMock()
    consumer.user.is_authenticated = True
    consumer.conversation_id = "sanitize-744-conv"
    consumer.default_blueprint = None
    consumer.active_agent = None
    consumer.send = AsyncMock()
    consumer.send_error_message = AsyncMock()
    consumer.save_conversation = AsyncMock()
    consumer.respond_with_default_model = AsyncMock()
    return consumer


async def test_user_pasted_control_sequences_never_reach_transcript(monkeypatch):
    import swarm.demo as demo

    monkeypatch.setattr(demo, "is_demo_mode", lambda: False)
    consumer = _consumer()

    await consumer.receive(json.dumps({"message": PASTED}))

    user_rows = [m for m in consumer.messages if m.get("role") == "user"]
    assert user_rows, "user message must be recorded"
    joined = json.dumps(user_rows)
    assert "[13;28;13" not in joined, "mangled CSI junk must not survive the boundary"
    assert "hey" in joined and "sup" in joined, "real words must survive"


async def test_plain_user_text_passes_through_untouched(monkeypatch):
    import swarm.demo as demo

    monkeypatch.setattr(demo, "is_demo_mode", lambda: False)
    consumer = _consumer()

    await consumer.receive(json.dumps({"message": "plain message [1] and {a:1}"}))

    user_rows = [m for m in consumer.messages if m.get("role") == "user"]
    assert user_rows and user_rows[-1]["content"] == "plain message [1] and {a:1}"

"""#818 — the consumer surfaces auxiliary LLM inference over the wire.

The advisor follow-up note is a real background LLM call; the socket must
announce its start, its finish, and accept kill-switch cancellations for
cancellable tasks.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from unittest.mock import AsyncMock, patch



def _frames(mock):
    """self.send(text_data=...) is called with a kwarg — read it from either."""
    out = []
    for call in mock.await_args_list:
        raw = call.kwargs.get("text_data", call.args[0] if call.args else None)
        out.append(json.loads(raw))
    return out


def _consumer():
    from swarm.consumers import DjangoChatConsumer

    consumer = DjangoChatConsumer(scope={"type": "websocket", "user": _fake_user()})
    consumer.user = _fake_user()
    consumer.send = AsyncMock()
    return consumer


def _fake_user():
    class U:
        is_authenticated = True
        pk = 1

    return U()


@pytest.mark.asyncio
async def test_advisor_note_announces_start_and_finish():
    consumer = _consumer()
    with patch(
        "swarm.consumers.DjangoChatConsumer._generate_advice_note_inner",
        new=AsyncMock(return_value="Be terse about exports."),
    ):
        await consumer._generate_advice_note("advisor", "worker", "reply")
    frames = _frames(consumer.send)
    types = [f.get("type") for f in frames]
    assert "aux_task_started" in types
    assert "aux_task_update" in types
    update = next(f for f in frames if f["type"] == "aux_task_update")
    assert update["state"] in {"done", "failed"}
    assert "duration_s" in update


@pytest.mark.asyncio
async def test_cancel_auxiliary_frame_reaches_the_registry():
    consumer = _consumer()
    reg = consumer.auxiliary_tasks
    tid = reg.register("Runaway summarizer")

    class Handle:
        def __init__(self):
            self.cancelled = False

        def cancel(self):
            self.cancelled = True

    handle = Handle()
    reg._tasks[tid]["cancellable"] = handle

    await consumer.receive(json.dumps({"type": "cancel_auxiliary", "task_id": tid}))
    assert handle.cancelled is True
    ack = _frames(consumer.send)[-1]
    assert ack["type"] == "aux_task_update"
    assert ack["cancelled"] is True
    # Silence the unused-import warning path for asyncio in this test module.
    assert asyncio is not None


@pytest.mark.asyncio
async def test_cancel_unknown_task_still_acks():
    consumer = _consumer()
    await consumer.receive(
        json.dumps({"type": "cancel_auxiliary", "task_id": "ghost"})
    )
    ack = _frames(consumer.send)[-1]
    assert ack["cancelled"] is False

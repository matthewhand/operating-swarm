"""#274 — first-turn CLI/config failures are not persisted as chat history."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from swarm.consumers import DjangoChatConsumer
from swarm.core.cli_session_error import FATAL_CONFIG_ERROR_KEY


def _consumer() -> DjangoChatConsumer:
    consumer = DjangoChatConsumer()
    consumer.user = MagicMock()
    consumer.user.is_authenticated = True
    consumer.conversation_id = "cli-poison-conv"
    consumer.ui_events = []
    consumer.save_conversation = AsyncMock()
    consumer.delete_conversation = AsyncMock()
    return consumer


def _poison_messages():
    return [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "No CLI agents are configured. Add a 'cli_agents' block.",
            FATAL_CONFIG_ERROR_KEY: True,
        },
    ]


async def test_fatal_cli_init_does_not_persist_completed_turn():
    consumer = _consumer()
    consumer.messages = _poison_messages()
    await consumer._persist_completed_turn()
    consumer.save_conversation.assert_not_awaited()


async def test_fatal_cli_init_is_not_saved_on_disconnect():
    consumer = _consumer()
    consumer.messages = _poison_messages()
    await consumer.disconnect(1000)
    consumer.save_conversation.assert_not_awaited()


async def test_continued_thread_still_persists():
    consumer = _consumer()
    consumer.messages = _poison_messages() + [{"role": "user", "content": "try again"}]
    await consumer._persist_completed_turn()
    consumer.save_conversation.assert_awaited_once()


async def test_successful_turn_still_persists():
    consumer = _consumer()
    consumer.messages = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello from grok"},
    ]
    await consumer._persist_completed_turn()
    consumer.save_conversation.assert_awaited_once()

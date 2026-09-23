"""REQ-171C-4 / C-H7: WS fetch_conversation mints before the old Django row."""

from __future__ import annotations

import pytest

from swarm.consumers import DjangoChatConsumer
from swarm.core import agent_settings as settings_store
from swarm.core import chat_store
from swarm.models import ChatConversation, ChatMessage


@pytest.fixture(autouse=True)
def _reset_agent_settings():
    settings_store.reset_agent_settings_cache()
    yield
    settings_store.reset_agent_settings_cache()


@pytest.mark.django_db
def test_fetch_on_mode_does_not_append_to_old_transcript(test_user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    settings_store.reset_agent_settings_cache()

    agent = "codey"
    old_cid = chat_store.conversation_id_for(test_user, agent)
    chat = ChatConversation.objects.create(
        conversation_id=old_cid,
        student=test_user,
        agent_id=agent,
    )
    ChatMessage.objects.create(conversation=chat, sender="user", content="old-turn")
    ChatMessage.objects.create(conversation=chat, sender="assistant", content="old-reply")
    chat_store.save(
        chat_store.user_key_for(test_user),
        agent,
        [
            {"role": "user", "content": "old-turn"},
            {"role": "assistant", "content": "old-reply"},
        ],
        conversation_id=old_cid,
    )
    settings_store.update_settings(agent, {"new_chat_per_task": True})

    consumer = DjangoChatConsumer()
    consumer.user = test_user
    consumer.default_blueprint = agent
    consumer.active_agent = agent
    consumer.conversation_id = old_cid
    consumer.messages = []
    consumer.ui_events = []

    fetch_sync = next(c for c in DjangoChatConsumer.__mro__ if "fetch_conversation" in c.__dict__).__dict__["fetch_conversation"].func
    save_sync = next(c for c in DjangoChatConsumer.__mro__ if "save_conversation" in c.__dict__).__dict__["save_conversation"].func

    result = fetch_sync(consumer, old_cid)
    assert result == []
    assert consumer.conversation_id != old_cid
    minted = consumer.conversation_id
    assert minted.startswith("task-")

    save_sync(
        consumer,
        minted,
        [{"role": "user", "content": "new-task"}, {"role": "assistant", "content": "new-reply"}],
    )

    old_chat = ChatConversation.objects.get(conversation_id=old_cid)
    assert list(old_chat.chat_messages.values_list("content", flat=True)) == [
        "old-turn",
        "old-reply",
    ]
    new_chat = ChatConversation.objects.get(conversation_id=minted)
    assert list(new_chat.chat_messages.values_list("content", flat=True)) == [
        "new-task",
        "new-reply",
    ]

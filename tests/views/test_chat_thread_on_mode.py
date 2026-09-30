"""REQ-171C-4 / C-H7: on-mode GET /chat/thread/ must not reuse the old Django row."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import agent_settings as settings_store
from swarm.core import chat_store
from swarm.models import ChatConversation, ChatMessage


@pytest.fixture(autouse=True)
def _reset_agent_settings():
    settings_store.reset_agent_settings_cache()
    yield
    settings_store.reset_agent_settings_cache()


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="on-mode-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="on-mode-op", password="pw")
    return c


def _seed_old_transcript(user, agent="codey", content="old-turn"):
    cid = chat_store.conversation_id_for(user, agent)
    chat_store.save(
        chat_store.user_key_for(user),
        agent,
        [
            {"role": "user", "content": content},
            {"role": "assistant", "content": "old-reply"},
        ],
        conversation_id=cid,
    )
    # #1440: save write-throughs Django. Reuse that row; do not INSERT again.
    chat, _created = ChatConversation.objects.get_or_create(
        conversation_id=cid,
        defaults={"student": user, "agent_id": agent},
    )
    if not chat.chat_messages.exists():
        ChatMessage.objects.create(conversation=chat, sender="user", content=content)
        ChatMessage.objects.create(conversation=chat, sender="assistant", content="old-reply")
    return cid, chat


@pytest.mark.django_db
def test_on_mode_get_mints_and_does_not_return_old_transcript(
    client, user, tmp_path, monkeypatch
):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    settings_store.reset_agent_settings_cache()
    old_cid, old_chat = _seed_old_transcript(user)
    settings_store.update_settings("codey", {"new_chat_per_task": True})

    resp = client.get("/chat/thread/?agent=codey")
    assert resp.status_code == 200
    body = resp.json()
    assert body["new_chat_per_task"] is True
    assert body["conversation_id"] != old_cid
    assert body["messages"] == []
    assert old_chat.chat_messages.count() == 2
    assert [row.content for row in old_chat.chat_messages.order_by("id")] == [
        "old-turn",
        "old-reply",
    ]

    default_resp = client.get(f"/chat/thread/?agent=codey&conversation_id={old_cid}")
    assert default_resp.status_code == 200
    default_body = default_resp.json()
    assert default_body["conversation_id"] != old_cid
    assert default_body["messages"] == []
    assert old_chat.chat_messages.count() == 2


@pytest.mark.django_db
def test_on_mode_post_does_not_append_to_old_transcript(client, user, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    settings_store.reset_agent_settings_cache()
    old_cid, old_chat = _seed_old_transcript(user)
    settings_store.update_settings("codey", {"new_chat_per_task": True})

    resp = client.post(
        "/chat/thread/?agent=codey",
        data=json.dumps({"message": {"role": "user", "content": "new-task"}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] != old_cid
    assert [row["content"] for row in body["messages"]] == ["new-task"]
    assert old_chat.chat_messages.count() == 2
    assert list(old_chat.chat_messages.values_list("content", flat=True)) == [
        "old-turn",
        "old-reply",
    ]
    old_disk = chat_store.load(
        chat_store.user_key_for(user),
        "codey",
        conversation_id=old_cid,
    )
    assert old_disk is not None
    assert [row["content"] for row in old_disk["messages"]] == ["old-turn", "old-reply"]

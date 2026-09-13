"""Remote rail seats hydrate the thread the websocket persists (issue #131).

The SPA hydrates a remote seat with ``agent=remote:<kind>``, but the chat
websocket persists remote conversations under the ``remote_harness`` blueprint
agent (its send frame sends ``blueprint: 'remote_harness'``). ``chat_thread``
maps the rail id to the storage agent so GET hydrate / POST append resolve to
the same thread file.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store

REMOTE_CID = "remote-omb-79b5852c-9ae8-4972-a662-80054be9ea5f"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="remote-hydrate-user", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="remote-hydrate-user", password="pw")
    return c


@pytest.mark.django_db
def test_remote_rail_seat_hydrates_remote_harness_thread(client, user):
    """GET /chat/thread/?agent=remote:omb returns the remote_harness thread."""
    # The websocket persists remote conversations via
    # ``_save_agent_json(..., conversation_id=..., session_id=...)`` →
    # ``<agent>__<cid>.json`` — seed the same scoped file.
    chat_store.save(
        chat_store.user_key_for(user),
        "remote_harness",
        [
            {"role": "user", "content": "can you ssh into the rover?"},
            {"role": "assistant", "content": "SSH to rover is unreachable."},
        ],
        conversation_id=REMOTE_CID,
        session_id=REMOTE_CID,
    )
    resp = client.get(f"/chat/thread/?agent=remote:omb&conversation_id={REMOTE_CID}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == REMOTE_CID
    assert body["kind"] == "remote"
    assert [row["content"] for row in body["messages"]] == [
        "can you ssh into the rover?",
        "SSH to rover is unreachable.",
    ]


@pytest.mark.django_db
def test_remote_dash_rail_seat_append_lands_on_remote_harness_thread(client, user):
    """SPA status appends post agent='remote-omb' (dash) — same storage mapping."""
    chat_store.save(
        chat_store.user_key_for(user),
        "remote_harness",
        [{"role": "user", "content": "hi"}],
        conversation_id=REMOTE_CID,
        session_id=REMOTE_CID,
    )
    resp = client.post(
        "/chat/thread/?agent=remote-omb",
        data=(
            '{"conversation_id": "%s", "message": {"role": "user", '
            '"content": "dash form"}}' % REMOTE_CID
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    loaded = chat_store.load(
        chat_store.user_key_for(user),
        "remote_harness",
        conversation_id=REMOTE_CID,
    )
    assert loaded is not None
    assert [row["content"] for row in loaded["messages"]] == ["hi", "dash form"]


@pytest.mark.django_db
def test_remote_rail_seat_empty_when_thread_missing(client, user):
    """A fresh remote seat with no persisted thread stays an honest empty chat."""
    resp = client.get("/chat/thread/?agent=remote:omb&conversation_id=remote-omb-never")
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == "remote-omb-never"
    assert body["messages"] == []


@pytest.mark.django_db
def test_remote_rail_seat_append_lands_on_remote_harness_thread(client, user):
    """POST status/chat appends for a remote rail seat land on the same file."""
    chat_store.save(
        chat_store.user_key_for(user),
        "remote_harness",
        [{"role": "user", "content": "hi"}],
        conversation_id=REMOTE_CID,
        session_id=REMOTE_CID,
    )
    resp = client.post(
        f"/chat/thread/?agent=remote:omb",
        data=(
            '{"conversation_id": "%s", "message": {"role": "user", '
            '"content": "Switched bot."}}' % REMOTE_CID
        ),
        content_type="application/json",
    )
    assert resp.status_code == 200
    loaded = chat_store.load(
        chat_store.user_key_for(user),
        "remote_harness",
        conversation_id=REMOTE_CID,
    )
    assert loaded is not None
    contents = [row["content"] for row in loaded["messages"]]
    assert contents == ["hi", "Switched bot."]
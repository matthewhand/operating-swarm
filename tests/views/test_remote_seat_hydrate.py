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


@pytest.mark.django_db
def test_chat_thread_sets_no_cache_headers(client, user):
    """GET /chat/thread/ must carry no-cache and no-store headers to prevent stale context."""
    resp = client.get(f"/chat/thread/?agent=remote:omb&conversation_id={REMOTE_CID}")
    assert resp.status_code == 200
    cache_control = resp.headers.get("Cache-Control", "")
    assert "no-cache" in cache_control
    assert "no-store" in cache_control


@pytest.mark.django_db
def test_chat_thread_flush_invalidates_memory_cache(client, user):
    """GET /chat/thread/?flush=1 invalidates IN_MEMORY_CONVERSATIONS for that thread."""
    from swarm.consumers import IN_MEMORY_CONVERSATIONS, _conversation_cache_key

    ck = _conversation_cache_key(user, REMOTE_CID)
    IN_MEMORY_CONVERSATIONS[ck] = [{"role": "assistant", "content": "stale cached turn"}]

    resp = client.get(f"/chat/thread/?agent=remote:omb&conversation_id={REMOTE_CID}&flush=1")
    assert resp.status_code == 200
    assert ck not in IN_MEMORY_CONVERSATIONS


def test_sanitize_herdr_response_strips_summary_table_headers():
    """sanitize_herdr_response strips '| | summary of conversation |' and table dividers."""
    from swarm.core.remotes import sanitize_herdr_response

    raw = """| | summary of conversation |
|---|---|
Here is the actual summary of what happened:
- Point A
- Point B"""
    cleaned = sanitize_herdr_response(raw)
    assert cleaned == """Here is the actual summary of what happened:
- Point A
- Point B"""


@pytest.mark.django_db
def test_herdr_seat_syncs_recent_pane_text(client, user, monkeypatch):
    """Selecting a Herdr seat pulls up-to-date pane text when thread is fresh."""
    from unittest.mock import MagicMock

    mock_read = MagicMock(return_value="| | summary of conversation |\nRecent output from grok pane.")
    monkeypatch.setattr("swarm.core.remotes.read_herdr_recent", mock_read)

    resp = client.get("/chat/thread/?agent=remote:herdr&conversation_id=remote-herdr-grok&flush=1")
    assert resp.status_code == 200
    mock_read.assert_called_with("grok")
    body = resp.json()
    assert len(body["messages"]) >= 1
    # Check that artifact is stripped and clean pane text is returned
    assert body["messages"][0]["content"] == "Recent output from grok pane."
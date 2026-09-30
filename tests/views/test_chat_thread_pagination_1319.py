"""#1319 — ``GET /chat/thread/`` newest-first hydration paging.

Acceptance covered:

- ``?limit=N`` returns at most the newest ``N`` turns with ``has_more`` and a
  cursor;
- ``?before=<cursor>`` returns the preceding page without duplicates/gaps;
- omitting paging (or passing an invalid value) keeps the full load;
- the DB-backfill path still mirrors the *full* transcript to JSON.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.models import ChatConversation, ChatMessage


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="page-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    assert c.login(username="page-op", password="pw")
    return c


def _seed(user, count=6, agent="codey"):
    cid = chat_store.conversation_id_for(user, agent)
    messages = [
        {
            "role": "user" if i % 2 == 0 else "assistant",
            "content": f"m{i}",
        }
        for i in range(count)
    ]
    chat_store.save(chat_store.user_key_for(user), agent, messages, conversation_id=cid)
    return cid


def _contents(resp, key="messages"):
    return [row["content"] for row in resp.json()[key]]


@pytest.mark.django_db
def test_limit_returns_newest_page_with_cursor(client, user):
    _seed(user, 6)
    resp = client.get("/chat/thread/?agent=codey&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert _contents(resp) == ["m4", "m5"]
    assert body["has_more"] is True
    assert body["cursor"] == "4"


@pytest.mark.django_db
def test_before_cursor_walks_older_pages_without_gaps(client, user):
    _seed(user, 7)
    seen: list[str] = []
    cursor: str | None = None
    for _ in range(10):
        url = f"/chat/thread/?agent=codey&limit=3"
        if cursor:
            url += f"&before={cursor}"
        resp = client.get(url)
        assert resp.status_code == 200
        body = resp.json()
        seen = _contents(resp) + seen
        if not body["has_more"]:
            assert body["cursor"] == ""
            break
        cursor = body["cursor"]
    else:  # pragma: no cover - safety net
        raise AssertionError("paging did not terminate")
    assert seen == [f"m{i}" for i in range(7)]
    assert len(seen) == len(set(seen))


@pytest.mark.django_db
def test_no_limit_returns_full_transcript_and_no_cursor(client, user):
    _seed(user, 5)
    resp = client.get("/chat/thread/?agent=codey")
    assert resp.status_code == 200
    body = resp.json()
    assert _contents(resp) == [f"m{i}" for i in range(5)]
    assert body["has_more"] is False
    assert body["cursor"] == ""


@pytest.mark.django_db
def test_invalid_limit_and_before_fall_back_to_full_load(client, user):
    _seed(user, 4)
    resp = client.get("/chat/thread/?agent=codey&limit=abc&before=null")
    assert resp.status_code == 200
    body = resp.json()
    assert _contents(resp) == [f"m{i}" for i in range(4)]
    assert body["has_more"] is False


@pytest.mark.django_db
def test_before_without_limit_returns_older_tail(client, user):
    _seed(user, 5)
    resp = client.get("/chat/thread/?agent=codey&before=2")
    assert resp.status_code == 200
    assert _contents(resp) == ["m0", "m1"]


@pytest.mark.django_db
def test_db_backfill_pages_but_persists_full_transcript(client, user):
    """A DB-only thread pages over HTTP; load must not write JSON (#1440)."""
    cid = chat_store.conversation_id_for(user, "hybrid_team")
    chat = ChatConversation.objects.create(conversation_id=cid, student=user)
    for i in range(6):
        ChatMessage.objects.create(
            conversation=chat,
            sender="user" if i % 2 == 0 else "assistant",
            content=f"db{i}",
        )
    resp = client.get("/chat/thread/?agent=hybrid_team&limit=2")
    assert resp.status_code == 200
    body = resp.json()
    assert _contents(resp) == ["db4", "db5"]
    assert body["has_more"] is True

    # Django keeps the full transcript. Load does not create a JSON loop.
    stored = list(
        ChatMessage.objects.filter(conversation=chat).values_list("content", flat=True)
    )
    assert stored == [f"db{i}" for i in range(6)]
    record = chat_store.load(chat_store.user_key_for(user), "hybrid_team")
    assert record is None


@pytest.mark.django_db
def test_post_append_ignores_paging_and_keeps_tail(client, user):
    """The append path must never be bounded by ?limit (older turns survive)."""
    _seed(user, 4)
    resp = client.post(
        "/chat/thread/?agent=codey&limit=2",
        data=json.dumps({"message": {"role": "user", "content": "new tail"}}),
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert _contents(resp)[-1] == "new tail"

    record = chat_store.load(chat_store.user_key_for(user), "codey")
    assert record is not None
    assert [row["content"] for row in record["messages"]][-1] == "new tail"
    assert len(record["messages"]) == 5


@pytest.mark.django_db
def test_seq_cursor_stable_after_new_tail_append(client, user):
    """A cursor stays valid after a newer turn is appended (seq, not offset)."""
    _seed(user, 6)
    first = client.get("/chat/thread/?agent=codey&limit=2").json()
    assert first["cursor"] == "4"

    client.post(
        "/chat/thread/?agent=codey",
        data=json.dumps({"message": {"role": "user", "content": "tail"}}),
        content_type="application/json",
    )

    older = client.get(f"/chat/thread/?agent=codey&limit=2&before={first['cursor']}")
    assert older.status_code == 200
    assert _contents(older) == ["m2", "m3"]

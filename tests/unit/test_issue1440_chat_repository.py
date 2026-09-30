"""#1440 — one ChatMessage row per composer send. JSON is only the cache."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from swarm.core import chat_store
from swarm.core.chat_db import replace_db_thread
from swarm.core.chat_repository import (
    append_message,
    archive_agent,
    insert_turns,
    prune_expired,
    restore_agent,
    stats_for,
)
from swarm.models import ChatConversation, ChatMessage


@pytest.fixture
def isolate_chat_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    yield tmp_path / "chats"


@pytest.fixture
def user(db):  # noqa: ARG001
    return get_user_model().objects.create_user(username="repo-1440", password="pw")


def _save_conversation(consumer, conversation_id, messages):
    method = next(
        cls.__dict__["save_conversation"]
        for cls in type(consumer).__mro__
        if "save_conversation" in cls.__dict__
    )
    return method.func(consumer, conversation_id, messages)


def _message_sql(queries, verb: str) -> list[str]:
    needle = f"{verb} "
    return [
        row["sql"]
        for row in queries
        if needle in row["sql"].upper() and "swarm_chatmessage" in row["sql"].lower()
    ]


@pytest.mark.django_db
def test_composer_send_inserts_exactly_one_row(user, isolate_chat_dir, monkeypatch):
    """The websocket save path inserts one row and does not replace the thread."""
    from swarm.consumers import DjangoChatConsumer

    def _explode(*_args, **_kwargs):
        raise AssertionError("composer send must not replace the thread")

    monkeypatch.setattr("swarm.core.chat_db.replace_db_thread", _explode)

    cid = chat_store.conversation_id_for(user, "jeeves")
    consumer = DjangoChatConsumer()
    consumer.user = user
    consumer.active_agent = "jeeves"
    consumer.conversation_id = cid
    consumer.ui_events = []
    consumer.messages = [{"role": "user", "content": "prior", "seq": 0}]
    _save_conversation(consumer, cid, consumer.messages)
    prior = ChatMessage.objects.get(conversation_id=cid)

    consumer.messages = [
        {"role": "user", "content": "prior", "seq": 0},
        {"role": "user", "content": "the send", "seq": 1},
    ]
    with CaptureQueriesContext(connection) as ctx:
        _save_conversation(consumer, cid, consumer.messages)

    rows = list(ChatMessage.objects.filter(conversation_id=cid).order_by("id"))
    assert [row.content for row in rows] == ["prior", "the send"]
    assert rows[0].id == prior.id
    assert len(_message_sql(ctx.captured_queries, "INSERT")) == 1
    assert _message_sql(ctx.captured_queries, "DELETE") == []

    with CaptureQueriesContext(connection) as again:
        _save_conversation(consumer, cid, consumer.messages)
    assert _message_sql(again.captured_queries, "INSERT") == []
    assert _message_sql(again.captured_queries, "DELETE") == []
    assert ChatMessage.objects.filter(conversation_id=cid).count() == 2


@pytest.mark.django_db
def test_assistant_turn_inserts_one_row_and_keeps_the_send(user, isolate_chat_dir):
    from swarm.consumers import DjangoChatConsumer

    cid = chat_store.conversation_id_for(user, "jeeves")
    consumer = DjangoChatConsumer()
    consumer.user = user
    consumer.active_agent = "jeeves"
    consumer.conversation_id = cid
    consumer.ui_events = []
    consumer.messages = [{"role": "user", "content": "the send", "seq": 0}]
    _save_conversation(consumer, cid, consumer.messages)
    user_row = ChatMessage.objects.get(conversation_id=cid)

    consumer.messages = [
        {"role": "user", "content": "the send", "seq": 0},
        {"role": "assistant", "content": "ack", "seq": 1},
    ]
    with CaptureQueriesContext(connection) as ctx:
        _save_conversation(consumer, cid, consumer.messages)

    rows = list(ChatMessage.objects.filter(conversation_id=cid).order_by("id"))
    assert [row.content for row in rows] == ["the send", "ack"]
    assert rows[0].id == user_row.id
    assert len(_message_sql(ctx.captured_queries, "INSERT")) == 1
    assert _message_sql(ctx.captured_queries, "DELETE") == []
    cached = chat_store.load(chat_store.user_key_for(user), "jeeves")
    assert cached is not None
    assert [row["content"] for row in cached["messages"]] == ["the send", "ack"]


@pytest.mark.django_db
def test_append_message_inserts_one_row_and_caches_json(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "codey")
    before = ChatMessage.objects.count()
    append_message(user, "codey", cid, {"role": "user", "content": "one send"})
    assert ChatMessage.objects.count() == before + 1
    assert ChatMessage.objects.get(conversation_id=cid).content == "one send"
    cached = chat_store.load(chat_store.user_key_for(user), "codey")
    assert cached is not None
    assert cached["messages"][0]["content"] == "one send"
    assert ChatMessage.objects.filter(content="one send").count() == 1


@pytest.mark.django_db
def test_archive_marks_db_and_reload_hides_then_restore(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "jeeves")
    append_message(user, "jeeves", cid, {"role": "user", "content": "keep me"})
    assert archive_agent(user, "jeeves") is True
    chat = ChatMessage.objects.get(conversation_id=cid).conversation
    assert chat.trashed_at is not None
    assert chat_store.load(chat_store.user_key_for(user), "jeeves") is None
    from swarm.core.thread_load import load_thread

    hidden = load_thread(user, "jeeves", requested_cid=cid, default_cid=cid)
    assert hidden.turns == []
    assert restore_agent(user, "jeeves") is True
    chat.refresh_from_db()
    assert chat.trashed_at is None
    restored = chat_store.load(chat_store.user_key_for(user), "jeeves")
    assert restored is not None
    assert restored["messages"][0]["content"] == "keep me"
    visible = load_thread(user, "jeeves", requested_cid=cid, default_cid=cid)
    assert visible.turns[0]["content"] == "keep me"


@pytest.mark.django_db
def test_append_message_keeps_the_turn_timestamp(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "codey")
    row = append_message(
        user,
        "codey",
        cid,
        {"role": "user", "content": "dated", "ts": "2020-01-02T03:04:05+00:00"},
    )
    row.refresh_from_db()
    assert row.timestamp.year == 2020
    assert row.timestamp.month == 1
    assert row.timestamp.day == 2
    assert row.extra["ts"] == "2020-01-02T03:04:05+00:00"


@pytest.mark.django_db
def test_archive_json_cache_when_the_database_has_no_row(user, isolate_chat_dir):
    chat_store.save(
        chat_store.user_key_for(user),
        "cacheonly",
        [{"role": "user", "content": "file"}],
        conversation_id="cid-cache",
        mirror_db=False,
    )
    assert archive_agent(user, "cacheonly") is True
    assert chat_store.load(chat_store.user_key_for(user), "cacheonly") is None


@pytest.mark.django_db
def test_json_save_does_not_rewrite_a_trashed_thread(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "jeeves")
    append_message(user, "jeeves", cid, {"role": "user", "content": "keep me"})
    assert archive_agent(user, "jeeves") is True
    chat_store.save(
        chat_store.user_key_for(user),
        "jeeves",
        [{"role": "user", "content": "ghost"}],
        conversation_id=cid,
    )
    chat = ChatConversation.objects.get(conversation_id=cid)
    assert chat.trashed_at is not None
    assert list(chat.chat_messages.values_list("content", flat=True)) == ["keep me"]
    assert insert_turns(chat, [{"role": "user", "content": "also ghost"}]) == 0
    assert chat.chat_messages.count() == 1


@pytest.mark.django_db
def test_prune_expired_keeps_a_fresh_sibling_conversation(user, isolate_chat_dir):
    old = ChatConversation.objects.create(
        conversation_id="old-session",
        student=user,
        agent_id="jeeves",
    )
    fresh = ChatConversation.objects.create(
        conversation_id="fresh-session",
        student=user,
        agent_id="jeeves",
    )
    ChatMessage.objects.create(conversation=old, sender="user", content="stale")
    ChatMessage.objects.create(conversation=fresh, sender="user", content="live")
    clock = datetime(2026, 9, 1, tzinfo=timezone.utc)
    ChatConversation.objects.filter(pk=old.pk).update(
        updated_at=clock - timedelta(days=120)
    )
    ChatConversation.objects.filter(pk=fresh.pk).update(
        updated_at=clock - timedelta(days=1)
    )

    assert prune_expired(user, max_age_days=90, now=clock) == ["jeeves"]
    old.refresh_from_db()
    fresh.refresh_from_db()
    assert old.trashed_at is not None
    assert fresh.trashed_at is None
    assert fresh.chat_messages.get().content == "live"


@pytest.mark.django_db
def test_stats_report_the_json_cache_directory(user, isolate_chat_dir):
    stats = stats_for(user)
    assert stats["format"] == "db"
    assert stats["store_dir"] == str(isolate_chat_dir)


@pytest.mark.django_db
def test_post_send_inserts_one_row_without_deleting_history(user, isolate_chat_dir):
    from django.test import Client

    cid = chat_store.conversation_id_for(user, "codey")
    replace_db_thread(
        user,
        cid,
        [{"role": "user", "content": "prior", "seq": 0}],
        agent_id="codey",
    )
    # Cache the prior row the way a finished turn would, without a second insert.
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": "prior", "seq": 0}],
        conversation_id=cid,
        mirror_db=False,
    )
    prior_id = ChatMessage.objects.get(conversation_id=cid).id
    client = Client()
    client.force_login(user)
    resp = client.post(
        "/chat/thread/?agent=codey",
        data='{"message": {"role": "user", "content": "one send"}}',
        content_type="application/json",
    )
    assert resp.status_code == 200
    rows = list(ChatMessage.objects.filter(conversation_id=cid).order_by("id"))
    assert [row.content for row in rows] == ["prior", "one send"]
    assert rows[0].id == prior_id
    assert resp.json()["messages"][-1]["content"] == "one send"


@pytest.mark.django_db
def test_agent_switch_keeps_each_thread(user, isolate_chat_dir):
    from swarm.core.thread_load import load_thread

    codey = chat_store.conversation_id_for(user, "codey")
    stewie = chat_store.conversation_id_for(user, "stewie")
    append_message(user, "codey", codey, {"role": "user", "content": "alpha"})
    append_message(user, "stewie", stewie, {"role": "user", "content": "beta"})
    assert load_thread(user, "codey", default_cid=codey).turns[0]["content"] == "alpha"
    assert load_thread(user, "stewie", default_cid=stewie).turns[0]["content"] == "beta"


@pytest.mark.django_db
def test_trashed_thread_survives_empty_disconnect_save(user, isolate_chat_dir):
    """Opening a trashed chat loads nothing. Disconnect must not wipe it."""
    from swarm.consumers import DjangoChatConsumer
    from swarm.core.thread_load import load_thread

    cid = chat_store.conversation_id_for(user, "codey")
    append_message(user, "codey", cid, {"role": "user", "content": "Reload me after a refresh"})
    append_message(
        user,
        "codey",
        cid,
        {"role": "assistant", "content": "Stored as its own row."},
    )
    assert archive_agent(user, "codey") is True

    consumer = DjangoChatConsumer()
    consumer.user = user
    consumer.active_agent = "codey"
    consumer.conversation_id = cid
    consumer.ui_events = []
    consumer.messages = []
    _save_conversation(consumer, cid, [])
    delete = next(
        cls.__dict__["delete_conversation"]
        for cls in type(consumer).__mro__
        if "delete_conversation" in cls.__dict__
    )
    delete.func(consumer, cid)

    assert ChatMessage.objects.filter(conversation_id=cid).count() == 2
    assert restore_agent(user, "codey") is True
    visible = load_thread(user, "codey", requested_cid=cid, default_cid=cid)
    assert [turn["content"] for turn in visible.turns] == [
        "Reload me after a refresh",
        "Stored as its own row.",
    ]

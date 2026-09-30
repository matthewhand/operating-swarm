"""#1440 — Django is the chat restore source of truth.

Intent (ADR-002 §7.6 / issue title): one-way migrate JSON → Django, then
Django wins. Attachment bytes stay on disk. No JSON↔SQL loop.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model

from swarm.core import chat_store
from swarm.core.chat_db import load_db_thread, replace_db_thread
from swarm.core.thread_load import load_thread
from swarm.models import ChatConversation, ChatMessage

TS = "2026-09-27T12:00:00+00:00"


@pytest.fixture
def isolate_chat_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    yield tmp_path / "chats"


@pytest.fixture
def user(db):  # noqa: ARG001
    return get_user_model().objects.create_user(username="sot-1440", password="pw")


def _turns():
    return [
        {"role": "user", "content": "edited ask", "ts": TS, "edited": True, "seq": 0},
        {"role": "assistant", "content": "ok", "ts": "2026-09-27T12:00:01+00:00", "seq": 1},
    ]


@pytest.mark.django_db
def test_django_wins_over_stale_json(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "codey")
    replace_db_thread(user, cid, _turns(), agent_id="codey", ui_events=[])
    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        [{"role": "user", "content": "stale json only", "ts": TS}],
        conversation_id=cid,
    )
    # save write-through would refresh Django — overwrite Django again to prove load prefers DB.
    replace_db_thread(user, cid, _turns(), agent_id="codey", ui_events=[])

    loaded = load_thread(user, "codey", requested_cid=cid, default_cid=cid)
    assert loaded.from_json is False
    assert [row["content"] for row in loaded.turns] == ["edited ask", "ok"]
    assert loaded.turns[0]["edited"] is True
    assert loaded.turns[0]["ts"] == TS
    assert loaded.turns[0]["seq"] == 0


@pytest.mark.django_db
def test_one_way_migrate_json_to_django_when_db_empty(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "jeeves")
    # Write JSON without going through chat_store.save's Django mirror.
    path = chat_store._active_path(
        chat_store.user_key_for(user),
        "jeeves",
        chat_store.store_dir(),
    )
    record = chat_store.empty_record(
        user_key=chat_store.user_key_for(user),
        agent_id="jeeves",
    )
    record["conversation_id"] = cid
    record["messages"] = _turns()
    record["ui_events"] = [{"role": "status", "content": "hop", "kind": "hop", "seq": 2}]
    chat_store._atomic_write(path, record)

    assert ChatMessage.objects.filter(conversation_id=cid).count() == 0

    loaded = load_thread(user, "jeeves", requested_cid=cid, default_cid=cid)
    assert loaded.from_json is True
    assert loaded.turns[0]["edited"] is True
    assert loaded.turns[0]["ts"] == TS

    db = load_db_thread(user, cid)
    assert db is not None
    turns, events = db
    assert [row["content"] for row in turns] == ["edited ask", "ok"]
    assert turns[0]["edited"] is True
    assert events and events[0]["kind"] == "hop"

    again = load_thread(user, "jeeves", requested_cid=cid, default_cid=cid)
    assert again.from_json is False
    assert again.turns[0]["edited"] is True


@pytest.mark.django_db
def test_load_does_not_write_json_from_django(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "support")
    replace_db_thread(user, cid, _turns(), agent_id="support")

    json_path = chat_store._active_path(
        chat_store.user_key_for(user),
        "support",
        chat_store.store_dir(),
    )
    assert json_path is not None
    assert not json_path.is_file()

    loaded = load_thread(
        user,
        "support",
        requested_cid=cid,
        default_cid=cid,
        backfill_json=True,
    )
    assert loaded.from_json is False
    assert [row["content"] for row in loaded.turns] == ["edited ask", "ok"]
    assert not json_path.is_file()


@pytest.mark.django_db
def test_replace_db_thread_round_trips_metadata_and_ui_events(user, isolate_chat_dir):
    cid = "agt-1440-meta"
    events = [{"role": "status", "content": "CLI: a → b", "kind": "status", "seq": 2}]
    replace_db_thread(user, cid, _turns(), agent_id="codey", ui_events=events)
    turns, stored_events = load_db_thread(user, cid)
    assert turns[0]["edited"] is True
    assert turns[0]["seq"] == 0
    assert turns[1]["seq"] == 1
    assert stored_events[0]["content"] == "CLI: a → b"
    chat = ChatConversation.objects.get(conversation_id=cid)
    assert chat.ui_events[0]["kind"] == "status"
    extras = list(ChatMessage.objects.filter(conversation=chat).values_list("extra", flat=True))
    assert extras[0]["edited"] is True
    assert extras[0]["ts"] == TS


@pytest.mark.django_db
def test_other_user_cannot_load_conversation(user, isolate_chat_dir, db):  # noqa: ARG001
    other = get_user_model().objects.create_user(username="sot-1440-b", password="pw")
    cid = chat_store.conversation_id_for(user, "codey")
    replace_db_thread(user, cid, _turns(), agent_id="codey")
    loaded = load_thread(other, "codey", requested_cid=cid, default_cid=cid)
    assert loaded.turns == []


@pytest.mark.django_db
def test_historical_timestamp_is_stored_and_seq_orders_restore(user, isolate_chat_dir):
    """auto_now_add used to stamp every row 'now', so restore order was an accident."""
    cid = "agt-1440-order"
    # Timestamp order is the reverse of seq. Restore must follow seq.
    turns = [
        {
            "role": "user",
            "content": "second",
            "ts": "2026-09-27T14:00:00+00:00",
            "seq": 1,
        },
        {
            "role": "assistant",
            "content": "first",
            "ts": "2026-09-27T15:00:00+00:00",
            "seq": 0,
        },
    ]
    replace_db_thread(user, cid, turns, agent_id="codey")
    rows = list(ChatMessage.objects.filter(conversation_id=cid).order_by("id"))

    def _instant(value):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    assert _instant(rows[0].timestamp) == datetime.fromisoformat("2026-09-27T14:00:00+00:00")
    assert _instant(rows[1].timestamp) == datetime.fromisoformat("2026-09-27T15:00:00+00:00")
    loaded, _events = load_db_thread(user, cid)
    assert [row["content"] for row in loaded] == ["first", "second"]


@pytest.mark.django_db
def test_replace_keeps_existing_rows_when_insert_fails(user, isolate_chat_dir, monkeypatch):
    cid = "agt-1440-atomic"
    replace_db_thread(user, cid, _turns(), agent_id="codey")

    def boom(rows, **kwargs):  # noqa: ARG001
        raise RuntimeError("insert failed")

    monkeypatch.setattr(ChatMessage.objects, "bulk_create", boom)
    with pytest.raises(RuntimeError, match="insert failed"):
        replace_db_thread(
            user,
            cid,
            [{"role": "user", "content": "replacement", "ts": TS, "seq": 0}],
            agent_id="codey",
        )
    kept = list(ChatMessage.objects.filter(conversation_id=cid).values_list("content", flat=True))
    assert kept == ["edited ask", "ok"]


@pytest.mark.django_db
def test_metadata_only_save_does_not_wipe_django_only_thread(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "codey")
    replace_db_thread(user, cid, _turns(), agent_id="codey", ui_events=[])
    json_path = chat_store._active_path(
        chat_store.user_key_for(user),
        "codey",
        chat_store.store_dir(),
    )
    assert json_path is not None and not json_path.is_file()

    chat_store.save(
        chat_store.user_key_for(user),
        "codey",
        None,
        conversation_id=cid,
        active_cli="grok",
    )
    loaded, _events = load_db_thread(user, cid)
    assert [row["content"] for row in loaded] == ["edited ask", "ok"]
    record = chat_store.load(chat_store.user_key_for(user), "codey")
    assert record is not None
    assert record["active_cli"] == "grok"
    assert [row["content"] for row in record["messages"]] == ["edited ask", "ok"]


@pytest.mark.django_db
def test_metadata_save_skips_write_when_django_hydrate_fails(user, isolate_chat_dir, monkeypatch):
    """A database error must not become an empty JSON snapshot that later wipes Django."""
    cid = chat_store.conversation_id_for(user, "codey")
    replace_db_thread(user, cid, _turns(), agent_id="codey", ui_events=[])
    json_path = chat_store._active_path(
        chat_store.user_key_for(user),
        "codey",
        chat_store.store_dir(),
    )
    assert json_path is not None and not json_path.is_file()

    def boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("db down")

    monkeypatch.setattr(ChatConversation.objects, "filter", boom)
    try:
        saved = chat_store.save(
            chat_store.user_key_for(user),
            "codey",
            None,
            conversation_id=cid,
            active_cli="grok",
        )
        assert saved is None
        assert not json_path.is_file()
    finally:
        monkeypatch.undo()
    loaded, _events = load_db_thread(user, cid)
    assert [row["content"] for row in loaded] == ["edited ask", "ok"]


@pytest.mark.django_db
def test_put_cli_session_does_not_copy_the_default_thread(user, isolate_chat_dir):
    """A missing JSON file must hydrate the caller's conversation, not the default one."""
    from swarm.core.cli_sessions import put_cli_session

    agent = "codey"
    default_cid = chat_store.conversation_id_for(user, agent)
    specific = "conv-1440-specific"
    replace_db_thread(
        user,
        default_cid,
        [{"role": "user", "content": "default-thread", "ts": TS, "seq": 0}],
        agent_id=agent,
    )
    replace_db_thread(
        user,
        specific,
        [{"role": "user", "content": "specific-thread", "ts": TS, "seq": 0}],
        agent_id=agent,
    )

    put_cli_session(
        chat_store.user_key_for(user),
        agent,
        "grok",
        "sid-grok",
        conversation_id=specific,
    )

    specific_turns, _events = load_db_thread(user, specific)
    default_turns, _default_events = load_db_thread(user, default_cid)
    assert [row["content"] for row in specific_turns] == ["specific-thread"]
    assert [row["content"] for row in default_turns] == ["default-thread"]
    record = chat_store.load(
        chat_store.user_key_for(user),
        agent,
        conversation_id=specific,
    )
    assert record is not None
    assert record["conversation_id"] == specific
    assert record["cli_sessions"]["grok"] == "sid-grok"


@pytest.mark.django_db
def test_append_seeds_from_django_when_json_file_is_missing(user, isolate_chat_dir):
    cid = chat_store.conversation_id_for(user, "jeeves")
    replace_db_thread(user, cid, _turns(), agent_id="jeeves")
    record = chat_store.load_or_django(chat_store.user_key_for(user), "jeeves")
    assert record is not None
    turns = list(record["messages"])
    turns.append(
        {"role": "user", "content": "third", "ts": "2026-09-27T12:00:02+00:00", "seq": 2}
    )
    chat_store.save(
        chat_store.user_key_for(user),
        "jeeves",
        turns,
        conversation_id=cid,
        ui_events=record.get("ui_events") or [],
    )
    loaded, _events = load_db_thread(user, cid)
    assert [row["content"] for row in loaded] == ["edited ask", "ok", "third"]


@pytest.mark.django_db
def test_explicit_empty_save_still_clears_django(user, isolate_chat_dir):
    """#1722 changed this contract: the JSON cache can no longer clear Django.

    This used to assert that ``chat_store.save(..., messages=[])`` deleted the
    canonical rows — i.e. that a cache file could destroy the database, which is
    precisely the "cache as a write-back source" behaviour #1722 removes. The
    two requirements cannot both hold: ``save`` cannot distinguish "the user
    cleared this thread" from "this file happens to be empty", and only the
    first is a real user action.

    So the clear moved to the canonical layer and both halves are asserted here:
    an empty cache write is inert, and the real clear still empties the thread.
    """
    from swarm.core.chat_repository import clear_thread

    cid = chat_store.conversation_id_for(user, "support")
    replace_db_thread(
        user,
        cid,
        _turns(),
        agent_id="support",
        ui_events=[{"role": "status", "content": "x"}],
    )
    chat_store.save(
        chat_store.user_key_for(user),
        "support",
        [],
        conversation_id=cid,
        ui_events=[],
    )
    loaded, events = load_db_thread(user, cid)
    assert [row["content"] for row in loaded] == ["edited ask", "ok"], (
        "an empty cache write deleted canonical rows — the cache is a derived "
        "export and must not be able to destroy the store it is derived from"
    )

    # The product action still clears the thread, on the canonical store.
    clear_thread(user, cid, agent_id="support")
    loaded, events = load_db_thread(user, cid)
    assert loaded == []
    assert events == []
    # …and the cache file was emptied with it, so nothing is left to re-import.
    on_disk = chat_store.load(
        chat_store.user_key_for(user), "support", conversation_id=cid
    )
    assert (on_disk or {}).get("messages") == []


@pytest.mark.django_db
def test_reactions_and_config_target_round_trip(user, isolate_chat_dir):
    cid = "agt-1440-react"
    turns = [
        {
            "role": "assistant",
            "content": "No CLI agents are configured.",
            "ts": TS,
            "seq": 0,
            "fatal_config_error": True,
            "config_target": {"section": "cli-agents"},
            "reactions": [{"emoji": "👍", "actors": ["user"]}],
        }
    ]
    replace_db_thread(user, cid, turns, agent_id="codey")
    loaded, _events = load_db_thread(user, cid)
    assert loaded[0]["config_target"] == {"section": "cli-agents"}
    assert loaded[0]["reactions"][0]["emoji"] == "👍"
    from swarm.core.thread_load import public_message

    public = public_message(loaded[0])
    assert public["config_target"] == {"section": "cli-agents"}
    assert public["reactions"][0]["emoji"] == "👍"
    assert public["reactions"][0]["userReacted"] is True


@pytest.mark.django_db
def test_swarm_migration_graph_has_one_leaf(db):  # noqa: ARG001
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader

    loader = MigrationLoader(connection, ignore_no_migrations=True)
    leaves = [node for node in loader.graph.leaf_nodes() if node[0] == "swarm"]
    # Exact parents of this leaf are locked in tests/core/test_swarm_migration_graph.py.
    assert leaves == [("swarm", "0026_chatconversation_purged_at")]


def test_attachment_bytes_stay_on_disk():
    """#1440 keeps file bytes out of the DB — ChatAttachment docstring + chat_attachments."""
    models = Path("src/swarm/models/__init__.py").read_text(encoding="utf-8")
    assert "Bytes live under" in models
    assert "SWARM_ATTACHMENTS_DIR" in models
    helper = Path("src/swarm/core/chat_db.py").read_text(encoding="utf-8")
    assert "Attachment bytes stay on disk" in helper
    load = Path("src/swarm/core/thread_load.py").read_text(encoding="utf-8")
    assert "Load never writes JSON from Django (no loop)" in load

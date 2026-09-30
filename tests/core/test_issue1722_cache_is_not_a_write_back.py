"""Issue #1722 — the ``chat_store`` JSON cache must never write back to Django.

``AGENTS.md`` §3: ``ChatConversation`` / ``ChatMessage`` is canonical, one
``ChatMessage`` per new message, and the JSON file is a derived cache refreshed
*after* the database write. ``chat_store`` JSON was in fact being treated as a
write-back source, so the cache could destroy and cross-contaminate the rows it
is supposed to be derived from. This is the opposite direction of #1721: there,
deleted content came back; here, live content is overwritten or truncated.

Each test below is a distinct destruction mechanism, not a variation on one:

* A. ``put_cli_session`` read the agent's *default* cache file and re-published
  it under the caller's conversation id, so one conversation's turns replaced
  another's rows.
* B. a short list meant "delete the tail", so a stale cache (a failed write, a
  metadata save) truncated canonical rows.
* C. a websocket socket that hydrated before a concurrent append re-saved its
  own short snapshot on disconnect, deleting the other writer's row.
* D. a metadata-only save (``messages=None``) round-tripped the file through a
  full delete-and-reinsert.

All of them are now prevented in one place: the single funnel every
``chat_store.save(..., mirror_db=True)`` call site passes through
(``chat_repository.persist_from_cache_record``) is append-only, and canonical
rows are only ever deleted when a caller says so explicitly.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store, cli_sessions
from swarm.models import ChatMessage

AGENT = "claude"
CID_A = "conv-1722-a-111111111111"
CID_B = "conv-1722-b-222222222222"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="wb-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="wb-op", password="pw")
    return c


def _rows(cid: str) -> list[str]:
    return list(
        ChatMessage.objects.filter(conversation__conversation_id=cid)
        .order_by("timestamp", "id")
        .values_list("content", flat=True)
    )


def _append(user, agent: str, cid: str, text: str, role: str = "user") -> None:
    """The canonical one-message-per-send write, the way a composer send does it."""
    from swarm.core.chat_repository import append_message

    append_message(user, agent, cid, {"role": role, "content": text})


# --------------------------------------------------------------------------- #
# A. put_cli_session cross-writes conversations
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_put_cli_session_does_not_overwrite_another_conversation(user):
    """Repro A: the CLI id store destroyed conversation A's rows.

    ``put_cli_session`` loaded the agent's **default** ``<agent>.json`` — the
    file that belongs to the seat's default conversation, not to the
    conversation being stamped — and then saved those turns under the *caller's*
    conversation id with ``mirror_db`` left at its default. So
    ``put_cli_session(conversation_id=A)`` published conversation B's transcript
    into A's ``ChatMessage`` rows.

    The shape below is the issue's own: two conversations created and saved
    through the JSON entry point, then stamped. ``_remember_session`` runs on
    every successful CLI turn, so any CLI seat with more than one conversation
    was affected.
    """
    key = chat_store.user_key_for(user)
    a_turns = [
        {"role": "user", "content": "a question"},
        {"role": "assistant", "content": "a answer"},
    ]
    b_turns = [
        {"role": "user", "content": "b question"},
        {"role": "assistant", "content": "b answer"},
    ]
    chat_store.save(key, AGENT, a_turns, conversation_id=CID_A)
    chat_store.save(key, AGENT, b_turns, conversation_id=CID_B)
    assert _rows(CID_A) == ["a question", "a answer"]
    assert _rows(CID_B) == ["b question", "b answer"]

    cli_sessions.put_cli_session(key, AGENT, AGENT, "host-sess-A", conversation_id=CID_A)
    cli_sessions.put_cli_session(key, AGENT, AGENT, "host-sess-B", conversation_id=CID_B)

    assert _rows(CID_A) == ["a question", "a answer"], (
        "put_cli_session replaced conversation A's rows with another conversation's"
    )
    assert _rows(CID_B) == ["b question", "b answer"], (
        "put_cli_session replaced conversation B's rows with another conversation's"
    )

    # The id really did land where it belongs: on the conversation's own record.
    assert cli_sessions.get_cli_session(key, AGENT, AGENT, conversation_id=CID_A) == "host-sess-A"
    assert cli_sessions.get_cli_session(key, AGENT, AGENT, conversation_id=CID_B) == "host-sess-B"


@pytest.mark.django_db
def test_put_cli_session_does_not_touch_the_default_conversation(user):
    """The default file is another conversation. Reading it is the bug.

    ``chat_store.load(user_key, agent_id)`` with no ids answers with
    ``<agent>.json`` — the seat's *default* thread, a different conversation
    with a different id. Using it as the base for a metadata write is how a
    stamp for conversation A could not avoid carrying the default thread's
    turns.
    """
    key = chat_store.user_key_for(user)
    default_cid = chat_store.conversation_id_for(user, AGENT)
    chat_store.save(
        key,
        AGENT,
        [{"role": "user", "content": "default turn"}],
        conversation_id=default_cid,
    )
    chat_store.save(
        key,
        AGENT,
        [{"role": "user", "content": "a question"}],
        conversation_id=CID_A,
    )
    assert _rows(default_cid) == ["default turn"]
    assert _rows(CID_A) == ["a question"]

    cli_sessions.put_cli_session(key, AGENT, AGENT, "host-sess-A", conversation_id=CID_A)

    assert _rows(default_cid) == ["default turn"], "the default thread was overwritten"
    assert _rows(CID_A) == ["a question"], "the stamped conversation was overwritten"
    default_record = chat_store.load(key, AGENT) or {}
    assert default_record.get("conversation_id") == default_cid
    assert "host-sess-A" not in str(default_record.get("cli_sessions")), default_record


@pytest.mark.django_db
def test_put_cli_session_writes_one_file_per_conversation(user):
    """A metadata write must not file a conversation under another's stem.

    Each conversation's transcript and its CLI id live in the same
    ``<agent>__<conversation_id>.json`` file. A metadata write that lands on the
    agent's default file is invisible to the next turn, which then starts a
    fresh host session (#1690) — and a metadata write that lands on the *wrong*
    conversation's file is #1722-A.
    """
    key = chat_store.user_key_for(user)
    _append(user, AGENT, CID_A, "a question", role="user")
    _append(user, AGENT, CID_B, "b question", role="user")

    cli_sessions.put_cli_session(key, AGENT, AGENT, "host-sess-A", conversation_id=CID_A)
    cli_sessions.put_cli_session(key, AGENT, AGENT, "host-sess-B", conversation_id=CID_B)

    record_a = chat_store.load(key, AGENT, conversation_id=CID_A) or {}
    record_b = chat_store.load(key, AGENT, conversation_id=CID_B) or {}
    assert record_a.get("cli_sessions") == {AGENT: "host-sess-A"}, record_a.get("cli_sessions")
    assert record_b.get("cli_sessions") == {AGENT: "host-sess-B"}, record_b.get("cli_sessions")
    assert record_a.get("conversation_id") == CID_A
    assert record_b.get("conversation_id") == CID_B
    # Neither conversation's file may carry the other's transcript.
    assert [m["content"] for m in record_a.get("messages") or []] == ["a question"]
    assert [m["content"] for m in record_b.get("messages") or []] == ["b question"]


@pytest.mark.django_db
def test_the_file_layout_rule_has_exactly_one_implementation(user):
    """Two copies of "which file holds this conversation" is the root cause.

    ``chat_repository._session_id_for`` and ``cli_sessions.thread_session_id``
    used to derive the stem independently, and they had already drifted: one
    honoured a layout already on disk, the other only predicted. The drift is
    what made the metadata read above answer with the default file.
    """
    key = chat_store.user_key_for(user)
    agent = "layout-probe"
    cid = "conv-1722-layout-444444444444"
    # A layout already on disk wins over the prediction, in both callers.
    chat_store.save(
        key,
        agent,
        [{"role": "user", "content": "hi"}],
        conversation_id=cid,
        session_id="an-existing-stem",
        mirror_db=False,
    )
    from swarm.core.chat_repository import _session_id_for

    assert _session_id_for(user, agent, cid) == "an-existing-stem"
    assert cli_sessions.thread_session_id(key, agent, cid) == "an-existing-stem"
    assert _session_id_for(user, agent, cid) == chat_store.session_stem_for_conversation(
        key, agent, cid
    )
    # With no record on disk, the prediction is the conversation id, because it
    # is not the owner's default thread.
    assert chat_store.session_stem_for_conversation(key, agent, "conv-unseen-555") == (
        "conv-unseen-555"
    )
    assert chat_store.session_stem_for_conversation(
        key, agent, chat_store.conversation_id_for(user, agent)
    ) == ""


# --------------------------------------------------------------------------- #
# B. a short list used to mean "delete the canonical tail"
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_a_stale_cache_file_cannot_truncate_canonical_rows(user):
    """Repro B: a cache left behind by a failed write destroyed a live row.

    ``_write_cache`` swallows write failures, so nothing ever reconciled the two
    stores. The database was right and the cache was short. The next
    JSON-first writer then handed the short list back to ``sync_transcript``,
    which read "shorter" as "delete the tail" and removed the row the cache had
    never heard of.
    """
    key = chat_store.user_key_for(user)
    _append(user, AGENT, CID_A, "turn one", role="user")
    _append(user, AGENT, CID_A, "answer two", role="assistant")
    assert _rows(CID_A) == ["turn one", "answer two"]

    # The failed cache write: the file is now short, the database is not.
    path = chat_store.store_dir() / "active" / key / f"{AGENT}__{CID_A}.json"
    record = chat_store.load(key, AGENT, conversation_id=CID_A) or {}
    stale = dict(record)
    stale["messages"] = [m for m in record.get("messages") or [] if m.get("content") == "turn one"]
    path.write_text(chat_store.json.dumps(stale, indent=2), encoding="utf-8")
    assert len((chat_store.load(key, AGENT, conversation_id=CID_A) or {}).get("messages") or []) == 1

    # Any JSON-first writer now runs. The read-then-append shape is the one
    # ``agent_mailbox.deliver_to_transcript``, ``omb_session_watch._persist``,
    # ``agent_lifecycle._audit``, ``cos_topology`` and ``cli_session_hop`` all
    # use: read the file, append, publish. Before the fix each of these handed
    # the short list back to ``sync_transcript``, which read "shorter" as
    # "delete the tail" and removed a row the cache had never heard of.
    from_file = list(stale["messages"])
    from_file.append({"role": "user", "content": "ping"})
    chat_store.save(
        key,
        AGENT,
        from_file,
        conversation_id=CID_A,
        session_id=CID_A,
    )
    assert _rows(CID_A) == ["turn one", "answer two", "ping"], (
        "a stale cache truncated canonical rows"
    )

    # A second, independent stale file with a *different* short list must not be
    # able to overwrite the row it is missing either.
    record = chat_store.load(key, AGENT, conversation_id=CID_A) or {}
    path.write_text(
        chat_store.json.dumps({**record, "messages": []}, indent=2), encoding="utf-8"
    )
    chat_store.save(key, AGENT, [], conversation_id=CID_A, session_id=CID_A)
    assert _rows(CID_A) == ["turn one", "answer two", "ping"], (
        "an empty cache file emptied the canonical thread"
    )


@pytest.mark.django_db
def test_a_metadata_only_save_cannot_rebuild_rows_from_the_file(user):
    """Repro B, no failure needed: ``_mark_active_cli`` truncated the thread.

    ``chat_store.save(..., messages=None)`` kept the default ``mirror_db=True``.
    The ``messages is not None`` guard skipped ``persist_from_cache_record`` and
    fell through to ``_mirror_record_to_django``, which is a full
    delete-and-reinsert of the canonical rows out of the JSON file. Confirmed in
    the issue: DB ``['q1','a1','q2']`` -> ``['q1','a1']``.
    """
    key = chat_store.user_key_for(user)
    _append(user, AGENT, CID_A, "q1", role="user")
    _append(user, AGENT, CID_A, "a1", role="assistant")
    _append(user, AGENT, CID_A, "q2", role="user")
    assert _rows(CID_A) == ["q1", "a1", "q2"]

    # Stamp the file short first, so a write-back would be visible.
    path = chat_store.store_dir() / "active" / key / f"{AGENT}__{CID_A}.json"
    record = chat_store.load(key, AGENT, conversation_id=CID_A) or {}
    stale = dict(record)
    stale["messages"] = [m for m in record.get("messages") or [] if m.get("content") != "q2"]
    path.write_text(chat_store.json.dumps(stale, indent=2), encoding="utf-8")

    chat_store.save(
        key,
        AGENT,
        None,
        conversation_id=CID_A,
        session_id=CID_A,
        active_cli=AGENT,
    )
    assert _rows(CID_A) == ["q1", "a1", "q2"], "a metadata save rebuilt rows from the file"


@pytest.mark.django_db
def test_clear_thread_is_the_only_thing_that_deletes_rows(user):
    """The fix is a gate, not a removal: explicit truncation still works.

    Without this, "never delete" would just be "never clear" — and clearing a
    thread is a real product action. The gate is ``truncate=True``, and
    :func:`clear_thread` is the only caller that sets it. An empty
    ``chat_store.save`` is deliberately *not* one of them: a cache file cannot
    say "the user cleared this", only "I have nothing", and those are not the
    same claim.
    """
    from swarm.core.chat_repository import clear_thread

    _append(user, AGENT, CID_A, "q1", role="user")
    _append(user, AGENT, CID_A, "a1", role="assistant")
    assert _rows(CID_A) == ["q1", "a1"]

    clear_thread(user, CID_A, agent_id=AGENT)
    assert _rows(CID_A) == []
    assert (chat_store.load(chat_store.user_key_for(user), AGENT, conversation_id=CID_A) or {}).get(
        "messages"
    ) == []

    # And an empty cache write stays inert even on a populated thread.
    _append(user, AGENT, CID_A, "q2", role="user")
    _append(user, AGENT, CID_A, "a2", role="assistant")
    chat_store.save(chat_store.user_key_for(user), AGENT, [], conversation_id=CID_A, session_id=CID_A)
    assert _rows(CID_A) == ["q2", "a2"], "an empty cache write emptied the thread"


# --------------------------------------------------------------------------- #
# C. a websocket socket's stale snapshot
# --------------------------------------------------------------------------- #


def _socket(user, cid: str):
    """A consumer bound to a real DB connection, holding a stale snapshot.

    ``ConversationsMixin`` is a plain mixin, so the persist path can be driven
    directly. Called from a synchronous test, ``SyncToAsync.__call__`` takes
    its sync path and runs on this thread, so the rows it writes are the ones
    this test can assert on.
    """
    from django.db import connection

    from asgiref.sync import SyncToAsync

    from swarm.chat.conversations_mixin import ConversationsMixin

    class FakeSocket(ConversationsMixin):
        def __init__(self):
            self._connection = connection
            self.user = user
            self.active_agent = AGENT
            self.default_blueprint = AGENT
            self.conversation_id = cid
            self.ui_events = []

    return FakeSocket()


# ``transaction=True`` is required, not a style choice. ``save_conversation`` is
# a ``SyncToAsync``, so it runs on a worker thread with its own database
# connection — outside the atomic block a plain ``django_db`` provides, where
# its writes would be invisible to this test (and would commit for real).
@pytest.mark.django_db(transaction=True)
def test_a_stale_socket_snapshot_cannot_delete_a_concurrent_writers_row(client, user):
    """Repro C: disconnecting a socket erased another writer's turn.

    ``save_conversation`` wrote ``self.messages`` — the socket's private
    snapshot, taken when it hydrated — through ``sync_transcript``, which
    deleted the tail when the list was shorter. A socket that hydrated before
    an out-of-band append therefore removed that append on disconnect. The same
    shape covers two tabs, two consumers, and out-of-band OMB/Herdr replies.
    """
    from asgiref.sync import async_to_sync

    _append(user, AGENT, CID_A, "socket turn", role="user")
    socket = _socket(user, CID_A)
    # The socket hydrates here and never learns about the next turn.
    socket.messages = [{"role": "user", "content": "socket turn"}]

    # A concurrent writer appends out of band.
    _append(user, AGENT, CID_A, "rest turn", role="user")
    assert _rows(CID_A) == ["socket turn", "rest turn"]

    async_to_sync(socket.save_conversation)(CID_A, socket.messages)

    assert _rows(CID_A) == ["socket turn", "rest turn"], (
        "the socket's stale snapshot deleted a concurrent writer's row"
    )


@pytest.mark.django_db(transaction=True)
def test_disconnect_refreshes_the_memory_cache_from_the_database(client, user):
    """The other half of repro C: the same snapshot truncated the WS cache.

    ``IN_MEMORY_CONVERSATIONS`` is what ``fetch_conversation`` serves a
    reconnecting socket, so publishing a stale list there hid a live turn from
    the UI even when the database was fine.
    """
    from asgiref.sync import async_to_sync

    from swarm.consumers import IN_MEMORY_CONVERSATIONS, IN_MEMORY_UI_EVENTS, _conversation_cache_key

    _append(user, AGENT, CID_A, "socket turn", role="user")
    socket = _socket(user, CID_A)
    socket.messages = [{"role": "user", "content": "socket turn"}]
    _append(user, AGENT, CID_A, "rest turn", role="user")

    key = _conversation_cache_key(user, CID_A)
    try:
        async_to_sync(socket.save_conversation)(CID_A, socket.messages)
        cached = [m.get("content") for m in IN_MEMORY_CONVERSATIONS.get(key) or []]
        assert cached == ["socket turn", "rest turn"], (
            f"the in-process WS cache was truncated to the socket's snapshot: {cached}"
        )
    finally:
        IN_MEMORY_CONVERSATIONS.pop(key, None)
        IN_MEMORY_UI_EVENTS.pop(key, None)


@pytest.mark.django_db
def test_archive_purges_the_in_process_websocket_cache(client, user):
    """Trash has to reach the memory cache, or a live socket keeps the content.

    ``archive_agent`` / ``empty_trash`` touched only the database and the
    filesystem, so ``fetch_conversation`` went on serving the full transcript
    out of ``IN_MEMORY_CONVERSATIONS`` to any socket in the process. Retirement
    is a privacy promise and the memory cache has to honour it too.
    """
    from swarm.consumers import IN_MEMORY_CONVERSATIONS, IN_MEMORY_UI_EVENTS, _conversation_cache_key

    key = _conversation_cache_key(user, CID_A)
    _append(user, AGENT, CID_A, "SECRET", role="user")
    IN_MEMORY_CONVERSATIONS[key] = [{"role": "user", "content": "SECRET"}]
    IN_MEMORY_UI_EVENTS[key] = []
    try:
        assert client.post(
            "/settings/chats/action/", {"action": "archive", "agent_id": AGENT}
        ).json()["success"] is True
        assert key not in IN_MEMORY_CONVERSATIONS, (
            "a live socket would still be served the trashed transcript"
        )
    finally:
        IN_MEMORY_CONVERSATIONS.pop(key, None)
        IN_MEMORY_UI_EVENTS.pop(key, None)


# --------------------------------------------------------------------------- #
# D. the one-way import itself
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_json_import_refuses_a_thread_that_already_has_rows(user):
    """``mirror_json_record_to_django`` is import-into-empty, or it is a writer.

    It is the only path that calls ``replace_db_thread`` (delete + reinsert), so
    "may only populate a thread the database has never seen" has to be enforced
    there rather than at each of its call sites.
    """
    from swarm.core.chat_db import mirror_json_record_to_django

    key = chat_store.user_key_for(user)
    _append(user, AGENT, CID_A, "canonical one", role="user")
    _append(user, AGENT, CID_A, "canonical two", role="assistant")

    record = {
        "agent_id": AGENT,
        "user_key": key,
        "conversation_id": CID_A,
        "messages": [{"role": "user", "content": "cache only"}],
        "ui_events": [],
    }
    assert mirror_json_record_to_django(key, AGENT, record) is False
    assert _rows(CID_A) == ["canonical one", "canonical two"], (
        "the one-way import overwrote a populated thread"
    )

    # An empty thread is still importable — that is the whole point of it.
    empty = "conv-1722-empty-333333333333"
    assert mirror_json_record_to_django(
        key, AGENT, {**record, "conversation_id": empty, "messages": [{"role": "user", "content": "imported"}]}
    ) is True
    assert _rows(empty) == ["imported"]
    # …and it is idempotent, not a one-shot: a second import of the same record
    # declines (it no longer has anything to add) and leaves the rows alone.
    assert mirror_json_record_to_django(
        key, AGENT, {**record, "conversation_id": empty, "messages": [{"role": "user", "content": "imported"}]}
    ) is False
    assert _rows(empty) == ["imported"], "a repeated import duplicated or changed rows"


# --------------------------------------------------------------------------- #
# Attachments (the lower-severity item in the same report)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_an_attachments_list_survives_the_round_trip(client, user):
    """``attachments`` was missing from all three whitelists on the way in.

    ``chat_store._normalize_messages`` is a whitelist *rebuild* and
    ``chat_db._TURN_EXTRA_KEYS`` is the Django-side allowlist, so the
    websocket's ``attachments=[aid]`` was dropped twice and the message ->
    attachment link did not survive. The bytes correctly stayed on disk; only
    the link was lost. This is the trap the report warns about: a key has to be
    carried by every projection between the socket and the row, or it silently
    vanishes.
    """
    from swarm.core.chat_repository import append_message
    from swarm.core.thread_load import public_message

    aid = "1f0c7a2e-0000-4000-8000-00000000abcd"
    append_message(
        user,
        AGENT,
        CID_A,
        {"role": "user", "content": "see this", "attachments": [aid]},
    )
    row = ChatMessage.objects.get(conversation__conversation_id=CID_A)
    assert row.extra.get("attachments") == [aid], row.extra

    # …and the cache file kept it, rather than dropping it on the whitelist
    # rebuild.
    record = chat_store.load(chat_store.user_key_for(user), AGENT, conversation_id=CID_A) or {}
    assert (record.get("messages") or [{}])[0].get("attachments") == [aid], record.get("messages")

    # …and the public projection echoes it back to the client.
    from swarm.core.chat_db import turn_from_row

    assert public_message(turn_from_row(row))["attachments"] == [aid]

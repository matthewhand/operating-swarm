"""Issue #1681 — list conversations and hand off to an id the user names.

OpenRig can hand off between *known* teammate/room ids. There was no way to
enumerate conversations or post into an arbitrary id, so relocating work meant
re-pasting context.

Two things these tests are really guarding, beyond the three acceptance boxes:

1. **No second chat registry.** Every read and write goes through the canonical
   ``ChatConversation`` / ``ChatMessage`` rows. The test asserts the row count
   and the ``ChatMessage`` rows directly, so an implementation that kept its
   own in-process conversation list would fail even if the HTTP shape were
   right.
2. **DB-is-canonical is not reopened.** A handoff writes one ``ChatMessage`` row
   and refreshes the derived JSON cache. It must not rebuild the thread from the
   cache — the class of bug #1721 / #1722 were filed about. A handoff into a
   thread whose cache file is short must leave the existing rows alone.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core.conversation_directory import (
    ConversationNotFound,
    list_conversations,
    move_topic,
    post_to_conversation,
    resolve_conversation,
)
from swarm.models import ChatConversation, ChatMessage

DM_CID = "conv-1681-dm-000000000001"
ROOM_CID = "conv-1681-room-000000000002"
OTHER_CID = "conv-1681-other-00000000003"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="dir-op", password="pw")


@pytest.fixture
def other(db):
    return get_user_model().objects.create_user(username="dir-other", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="dir-op", password="pw")
    return c


def _make(user, cid: str, agent: str, title: str, texts=("hello", "hi there")):
    from swarm.core.chat_repository import append_message

    row = ChatConversation.objects.create(
        conversation_id=cid, student=user, agent_id=agent, title=title
    )
    for index, text in enumerate(texts):
        append_message(
            user,
            agent,
            cid,
            {"role": "user" if index % 2 == 0 else "assistant", "content": text},
        )
    return row


def _rows(cid: str) -> list[str]:
    return list(
        ChatMessage.objects.filter(conversation__conversation_id=cid)
        .order_by("timestamp", "id")
        .values_list("content", flat=True)
    )


# --------------------------------------------------------------------------- #
# list shape
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_list_returns_id_title_type_and_members(client, user):
    _make(user, DM_CID, "codey", "Kitchen reno")
    resp = client.get("/v1/conversations/")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["object"] == "conversation_list"
    by_id = {row["id"]: row for row in body["conversations"]}
    assert DM_CID in by_id, by_id

    row = by_id[DM_CID]
    assert set(("id", "title", "type", "members")) <= set(row), row
    assert row["id"] == DM_CID
    assert row["title"] == "Kitchen reno"
    assert row["type"] == "dm", row
    assert row["members"] == ["codey"], row
    assert row["message_count"] == 2, row


@pytest.mark.django_db
def test_a_multi_member_seat_is_reported_as_a_room(client, user, tmp_path, monkeypatch):
    """``type: room`` and ``members[]`` are derived, not invented.

    A conversation whose seat is a team roster is a room: the roster is the only
    multi-member grouping this product has, and ``rig_addresses`` already models
    it as a static rig. Everything else is a direct thread with one seat.
    """
    roster_file = tmp_path / "team_rosters.json"
    roster_file.write_text(
        '{"ops": {"id": "ops", "name": "Ops", "blueprint_id": "sre_team",'
        ' "members": [{"id": "sre_team", "kind": "team", "name": "SRE"},'
        ' {"id": "oncall_bot", "kind": "api", "name": "Oncall"}]}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("swarm.core.team_rosters.team_rosters_path", lambda: roster_file)
    # The roster store memoises in a module global; drop it either side so this
    # test does not read a roster another test left cached.
    from swarm.core.team_rosters import reset_team_rosters

    reset_team_rosters()
    try:
        _make(user, ROOM_CID, "sre_team", "Oncall")
        resp = client.get("/v1/conversations/")
    finally:
        reset_team_rosters()
    assert resp.status_code == 200, resp.content
    row = {r["id"]: r for r in resp.json()["conversations"]}[ROOM_CID]
    assert row["type"] == "room", row
    assert row["members"] == ["sre_team", "oncall_bot"], row
    assert row["title"] == "Oncall"


@pytest.mark.django_db
def test_list_is_scoped_to_the_caller(client, user, other):
    _make(user, DM_CID, "codey", "Mine")
    _make(other, OTHER_CID, "codey", "Theirs")
    resp = client.get("/v1/conversations/")
    ids = [row["id"] for row in resp.json()["conversations"]]
    assert ids == [DM_CID], ids


@pytest.mark.django_db
def test_list_hides_trashed_and_purged_conversations(client, user):
    from swarm.core.chat_repository import archive_agent, empty_trash

    # Trashed: a thread the user hid, which is not a place to hand work into.
    _make(user, DM_CID, "codey", "Trashed")
    assert archive_agent(user, "codey")
    assert empty_trash(user) == 1
    # Purged: an empty_trash tombstone from #1721, not a conversation at all.
    _make(user, ROOM_CID, "sre_team", "Purged")
    assert archive_agent(user, "sre_team")
    assert empty_trash(user) == 1
    assert ChatConversation.objects.get(conversation_id=DM_CID).purged_at is not None
    assert ChatConversation.objects.get(conversation_id=ROOM_CID).purged_at is not None

    ids = [row["id"] for row in client.get("/v1/conversations/").json()["conversations"]]
    assert DM_CID not in ids, ids
    assert ROOM_CID not in ids, ids


@pytest.mark.django_db
def test_list_hides_a_soft_trashed_conversation(client, user):
    from swarm.core.chat_repository import archive_agent

    _make(user, DM_CID, "codey", "Hidden")
    assert archive_agent(user, "codey")
    row = ChatConversation.objects.get(conversation_id=DM_CID)
    assert row.purged_at is None, "archive is a soft delete"
    assert [r["id"] for r in client.get("/v1/conversations/").json()["conversations"]] == []


@pytest.mark.django_db
def test_list_rejects_a_nonsense_limit(client, user):
    _make(user, DM_CID, "codey", "Mine")
    assert client.get("/v1/conversations/?limit=abc").status_code == 400
    assert client.get("/v1/conversations/?limit=-1").status_code == 400
    assert client.get("/v1/conversations/?limit=1").status_code == 200


# --------------------------------------------------------------------------- #
# handoff by conversation id
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_handoff_lands_in_the_named_conversation(client, user):
    _make(user, DM_CID, "codey", "Kitchen reno")
    resp = client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "carrying the tile count over", "from_conversation_id": ROOM_CID},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["delivered"] is True
    assert body["conversation"]["id"] == DM_CID
    assert body["conversation"]["message_count"] == 3

    assert _rows(DM_CID) == ["hello", "hi there", "carrying the tile count over"]
    # The canonical store is what moved. No second list was involved.
    assert ChatConversation.objects.filter(conversation_id=DM_CID).count() == 1
    # The derived cache agrees, which is what makes a reload show the handoff.
    record = chat_store.load(chat_store.user_key_for(user), "codey", conversation_id=DM_CID)
    assert [m["content"] for m in record["messages"]][-1] == "carrying the tile count over"


@pytest.mark.django_db
def test_handoff_rejects_an_unknown_conversation(client, user):
    _make(user, DM_CID, "codey", "Mine")
    resp = client.post(
        "/v1/conversations/conv-does-not-exist/handoff/",
        data={"message": "hello?"},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_conversation"
    assert ChatMessage.objects.filter(content="hello?").count() == 0


@pytest.mark.django_db
def test_handoff_rejects_a_conversation_owned_by_someone_else(client, user, other):
    """AuthZ: no cross-tenant leak, in either direction.

    Not merely "it does not write" — the response must not confirm the id
    exists, or the endpoint becomes a probe for other people's thread names.
    """
    _make(other, OTHER_CID, "codey", "Theirs")
    _make(user, DM_CID, "codey", "Mine")

    forbidden = client.post(
        f"/v1/conversations/{OTHER_CID}/handoff/",
        data={"message": "let me in"},
        content_type="application/json",
    )
    assert forbidden.status_code == 404
    assert forbidden.json()["error"] == "unknown_conversation"

    unknown = client.post(
        "/v1/conversations/conv-nope-000000000000000/handoff/",
        data={"message": "let me in"},
        content_type="application/json",
    )
    assert unknown.status_code == 404
    # Byte-identical: the caller cannot tell "not yours" from "not real".
    assert unknown.json() == forbidden.json() | {"conversation_id": unknown.json()["conversation_id"]}

    assert _rows(OTHER_CID) == ["hello", "hi there"], "another tenant's thread was written to"

    # …and the other tenant can post into their own.
    theirs = Client()
    theirs.login(username="dir-other", password="pw")
    ok = theirs.post(
        f"/v1/conversations/{OTHER_CID}/handoff/",
        data={"message": "mine to write"},
        content_type="application/json",
    )
    assert ok.status_code == 200
    assert _rows(OTHER_CID)[-1] == "mine to write"


@pytest.mark.django_db
def test_handoff_validates_its_payload(client, user):
    _make(user, DM_CID, "codey", "Mine")
    assert client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "   "},
        content_type="application/json",
    ).status_code == 400
    assert client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "ok", "role": "wizard"},
        content_type="application/json",
    ).status_code == 400
    assert client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "x" * 9000},
        content_type="application/json",
    ).status_code == 400
    assert _rows(DM_CID) == ["hello", "hi there"]


@pytest.mark.django_db
def test_handoff_does_not_rebuild_the_thread_from_a_short_cache(client, user):
    """A handoff must not reopen the #1722 hole.

    The cache file is short (a failed write, a second worker). The handoff adds
    one row; it must not reconcile the whole transcript against the file and
    delete the rows the file never saw.
    """
    _make(user, DM_CID, "codey", "Mine", texts=("turn one", "answer two", "turn three"))
    assert _rows(DM_CID) == ["turn one", "answer two", "turn three"]

    path = chat_store.store_dir() / "active" / chat_store.user_key_for(user) / f"codey__{DM_CID}.json"
    record = chat_store.load(chat_store.user_key_for(user), "codey", conversation_id=DM_CID)
    path.write_text(
        chat_store.json.dumps(
            {**record, "messages": [m for m in record["messages"] if m["content"] == "turn one"]},
            indent=2,
        ),
        encoding="utf-8",
    )
    assert len(chat_store.load(chat_store.user_key_for(user), "codey", conversation_id=DM_CID)["messages"]) == 1

    resp = client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "handoff line"},
        content_type="application/json",
    )
    assert resp.status_code == 200
    assert _rows(DM_CID) == ["turn one", "answer two", "turn three", "handoff line"]


@pytest.mark.django_db
def test_handoff_cannot_revive_a_purged_conversation(client, user):
    """#1721's tombstone also closes this door."""
    from swarm.core.chat_repository import archive_agent, empty_trash

    _make(user, DM_CID, "codey", "Gone")
    archive_agent(user, "codey")
    empty_trash(user)
    assert ChatConversation.objects.get(conversation_id=DM_CID).purged_at is not None

    resp = client.post(
        f"/v1/conversations/{DM_CID}/handoff/",
        data={"message": "back from the dead"},
        content_type="application/json",
    )
    assert resp.status_code == 404
    assert _rows(DM_CID) == []
    with pytest.raises(ConversationNotFound):
        resolve_conversation(user, DM_CID)


# --------------------------------------------------------------------------- #
# move-topic (the optional-but-preferred item)
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_move_topic_parks_a_summary_in_the_target(client, user):
    _make(user, DM_CID, "codey", "Source")
    _make(user, ROOM_CID, "sre_team", "Target room")
    resp = client.post(
        f"/v1/conversations/{ROOM_CID}/move/",
        data={"summary": "Tile count is 42; waiting on the supplier.", "source_conversation_id": DM_CID},
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["moved"] is True
    assert body["conversation"]["id"] == ROOM_CID

    parked = _rows(ROOM_CID)[-1]
    assert "Tile count is 42" in parked
    assert DM_CID in parked, "the parked summary must say where it came from"
    # The source keeps its own history. A move that drained the source would be
    # a data-loss bug dressed as a feature.
    assert _rows(DM_CID) == ["hello", "hi there"]


@pytest.mark.django_db
def test_move_topic_rejects_a_foreign_source(client, user, other):
    _make(other, OTHER_CID, "codey", "Theirs")
    _make(user, ROOM_CID, "sre_team", "Target room")
    resp = client.post(
        f"/v1/conversations/{ROOM_CID}/move/",
        data={"summary": "sneaky", "source_conversation_id": OTHER_CID},
        content_type="application/json",
    )
    assert resp.status_code == 404
    # The refusal names the offending id, not the target.
    assert resp.json()["conversation_id"] == OTHER_CID
    assert len(_rows(ROOM_CID)) == 2, "nothing should have been parked"


@pytest.mark.django_db
def test_move_topic_requires_a_summary(client, user):
    _make(user, ROOM_CID, "sre_team", "Target room")
    assert client.post(
        f"/v1/conversations/{ROOM_CID}/move/",
        data={"summary": ""},
        content_type="application/json",
    ).status_code == 400


# --------------------------------------------------------------------------- #
# the layer itself
# --------------------------------------------------------------------------- #


@pytest.mark.django_db
def test_the_module_is_a_projection_not_a_registry(user):
    """Calling the helpers directly must not create or cache anything.

    The acceptance criterion is "reuse existing conversation/session stores; do
    not create a second chat registry". A process-global list would show up here
    as a second source of truth: a row created directly in the database has to
    show up in ``list_conversations`` with no prior call to anything else.
    """
    _make(user, DM_CID, "codey", "Direct")
    assert [row["id"] for row in list_conversations(user)] == [DM_CID]

    from swarm.core import conversation_directory

    assert not hasattr(conversation_directory, "_CONVERSATIONS")
    assert not hasattr(conversation_directory, "CONVERSATIONS")

    # A row written by a *different* code path (a composer send) is visible,
    # because there is only one store.
    from swarm.core.chat_repository import append_message

    append_message(user, "codey", DM_CID, {"role": "user", "content": "from elsewhere"})
    assert [row["id"] for row in list_conversations(user)] == [DM_CID]
    assert list_conversations(user)[0]["message_count"] == 3


@pytest.mark.django_db
def test_helpers_refuse_an_anonymous_caller(user):
    from django.contrib.auth.models import AnonymousUser

    assert list_conversations(AnonymousUser()) == []
    assert list_conversations(None) == []
    with pytest.raises(ConversationNotFound):
        post_to_conversation(AnonymousUser(), DM_CID, {"content": "hi"})
    with pytest.raises(ConversationNotFound):
        move_topic(AnonymousUser(), DM_CID, "hi")

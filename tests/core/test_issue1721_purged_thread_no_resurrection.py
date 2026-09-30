"""Issue #1721 — a permanently deleted conversation must not come back.

``AGENTS.md`` §3 says the Django database is canonical, the ``chat_store`` JSON
file is a derived cache refreshed *after* the database write, and the one-way
import only runs "when the DB thread is empty". ``empty_trash`` broke both
halves of that at once: it ``DELETE``d the ``ChatConversation`` row *and* left
the per-conversation ``active/<agent>__<cid>.json`` file behind. The next
``load_thread`` therefore saw an empty DB thread (no row), found the orphan
file, and re-imported it — content returned to the UI *and* was written back
into the database. The user asked for erasure and got a recoverable thread.

The reproduction is the issue's own HTTP sequence, driven through the real
endpoints so nothing about it depends on an internal being called in a
particular order.

Fix under test: a durable tombstone. ``ChatConversation.purged_at`` retires the
id, every read/write predicate honours it, and ``empty_trash`` also unlinks the
cache file. Deletion is then a property of the *id*, not of a file that has to
be found and cleaned up in the right order.
"""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.models import ChatConversation, ChatMessage

AGENT = "grok"
# The shape ``create_empty_session`` mints, i.e. the "New session" button.
CID = "sess-1-grok-abcdef123456"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="purged-op", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="purged-op", password="pw")
    return c


def _rows(cid: str) -> list[str]:
    return list(
        ChatMessage.objects.filter(conversation__conversation_id=cid)
        .order_by("timestamp", "id")
        .values_list("content", flat=True)
    )


def _thread_path(user, agent: str, cid: str):
    return chat_store.store_dir() / "active" / chat_store.user_key_for(user) / f"{agent}__{cid}.json"


def _send(client, cid: str, texts: tuple[str, ...], agent: str = AGENT):
    """Drive the public composer endpoint so the writes are production-shaped."""
    for role, text in zip(("user", "assistant") * len(texts), texts):
        resp = client.post(
            f"/chat/thread/?agent={agent}",
            data=json.dumps({"conversation_id": cid, "message": {"role": role, "content": text}}),
            content_type="application/json",
        )
        assert resp.status_code == 200, resp.content


@pytest.mark.django_db
def test_empty_trash_does_not_resurrect_the_conversation(client, user):
    """THE bug: archive -> empty trash -> load must stay empty, forever.

    Before the fix, step 4 returned ``["SECRET", "reply"]`` and re-created the
    ``ChatMessage`` rows.
    """
    # 1. Save a conversation with distinctive text. Rows exist; the per-session
    #    cache file exists.
    _send(client, CID, ("SECRET", "reply"))
    assert _rows(CID) == ["SECRET", "reply"]
    assert _thread_path(user, AGENT, CID).is_file()

    # 2. Archive the agent.
    resp = client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    # 3. Empty the trash. This is the destructive step.
    resp = client.post("/settings/chats/action/", {"action": "empty_trash"})
    assert resp.status_code == 200
    assert resp.json()["removed"] == 1
    assert _rows(CID) == [], "empty_trash left canonical rows behind"

    # 4. Load the thread. This is where the content came back.
    resp = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={CID}")
    assert resp.status_code == 200
    assert resp.json()["messages"] == [], (
        "permanently deleted content was served back after empty_trash"
    )
    # …and the rows must stay deleted. A second load is the honest check: the
    # first one is the one that re-imports, so it can leave a trace that makes
    # a single assertion look satisfied.
    resp = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={CID}")
    assert resp.json()["messages"] == [], "content resurrected on the second load"
    assert _rows(CID) == [], "the load re-created the ChatMessage rows"


@pytest.mark.django_db
def test_a_purged_id_is_retired_not_recreated(client, user):
    """The tombstone is the fix, so assert the tombstone directly.

    A purged id must stay a purged id no matter what a cache file claims. This
    is the part that survives a cache file written *after* the delete — by a
    second process, by a racing writer, by hand.
    """
    _send(client, CID, ("SECRET", "reply"))
    client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    client.post("/settings/chats/action/", {"action": "empty_trash"})

    row = ChatConversation.objects.get(conversation_id=CID)
    assert row.purged_at is not None
    # The content really is gone; only the retirement marker survives.
    assert not row.chat_messages.exists()
    assert row.title == ""
    assert row.snippet == ""

    # A cache file reappears afterwards — a stale writer, another process, a
    # restore of an old backup. It must not be able to write anything back.
    chat_store.save(
        chat_store.user_key_for(user),
        AGENT,
        [{"role": "user", "content": "SECRET"}, {"role": "assistant", "content": "reply"}],
        conversation_id=CID,
        session_id=CID,
        mirror_db=False,
    )
    assert _thread_path(user, AGENT, CID).is_file(), "probe did not reproduce the stale-cache shape"

    for _ in range(2):
        loaded = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={CID}")
        assert loaded.json()["messages"] == []
    assert _rows(CID) == [], "a stale cache file re-imported a purged conversation"
    assert ChatConversation.objects.get(conversation_id=CID).purged_at is not None


@pytest.mark.django_db
def test_purged_title_and_snippet_do_not_come_back_in_the_picker(client, user):
    """A trashed session's title/snippet must not reappear (#1721 scope).

    ``list_agent_sessions`` -> ``import_disk_sessions`` re-created the row *and*
    rebuilt its title and snippet from the deleted content, so the session
    picker offered the user a ghost built from the first message they had
    permanently deleted.
    """
    _send(client, CID, ("SECRET", "reply"))
    client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    client.post("/settings/chats/action/", {"action": "empty_trash"})

    # Put the orphan file back: the picker is exactly the path that used to
    # resurrect it, and it runs on every session list.
    chat_store.save(
        chat_store.user_key_for(user),
        AGENT,
        [{"role": "user", "content": "SECRET"}, {"role": "assistant", "content": "reply"}],
        conversation_id=CID,
        session_id=CID,
        mirror_db=False,
    )

    from swarm.core.agent_sessions import list_agent_sessions, session_to_dict

    listed = session_to_dict(list_agent_sessions(user, AGENT)[0])
    assert "SECRET" not in str(listed), listed
    assert listed["snippet"] == "", listed
    assert CID not in str(listed["id"]), listed
    ids = [row.conversation_id for row in list_agent_sessions(user, AGENT)]
    assert CID not in ids, f"a purged session is back in the picker: {ids}"


@pytest.mark.django_db
def test_single_archive_moves_the_session_file_too(client, user):
    """``archive_all`` already moved session files; single ``archive`` did not.

    That asymmetry is the mechanism: an archived-but-not-moved
    ``<agent>__<cid>.json`` is the fuel the one-way import burns, so the two
    entry points have to agree. Asserted separately for each, because running
    both in one test lets ``archive_all`` clean up after the broken one.
    """
    root = chat_store.store_dir() / "active" / chat_store.user_key_for(user)
    _send(client, CID, ("SECRET", "reply"))
    assert _thread_path(user, AGENT, CID).is_file()

    resp = client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert not _thread_path(user, AGENT, CID).is_file(), (
        "single archive left the session file in active/ -- it can be re-imported"
    )
    assert sorted(p.name for p in root.glob("*.json")) == []
    trashed = sorted(
        p.name
        for p in (chat_store.store_dir() / "trash" / chat_store.user_key_for(user)).glob("*.json")
    )
    assert trashed, "archive moved nothing to trash"


@pytest.mark.django_db
def test_archive_all_moves_the_session_files_too(client, user):
    """The behaviour single ``archive`` now matches."""
    root = chat_store.store_dir() / "active" / chat_store.user_key_for(user)
    for agent in ("grok", "claude"):
        cid = f"sess-1-{agent}-feedface654321"
        _send(client, cid, (f"{agent} secret",), agent=agent)
        assert _thread_path(user, agent, cid).is_file(), agent

    resp = client.post("/settings/chats/action/", {"action": "archive_all"})
    assert resp.status_code == 200
    assert sorted(p.name for p in root.glob("*.json")) == []
    trashed = sorted(
        p.name
        for p in (chat_store.store_dir() / "trash" / chat_store.user_key_for(user)).glob("*.json")
    )
    assert len(trashed) == 2, trashed


@pytest.mark.django_db
def test_archive_all_reports_seat_ids_not_file_stems(client, user):
    """``archive_all``'s response listed file stems as agent ids.

    ``chat_store.list_active`` set ``agent_id = path.stem``, so a per-conversation
    thread was reported as an agent called
    ``claude__sess-1-claude-feedface654321``. The caller renders these as seat
    names in the Settings response, so a "Move to trash" confirmation named a
    conversation id as though it were a seat.
    """
    for agent in ("grok", "claude"):
        _send(client, f"sess-1-{agent}-beefbeef654321", (f"{agent} secret",), agent=agent)

    resp = client.post("/settings/chats/action/", {"action": "archive_all"})
    assert resp.status_code == 200
    assert sorted(resp.json()["archived"]) == ["claude", "grok"]


@pytest.mark.django_db
def test_retention_sweep_then_empty_trash_also_stays_gone(client, user):
    """``prune_expired`` -> ``empty_trash`` is the automated retention path."""
    from datetime import timedelta

    from swarm.core.chat_repository import _now, empty_trash, prune_expired

    _send(client, CID, ("SECRET", "reply"))
    # A clock past the retention window, so the sweep really runs.
    archived = prune_expired(
        user,
        max_age_days=1,
        now=_now() + timedelta(days=2),
        base_dir=chat_store.store_dir(),
    )
    assert archived, "prune_expired archived nothing, so the sweep was not exercised"
    assert empty_trash(user, base_dir=chat_store.store_dir()) == 1

    for _ in range(2):
        loaded = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={CID}")
        assert loaded.json()["messages"] == []
    assert _rows(CID) == []


@pytest.mark.django_db
def test_trash_soft_delete_is_still_restorable(client, user):
    """The tombstone must not turn ``trash`` into ``purge``.

    Guards the boundary: archive -> restore has to keep working, or the fix
    would have quietly made every archive a hard delete.
    """
    _send(client, CID, ("SECRET", "reply"))
    client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    row = ChatConversation.objects.get(conversation_id=CID)
    assert row.trashed_at is not None
    assert row.purged_at is None, "archive must not write the hard-delete marker"

    resp = client.post("/settings/chats/action/", {"action": "restore", "agent_id": AGENT})
    assert resp.status_code == 200
    row.refresh_from_db()
    assert row.trashed_at is None
    loaded = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={CID}")
    assert [m["content"] for m in loaded.json()["messages"]] == ["SECRET", "reply"]
    assert _rows(CID) == ["SECRET", "reply"]


@pytest.mark.django_db
def test_a_purged_default_seat_mints_a_fresh_conversation(client, user):
    """The derived default id is not random, so it has to be handled.

    ``conversation_id_for`` is ``agt-<pk>-<agent>``. After the user empties the
    trash, the very next session list derives the *same* id again. Reusing the
    tombstone would hand the seat a thread nothing can ever write to.
    """
    default_cid = chat_store.conversation_id_for(user, AGENT)
    _send(client, default_cid, ("SECRET", "reply"))
    client.post("/settings/chats/action/", {"action": "archive", "agent_id": AGENT})
    client.post("/settings/chats/action/", {"action": "empty_trash"})
    assert ChatConversation.objects.get(conversation_id=default_cid).purged_at is not None

    from swarm.core.agent_sessions import list_agent_sessions

    ids = [row.conversation_id for row in list_agent_sessions(user, AGENT)]
    assert default_cid not in ids, f"the seat was handed its retired id again: {ids}"
    assert ids, "the seat must still have a usable conversation"

    # …and the fresh id actually works.
    fresh = ids[0]
    _send(client, fresh, ("hello again",))
    loaded = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={fresh}")
    assert [m["content"] for m in loaded.json()["messages"]] == ["hello again"]
    assert _rows(default_cid) == [], "the retired id accepted a write"

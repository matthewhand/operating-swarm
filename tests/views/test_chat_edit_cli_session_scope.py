"""REQ-808 — an edit must clear the CLI session on THAT conversation, not the seat.

Editing a message restarts the provider session, so ``PATCH /chat/thread/``
clears the stored CLI session id for every CLI the edited thread touched. Since
#1690 that id lives on the *conversation's own* record
(``<agent>__<conversation_id>.json``) rather than one id per agent, precisely so
two conversations in the same seat cannot resume each other's host session.

A clear that does not name the conversation therefore clears the wrong record:
the edited conversation keeps the id its very next turn is about to resume, and
an unrelated default conversation in the same seat loses its own id instead.
``cli_sessions.thread_session_id`` owns the "which file holds THIS thread" rule;
the view only has to ask it about the right thread.

Reachability, stated honestly: the loop that collects the involved CLIs reads
``turn["cli_name"]``, and no stored turn can carry that key.
``chat_store._normalize_messages`` rebuilds every turn from a whitelist on *both*
the write and the read, and ``chat_db._TURN_EXTRA_KEYS`` has no such slot
either, so ``involved_clis`` is empty on every path the store can produce. The
branch is dead code, not merely unexercised. These tests still pin it, because a
call with a stale contract is a trap for whoever wires it up: the view tests
hand the loader a thread that names a CLI (the only way to reach the branch)
and then assert, on real files on disk, which record the clear landed on. The
last test pins the store-level contract they rely on, which *is* live.
"""

from __future__ import annotations

import dataclasses
import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core.cli_sessions import clear_cli_session, get_cli_session, put_cli_session

SEAT = "cli-grok"
# A non-default conversation. ``chat_repository._session_id_for`` files it under
# ``<seat>__<conversation_id>.json``; the seat's default thread stays ``<seat>.json``.
CONVERSATION = "chat-edit-cli-session-scope"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="edit-cli-scope", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="edit-cli-scope", password="pw")
    return c


@pytest.fixture
def names_the_cli(monkeypatch):
    """Make the loaded thread name the CLI it was talking to.

    The store cannot represent ``cli_name`` (module docstring), so this is the
    only way to open the branch. Everything downstream of the loader — the
    conversation the view resolves, the transcript write, and the
    ``clear_cli_session`` call and its file writes — is the real thing.
    """
    from swarm.views import chat_persist_views

    real_load_thread = chat_persist_views.load_thread

    def _load(*args, **kwargs):
        loaded = real_load_thread(*args, **kwargs)
        turns = [
            {**turn, "cli_name": "grok"} if turn.get("role") == "assistant" else turn
            for turn in loaded.turns
        ]
        return dataclasses.replace(loaded, turns=turns)

    monkeypatch.setattr(chat_persist_views, "load_thread", _load)


def _seed(user, turns, *, conversation_id, session_id, cli_sessions):
    return chat_store.save(
        chat_store.user_key_for(user),
        SEAT,
        turns,
        conversation_id=conversation_id,
        session_id=session_id,
        cli_sessions=cli_sessions,
        mirror_db=False,
    )


def _default_record(user):
    return chat_store.load(chat_store.user_key_for(user), SEAT) or {}


def _conversation_record(user, conversation_id=CONVERSATION):
    return chat_store.load(
        chat_store.user_key_for(user), SEAT, session_id=conversation_id
    ) or {}


def _patch(client, content, *, conversation_id):
    resp = client.patch(
        f"/chat/thread/?agent={SEAT}&conversation_id={conversation_id}",
        data=json.dumps({"index": 0, "content": content}),
        content_type="application/json",
    )
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["session_reset"] is True
    assert body["cli_session_reset"] is True
    return body


def _seed_two_conversations(user):
    """Two live conversations in one seat, each with its own CLI session ids."""
    default_cid = chat_store.conversation_id_for(user, SEAT)
    assert default_cid != CONVERSATION, "the seed conversation must not be the default"
    _seed(
        user,
        [{"role": "user", "content": "a different question"}],
        conversation_id=default_cid,
        session_id="",
        cli_sessions={"grok": "default-host-sess", "codex": "default-codex-sess"},
    )
    _seed(
        user,
        [
            {"role": "user", "content": "engineer this"},
            {"role": "assistant", "content": "sure"},
        ],
        conversation_id=CONVERSATION,
        session_id=CONVERSATION,
        cli_sessions={"grok": "conv-host-sess", "codex": "conv-codex-sess"},
    )
    return default_cid


@pytest.mark.django_db
def test_edit_clears_the_id_on_the_edited_conversation_only(
    client, user, names_the_cli
):
    """THE regression: the clear follows the conversation, not the seat.

    Before the fix the view called ``clear_cli_session`` with no conversation
    id, so the clear resolved to the agent's default record: the edited
    conversation kept ``conv-host-sess`` (its next turn would have resumed it)
    and the default thread lost ``default-host-sess`` for no reason at all.
    """
    _seed_two_conversations(user)

    body = _patch(client, "engineered question", conversation_id=CONVERSATION)
    assert body["messages"][0]["content"] == "engineered question"

    # The edited conversation gave up the host session it was resumed into…
    assert _conversation_record(user)["cli_sessions"] == {"codex": "conv-codex-sess"}
    # …and the unrelated default conversation kept both of its own.
    assert _default_record(user)["cli_sessions"] == {
        "grok": "default-host-sess",
        "codex": "default-codex-sess",
    }


@pytest.mark.django_db
def test_edit_clears_only_the_cli_the_thread_named(client, user, names_the_cli):
    """The clear is driven by the thread's turns, not by the record's contents.

    A record-wide wipe would be a second, subtler way to get this wrong: it
    would drop an id for a CLI the user never ran in the edited conversation.
    """
    _seed_two_conversations(user)

    _patch(client, "engineered question", conversation_id=CONVERSATION)

    conv = _conversation_record(user)
    assert "grok" not in conv["cli_sessions"]
    assert conv["cli_sessions"]["codex"] == "conv-codex-sess"
    assert _default_record(user)["cli_sessions"]["grok"] == "default-host-sess"


@pytest.mark.django_db
def test_edit_on_the_default_conversation_still_clears_the_default_record(
    client, user, names_the_cli
):
    """The pre-existing behaviour must survive the fix.

    ``thread_session_id`` maps the owner's default conversation to the empty
    stem — the reuse file ``<seat>.json`` — so threading the conversation id
    through has to land on exactly the record it did before.
    """
    default_cid = chat_store.conversation_id_for(user, SEAT)
    _seed(
        user,
        [
            {"role": "user", "content": "engineer this"},
            {"role": "assistant", "content": "sure"},
        ],
        conversation_id=default_cid,
        session_id="",
        cli_sessions={"grok": "default-host-sess"},
    )
    # A sibling conversation, so a clear that wandered off would be visible.
    _seed(
        user,
        [{"role": "user", "content": "other"}],
        conversation_id=CONVERSATION,
        session_id=CONVERSATION,
        cli_sessions={"grok": "conv-host-sess"},
    )

    _patch(client, "engineered question", conversation_id=default_cid)

    assert _default_record(user)["cli_sessions"] == {}
    assert _conversation_record(user)["cli_sessions"] == {"grok": "conv-host-sess"}


@pytest.mark.django_db
def test_a_conversation_scoped_clear_leaves_the_default_record_alone(db):
    """The contract the view now depends on, exercised through the real store.

    Unlike the view tests above this one needs no seam: ``put_cli_session`` is
    the production writer for these ids and ``thread_session_id`` is the
    production rule for which file holds a given thread. Two conversations in
    one seat each hold an id, and a clear naming one leaves the other alone.
    """
    user = get_user_model().objects.create_user(username="clear-scope", password="pw")
    user_key = chat_store.user_key_for(user)
    default_cid = chat_store.conversation_id_for(user, SEAT)

    put_cli_session(
        user_key, SEAT, "grok", "default-host-sess", conversation_id=default_cid
    )
    put_cli_session(
        user_key, SEAT, "grok", "conv-host-sess", conversation_id=CONVERSATION
    )
    assert get_cli_session(user_key, SEAT, "grok", conversation_id=default_cid) == (
        "default-host-sess"
    )
    assert get_cli_session(user_key, SEAT, "grok", conversation_id=CONVERSATION) == (
        "conv-host-sess"
    )

    clear_cli_session(user_key, SEAT, "grok", conversation_id=CONVERSATION)

    # The named conversation gave up its id…
    assert get_cli_session(user_key, SEAT, "grok", conversation_id=CONVERSATION) is None
    assert _conversation_record(user)["cli_sessions"] == {}
    # …and the seat's default conversation still has its own, in its own file.
    assert get_cli_session(user_key, SEAT, "grok", conversation_id=default_cid) == (
        "default-host-sess"
    )
    assert _default_record(user)["cli_sessions"] == {"grok": "default-host-sess"}

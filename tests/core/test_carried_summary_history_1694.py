"""#1694 — a carried summary must be READABLE BACK in the chat's own history.

The hop announces itself: ``hop_backend`` appends a ``context_carried`` status
line reading ``Started a new X session (a → b). Carried summary context (N
tokens).``  That line is chrome, and chrome says only that *something* was
carried. The thing itself — the redacted injection blob the new session was
actually seeded with — lived only in the transient ``cli_hop`` pending record,
which ``consume_pending_hop`` clears on the next turn. After that turn, and
after any page reload, the chat's own history could not tell the user what
their next message was built on.

So these tests do not assert that a string appears in the transcript. They
assert the summary is *recoverable from history*: the chat's canonical store is
re-read from scratch the way a reload reads it, and the summary is still there.

Where it is recorded, and why it can be read back:

* the hop writes the summary onto the ``context_carried`` **ui event**, which is
  the chat's own side channel and is stored in ``ChatConversation.ui_events``;
* a ui event is NOT a ``ChatMessage`` row, so ``chat_db._TURN_EXTRA_KEYS`` does
  not apply to it — ``extra_from_turn`` only runs for model turns. The two
  whitelists a ui event actually crosses are ``chat_store._normalize_messages``
  (the derived cache) and ``thread_load.public_message`` (the HTTP/WS
  projection). Both are fixed-key rebuilds, so the summary has to be carried by
  both or it silently vanishes; that is what the parity test below pins.

No test here asserts on a source substring, and none of them weaken an
assertion to stay green.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core.chat_db import load_db_thread
from swarm.core.cli_session_hop import consume_pending_hop, hop_backend
from swarm.core.thread_load import load_thread, public_message

AGENT = "cli_agent"
THREAD = "agt-h1694-cli_agent"

# Two prior turns, so the hop has real content to carry. The secret is here to
# prove the stored summary is the REDACTED blob, not a second, unfiltered copy.
PRIOR = [
    {"role": "user", "content": "Design a rate limiter"},
    {"role": "assistant", "content": "Use a token bucket keyed by burst size."},
    {"role": "user", "content": "Now add the config flag, key=sk-h1694fixationaaaa"},
]
CARRIED_FRAGMENT = "token bucket"
REDACTED_FRAGMENT = "[REDACTED]"


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="h1694", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    assert c.login(username="h1694", password="pw")
    return c


def do_hop(user, tmp_path):
    """Seed a thread, hop grok → agy, and return the hop result."""
    uk = chat_store.user_key_for(user)
    chat_store.save(
        uk,
        AGENT,
        PRIOR,
        conversation_id=THREAD,
        cli_sessions={"grok": "sid-grok"},
        active_cli="grok",
        base_dir=tmp_path,
    )
    return hop_backend(
        uk,
        AGENT,
        from_cli="grok",
        to_cli="agy",
        conversation_id=THREAD,
        mode="summary",
        base_dir=tmp_path,
    )


def carried_events(loaded) -> list[dict]:
    """The ``context_carried`` chrome rows, from turns OR ui_events."""
    turns, events = (loaded or ([], []))
    rows = list(turns) + list(events)
    return [row for row in rows if isinstance(row, dict) and row.get("kind") == "context_carried"]


# --------------------------------------------------------------------------
# The defect. Each of these fails on the unfixed tree.
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_history_survives_the_next_turn_and_says_what_was_carried(user, tmp_path):
    """The summary is still in history AFTER the pending hop is consumed.

    This is the defect in one assertion. ``cli_hop`` is the only place the
    summary body used to live, and ``consume_pending_hop`` clears it — so
    before the fix, the moment the user sends their next message, the record of
    what that message was built on was gone.
    """
    do_hop(user, tmp_path)
    consume_pending_hop(
        chat_store.user_key_for(user),
        AGENT,
        "agy",
        conversation_id=THREAD,
        base_dir=tmp_path,
    )

    loaded = load_db_thread(user, THREAD)
    events = carried_events(loaded)
    assert len(events) == 1, (
        "the context_carried boundary marker must survive into the canonical "
        f"store; got {[e.get('kind') for e in (loaded[0] + loaded[1])]}"
    )
    summary = events[0].get("carried_summary")
    assert summary, (
        "the context_carried event must carry the summary body; today it only "
        f"announces one. event={events[0]!r}"
    )
    assert CARRIED_FRAGMENT in summary["text"], summary
    assert summary["from_cli"] == "grok"
    assert summary["to_cli"] == "agy"
    assert summary["tokens"] > 0
    assert isinstance(summary["omitted"], list) and summary["omitted"]


@pytest.mark.django_db
def test_history_survives_a_page_reload_reading_django_only(user, tmp_path):
    """A reload reads Django first and never the JSON cache.

    ``load_thread`` is the shared reload path (HTTP ``GET /chat/thread/`` and
    WS reconnect both call it). Deleting the cache directory first makes the
    test prove the summary is in the canonical store, not merely in a derived
    file that happened to still be there.
    """
    import shutil

    do_hop(user, tmp_path)
    chat_dir = tmp_path / "chats"
    if chat_dir.exists():
        shutil.rmtree(chat_dir)

    loaded = load_thread(user, AGENT, requested_cid=THREAD)
    assert loaded.from_json is False, "the reload fell back to the JSON cache"
    events = carried_events((loaded.turns, loaded.events))
    assert len(events) == 1
    summary = events[0].get("carried_summary")
    assert summary, (
        "after a cache-free reload the history must still say what was "
        f"carried; event={events[0]!r}"
    )
    assert CARRIED_FRAGMENT in summary["text"]


@pytest.mark.django_db
def test_thread_endpoint_returns_the_summary_to_the_client(client, user, tmp_path):
    """The payload the browser actually receives carries the summary.

    ``public_message`` is a third fixed-key projection — the one the HTTP
    response and the websocket both go through. A summary that survives to
    Django but not through here is still invisible after a reload.
    """
    do_hop(user, tmp_path)

    resp = client.get(f"/chat/thread/?agent={AGENT}&conversation_id={THREAD}")
    assert resp.status_code == 200
    body = resp.json()
    rows = [r for r in (body.get("ui_events") or []) if r.get("kind") == "context_carried"]
    assert len(rows) == 1, f"thread payload lost the marker: {body.get('ui_events')!r}"
    summary = rows[0].get("carried_summary")
    assert summary, f"thread payload lost the summary body: {rows[0]!r}"
    assert CARRIED_FRAGMENT in summary["text"]
    assert summary["to_cli"] == "agy"


@pytest.mark.django_db
def test_stored_summary_is_the_redacted_blob_not_a_second_secret_copy(
    user, tmp_path
):
    """The stored text must be exactly the redacted thing that was seeded.

    Recording the summary creates a second durable copy of the injection. If it
    were the unredacted source, this feature would become a secret-at-rest
    surface that the existing ``redact_injection_text`` guarantee never covered.
    """
    result = do_hop(user, tmp_path)
    seeded = result["injection"]["text"]

    loaded = load_db_thread(user, THREAD)
    summary = carried_events(loaded)[0]["carried_summary"]
    assert summary["text"] == seeded
    assert "sk-h1694fixationaaaa" not in summary["text"]
    assert REDACTED_FRAGMENT in summary["text"]


@pytest.mark.django_db
def test_no_summary_is_claimed_when_nothing_was_carried(user, tmp_path):
    """An empty hop must not advertise a summary.

    ``hop_notice_text`` has an honest empty branch ("No prior context to
    carry"). Recording a summary for it would make the transcript claim
    context that does not exist — the exact dishonesty the issue is about.
    """
    uk = chat_store.user_key_for(user)
    chat_store.save(
        uk,
        AGENT,
        [],
        conversation_id=THREAD,
        active_cli="grok",
        base_dir=tmp_path,
    )
    result = hop_backend(
        uk,
        AGENT,
        from_cli="grok",
        to_cli="agy",
        conversation_id=THREAD,
        base_dir=tmp_path,
    )
    assert result["empty"] is True

    loaded = load_db_thread(user, THREAD)
    events = carried_events(loaded)
    assert len(events) == 1
    assert not events[0].get("carried_summary"), (
        "an empty hop must not record a summary body: " f"{events[0]!r}"
    )


# --------------------------------------------------------------------------
# Parity with the existing round-trip guarantees. These pass before and after
# the fix on purpose — they are the guard that stops a future #1722 (a key
# missing from one of the whitelists) from silently breaking the summary again.
# --------------------------------------------------------------------------


def test_summary_key_is_carried_by_both_ui_event_whitelists():
    """DELIBERATE NON-REGRESSION GUARD (passes before and after the fix).

    ``chat_store._normalize_messages`` and ``thread_load.public_message`` are
    both fixed-key rebuilds. ``#1722`` was exactly this: ``attachments`` was
    missing from one of them, so the link was dropped on the way to disk while
    every test still passed. This pins both for the summary key, so a future
    edit to either whitelist cannot quietly un-record a carried summary.
    """
    from swarm.core.chat_store import _normalize_events

    # A fully-populated row: every key the two projections must agree on.
    # Asserting the projections are EQUAL to each other (not to a hand-written
    # literal) is the property that matters — the two whitelists are the same
    # shape, so if one is edited and the other is not, this goes red.
    row = {
        "role": "status",
        "content": "Carried summary context (12 tokens).",
        "kind": "context_carried",
        "carried_summary": {
            "text": "BODY",
            "from_cli": "grok",
            "to_cli": "agy",
            "mode": "summary",
            "tokens": 12,
            "turn_count": 3,
            "omitted": ["secrets", "tool_noise"],
        },
    }
    cache_side = _normalize_events([row])[0].get("carried_summary")
    wire_side = public_message(row).get("carried_summary")
    assert cache_side, "chat_store._normalize_messages dropped carried_summary (cache side)"
    assert wire_side, "thread_load.public_message dropped carried_summary (HTTP/WS side)"
    assert cache_side == wire_side, (
        "the two ui_event whitelists disagree on the carried-summary shape: "
        f"cache={cache_side!r} wire={wire_side!r}"
    )
    assert cache_side["text"] == "BODY"
    assert (cache_side["from_cli"], cache_side["to_cli"]) == ("grok", "agy")
    assert cache_side["tokens"] == 12

    # And the rebuild must not smuggle an undeclared field through: a stored
    # row is untrusted input, exactly like every other value on this path.
    smuggled = _normalize_events(
        [{**row, "carried_summary": {**row["carried_summary"], "injected": "x"}}]
    )[0]["carried_summary"]
    assert "injected" not in smuggled, f"whitelist is not a whitelist: {smuggled!r}"


def test_carried_summary_is_not_a_model_turn():
    """DELIBERATE NON-REGRESSION GUARD (passes before and after the fix).

    A summary is a boundary marker, not conversation. It must stay on the UI
    side channel so it never reaches the model payload — otherwise the chat
    would be billed for re-sending its own context on every turn, and
    ``turns_for_injection`` would treat it as a carryable turn next time.
    """
    from swarm.core.transcript_roles import messages_for_model

    chrome = {
        "role": "status",
        "content": "Carried summary context (12 tokens).",
        "kind": "context_carried",
        "carried_summary": {"text": "BODY", "tokens": 12},
    }
    assert messages_for_model([chrome]) == []

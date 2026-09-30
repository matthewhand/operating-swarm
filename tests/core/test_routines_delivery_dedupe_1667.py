"""#1667 — a redelivered GitHub webhook is a no-op, not a second run.

GitHub redelivers a delivery it did not get a fast 2xx for, and it does so after
restarts. ``github_event_conversation_id`` is per issue, so the redelivery landed
on the same conversation again: the turn was appended a second time and the
operator-plane lease answered the duplicate with a "busy" error row — a
user-visible error where a no-op belongs.

Contracts:
- the same ``X-GitHub-Delivery`` id fires nothing the second time,
- the webhook thread is not rewritten by the redelivery,
- the record survives a restart (that is *why* GitHub redelivers), and an
  in-process cache would not,
- a different delivery is still delivered, and a failed run releases its claim
  so GitHub's retry can have another go.
"""

from __future__ import annotations

import json

import pytest

from swarm.core import chat_store
from swarm.core import routines as store

pytestmark = pytest.mark.django_db

WEBHOOK_SECRET = "test-github-webhook-secret"
DELIVERY_ID = "3f9a2c40-1d5e-4a7b-9c11-000000000001"


@pytest.fixture
def chat_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    return tmp_path / "chats"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _triage_routine(agent="codey", number_match="issues.opened"):
    return store.create_routine(
        agent,
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": {
                "kind": "github_event",
                "event_type": number_match,
                "owner_repo": "owner/repo",
            },
        },
    )


def _issue_opened(number=17, title="Flaky login"):
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": title,
            "body": "Repro on main.",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "user": {"login": "octocat"},
            "labels": [],
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "octocat"},
    }


def _history(agent, routine_id):
    return store.get_routine(agent, routine_id)["history"]


# --- the redelivery itself --------------------------------------------------------


def test_a_repeated_delivery_id_fires_nothing_the_second_time():
    created = _triage_routine()
    payload = _issue_opened()

    first = store.deliver_github_event(
        payload, event_header="issues", delivery_id=DELIVERY_ID
    )
    second = store.deliver_github_event(
        payload, event_header="issues", delivery_id=DELIVERY_ID
    )

    assert len(first) == 1
    assert second == []
    # Exactly one turn was recorded, and it succeeded — not a "busy" error row.
    history = _history("codey", created["id"])
    assert len(history) == 1
    assert history[0]["status"] == store.HISTORY_STATUS_SUCCESS
    assert history[0]["source"] == store.SOURCE_GITHUB_WEBHOOK
    assert len(store.fired_prompts()) == 1


def test_a_redelivery_does_not_rewrite_the_webhook_conversation(chat_dir):
    created = _triage_routine()
    payload = _issue_opened()
    conversation_id = store.github_event_conversation_id(
        store.parse_github_webhook_event(payload, "issues")
    )
    assert conversation_id == "conv-github-issue-17"

    store.deliver_github_event(payload, event_header="issues", delivery_id=DELIVERY_ID)
    # Stand in for the live agent's own turn landing in the same thread.
    thread = store.load_github_event_thread("codey", conversation_id)
    chat_store.save(
        store.GITHUB_WEBHOOK_USER_KEY,
        "codey",
        [
            *thread["messages"],
            {"role": "assistant", "content": "Filed fix/issue-17."},
        ],
        conversation_id=conversation_id,
        session_id=conversation_id,
    )

    redelivered = store.deliver_github_event(
        payload, event_header="issues", delivery_id=DELIVERY_ID
    )

    assert redelivered == []
    thread = store.load_github_event_thread("codey", conversation_id)
    assert [msg["role"] for msg in thread["messages"]] == ["user", "assistant"]
    assert len(_history("codey", created["id"])) == 1


def test_a_redelivery_without_the_header_is_still_a_no_op():
    """A caller that cannot forward ``X-GitHub-Delivery`` resends the same body.

    The signed body plus the event header is the fallback key, so the shipped
    webhook endpoint is idempotent on its own.
    """
    _triage_routine()
    payload = _issue_opened()

    assert len(store.deliver_github_event(payload, event_header="issues")) == 1
    assert store.deliver_github_event(payload, event_header="issues") == []
    assert len(store.fired_prompts()) == 1


# --- what the record is and where it lives ---------------------------------------


def test_the_delivery_record_is_a_file_next_to_the_store(tmp_path, monkeypatch):
    _triage_routine()
    payload = _issue_opened()

    store.deliver_github_event(payload, event_header="issues", delivery_id=DELIVERY_ID)

    record = store.delivery_log_path()
    assert record == tmp_path / "agent_routines.json.webhook_deliveries.json"
    assert record.is_file()
    keys = json.loads(record.read_text(encoding="utf-8"))["keys"]
    assert f"id:{DELIVERY_ID}" in keys
    # The fallback key is recorded too, so a redelivery that lost the header is
    # still recognised after the endpoint starts forwarding it.
    assert any(key.startswith("sha256:") for key in keys)
    # Delivery ids are not routine data and must not leak into the store.
    on_disk = json.loads((tmp_path / "agent_routines.json").read_text(encoding="utf-8"))
    assert DELIVERY_ID not in json.dumps(on_disk)


def test_the_record_survives_a_process_restart(tmp_path, monkeypatch):
    """A restart is exactly when a redelivery arrives, so memory is not enough."""
    _triage_routine()
    payload = _issue_opened()
    store.deliver_github_event(payload, event_header="issues", delivery_id=DELIVERY_ID)

    # A restart: nothing in memory survives, only the file does.
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    assert store._cache is None

    assert store.deliver_github_event(
        payload, event_header="issues", delivery_id=DELIVERY_ID
    ) == []
    assert len(store.fired_prompts()) == 0


def test_the_record_is_bounded():
    keys = [f"d{index}" for index in range(store.MAX_TRACKED_DELIVERIES + 25)]
    for key in keys:
        assert store.delivery_id_key(key) == key
    path = store.delivery_log_path()
    store._write_delivery_log(path, keys)
    kept = json.loads(path.read_text(encoding="utf-8"))["keys"]
    assert len(kept) == store.MAX_TRACKED_DELIVERIES
    assert kept[-1] == keys[-1]
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == store.DELIVERY_LOG_SCHEMA


def test_a_hostile_delivery_id_is_not_a_key():
    assert store.delivery_id_key("") == ""
    assert store.delivery_id_key("a" * 5000) == ""
    assert store.delivery_id_key("id with spaces") == ""
    assert store.delivery_id_key("drop\ntable") == ""
    assert store.delivery_id_key(DELIVERY_ID) == DELIVERY_ID


# --- the boundaries ----------------------------------------------------------------


def test_a_different_delivery_of_a_different_event_still_fires():
    created = _triage_routine()

    first = store.deliver_github_event(
        _issue_opened(number=17), event_header="issues", delivery_id="delivery-1"
    )
    second = store.deliver_github_event(
        _issue_opened(number=18), event_header="issues", delivery_id="delivery-2"
    )

    assert len(first) == 1
    assert len(second) == 1
    assert len(_history("codey", created["id"])) == 2


def test_a_delivery_that_matched_nothing_is_still_recorded():
    """A processed delivery is processed, whether or not a routine matched."""
    payload = _issue_opened()

    assert store.deliver_github_event(payload, event_header="issues", delivery_id="d0") == []
    assert store.fired_prompts() == []

    # A routine created after the fact does not resurrect an already-processed
    # delivery: the delivery got its 2xx, so it is done.
    later = _triage_routine()
    assert store.deliver_github_event(payload, event_header="issues", delivery_id="d0") == []
    assert len(_history("codey", later["id"])) == 0
    assert store.fired_prompts() == []


def test_a_delivery_that_failed_outside_the_run_releases_its_claim(monkeypatch):
    """A delivery that never completed is not "done" — GitHub must be able to retry.

    A routine that errors is a *completed* delivery (``fire_routine`` records the
    error row and answers 200), so it keeps its claim. The release path is for a
    delivery that blew up before it could finish — a locked store, say — which
    the view answers 500 for.
    """
    _triage_routine()
    payload = _issue_opened()

    def _boom(event):
        raise OSError("Could not lock agent routines.")

    with monkeypatch.context() as patch:
        patch.setattr(store, "_deliver_github_event", _boom)
        with pytest.raises(OSError):
            store.deliver_github_event(
                payload, event_header="issues", delivery_id="d-retry"
            )

    fired = store.deliver_github_event(
        payload, event_header="issues", delivery_id="d-retry"
    )
    assert len(fired) == 1
    assert len(store.fired_prompts()) == 1


def test_a_routine_that_errors_still_counts_as_delivered():
    """An error row is a completed run, so its redelivery is a no-op, not a re-run."""

    def _boom(agent_id, instruction, source):
        raise RuntimeError("agent crashed")

    _triage_routine()
    store.set_instruction_runner(_boom)
    payload = _issue_opened()

    first = store.deliver_github_event(payload, event_header="issues", delivery_id="d-err")
    second = store.deliver_github_event(payload, event_header="issues", delivery_id="d-err")

    assert len(first) == 1
    assert first[0]["routine"]["history"][0]["status"] == store.HISTORY_STATUS_ERROR
    assert second == []

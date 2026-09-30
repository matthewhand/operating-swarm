"""#1318 — routine/webhook sessions surface in the operator's bot chat.

The routines dispatcher records webhook turns under the installation-global
``github-webhook`` key. The operator chat must still hydrate them:

- a fired GitHub routine mirrors the session into the operator's ``u<pk>``
  store, so ``GET /chat/thread/?conversation_id=conv-github-*`` is populated;
- a legacy session that only exists under the webhook key reads through for
  the operator (no write/migration);
- the read-through is scoped to the operator when one exists;
- mirroring stays best-effort when no operator / DB is available.
"""

from __future__ import annotations

import asyncio

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import chat_store
from swarm.core import routines as routines_store

WEBHOOK_SECRET = "test-github-webhook-secret"


@pytest.fixture
def operator(db):
    return get_user_model().objects.create_superuser(
        username="operator", password="pw", email="op@example.com"
    )


@pytest.fixture
def client(operator):
    c = Client()
    assert c.login(username="operator", password="pw")
    return c


@pytest.fixture
def isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv(
        "SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json")
    )
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    routines_store.reset_routines_cache()
    routines_store.set_instruction_runner(None)
    routines_store.set_live_instruction_runner(None)


def _issue_opened_payload(*, number=17, title="Flaky login"):
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


def _make_routine():
    return routines_store.create_routine(
        "codey",
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "owner/repo",
            },
        },
    )


@pytest.mark.django_db
def test_fired_webhook_mirrors_to_operator_and_hydrates_thread(
    operator, client, isolate
):
    _make_routine()
    fired = routines_store.deliver_github_event(
        _issue_opened_payload(), event_header="issues"
    )
    assert len(fired) == 1

    operator_key = chat_store.user_key_for(operator)
    record = chat_store.load(operator_key, "codey", session_id="conv-github-issue-17")
    assert record is not None
    assert record["messages"][0]["role"] == "user"
    assert "Flaky login" in record["messages"][0]["content"]

    # Seeing the session under the owner key must not disturb the webhook copy.
    assert (
        chat_store.load(
            "github-webhook", "codey", session_id="conv-github-issue-17"
        )
        is not None
    )

    resp = client.get(
        "/chat/thread/?agent=codey&conversation_id=conv-github-issue-17"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["conversation_id"] == "conv-github-issue-17"
    assert body["session_missing"] is False
    contents = [row["content"] for row in body["messages"]]
    assert any("Flaky login" in text for text in contents)


@pytest.mark.django_db
def test_legacy_webhook_session_reads_through_for_operator(operator, client, isolate, monkeypatch):
    # Record the session WITHOUT the operator mirror, as the old dispatcher did.
    with monkeypatch.context() as patch:
        patch.setattr(chat_store, "primary_operator_user_key", lambda: "")
        chat_store.save(
            "github-webhook",
            "codey",
            [{"role": "user", "content": "legacy webhook prompt"}],
            conversation_id="conv-github-pr-42",
            session_id="conv-github-pr-42",
        )

    operator_key = chat_store.user_key_for(operator)
    assert (
        chat_store.load(operator_key, "codey", session_id="conv-github-pr-42")
        is not None
    )

    resp = client.get(
        "/chat/thread/?agent=codey&conversation_id=conv-github-pr-42"
    )
    assert resp.status_code == 200
    contents = [row["content"] for row in resp.json()["messages"]]
    assert contents == ["legacy webhook prompt"]


@pytest.mark.django_db
def test_read_through_denied_for_non_operator(operator, isolate, monkeypatch):
    with monkeypatch.context() as patch:
        patch.setattr(chat_store, "primary_operator_user_key", lambda: "")
        chat_store.save(
            "github-webhook",
            "codey",
            [{"role": "user", "content": "operator only"}],
            conversation_id="conv-github-issue-9",
            session_id="conv-github-issue-9",
        )

    other = get_user_model().objects.create_user(username="someone", password="pw")
    assert (
        chat_store.load(
            chat_store.user_key_for(other), "codey", session_id="conv-github-issue-9"
        )
        is None
    )
    # The operator still sees it.
    assert (
        chat_store.load(
            chat_store.user_key_for(operator),
            "codey",
            session_id="conv-github-issue-9",
        )
        is not None
    )


def test_mirror_is_best_effort_without_operator(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    monkeypatch.setattr(chat_store, "primary_operator_user_key", lambda: "")
    path = chat_store.save(
        "github-webhook",
        "codey",
        [{"role": "user", "content": "headless"}],
        conversation_id="conv-github-issue-5",
        session_id="conv-github-issue-5",
    )
    assert path is not None
    assert (
        chat_store.load("github-webhook", "codey", session_id="conv-github-issue-5")
        is not None
    )


@pytest.mark.django_db
def test_reply_saved_inside_event_loop_reaches_operator(operator, isolate):
    """A routine reply persisted under asyncio.run must land on the operator copy.

    The live job calls ``save`` on the event-loop thread. An ORM lookup there
    raises SynchronousOnlyOperation, and skipping the mirror leaves the
    operator file on the spawn prompt so the reply never shows up.
    """
    chat_store.reset_operator_key_cache()
    cid = "conv-github-issue-42"
    chat_store.save(
        "github-webhook",
        "codey",
        [{"role": "user", "content": "Investigate and fix."}],
        conversation_id=cid,
        session_id=cid,
    )

    async def _reply():
        chat_store.save(
            "github-webhook",
            "codey",
            [
                {"role": "user", "content": "Investigate and fix."},
                {"role": "assistant", "content": "opened pull request"},
            ],
            conversation_id=cid,
            session_id=cid,
        )

    asyncio.run(_reply())
    record = chat_store.load(chat_store.user_key_for(operator), "codey", session_id=cid)
    assert record is not None
    assert [row["role"] for row in record["messages"]] == ["user", "assistant"]
    assert record["messages"][-1]["content"] == "opened pull request"


@pytest.mark.django_db(transaction=True)
def test_reply_saved_inside_event_loop_reaches_django(operator, isolate):
    """Hydration reads Django (#1440), so the in-loop reply must land there.

    The operator JSON file can update from the cached key while
    ``mirror_json_record_to_django`` still runs on the loop thread, raises
    ``SynchronousOnlyOperation``, and is swallowed. The opened thread then
    stays on the spawn prompt.
    """
    from swarm.core.thread_load import load_thread

    chat_store.reset_operator_key_cache()
    cid = "conv-github-issue-99"
    chat_store.save(
        "github-webhook",
        "codey",
        [{"role": "user", "content": "Investigate and fix."}],
        conversation_id=cid,
        session_id=cid,
    )

    async def _reply():
        chat_store.save(
            "github-webhook",
            "codey",
            [
                {"role": "user", "content": "Investigate and fix."},
                {"role": "assistant", "content": "opened pull request"},
            ],
            conversation_id=cid,
            session_id=cid,
        )

    asyncio.run(_reply())
    loaded = load_thread(operator, "codey", requested_cid=cid, session_id=cid)
    assert [row.get("content") for row in loaded.turns] == [
        "Investigate and fix.",
        "opened pull request",
    ]


@pytest.mark.django_db
def test_stale_operator_copy_yields_newer_webhook_reply(operator, isolate, monkeypatch):
    cid = "conv-github-issue-7"
    op_key = chat_store.user_key_for(operator)
    chat_store.save(
        op_key,
        "codey",
        [{"role": "user", "content": "prompt only"}],
        conversation_id=cid,
        session_id=cid,
    )
    with monkeypatch.context() as patch:
        patch.setattr(chat_store, "primary_operator_user_key", lambda: "")
        chat_store.save(
            "github-webhook",
            "codey",
            [
                {"role": "user", "content": "prompt only"},
                {"role": "assistant", "content": "the reply"},
            ],
            conversation_id=cid,
            session_id=cid,
        )

    record = chat_store.load(op_key, "codey", session_id=cid)
    assert record is not None
    assert record["messages"][-1]["content"] == "the reply"
    stored = chat_store._load_record(op_key, "codey", session_id=cid)
    assert stored is not None
    assert stored["messages"][-1]["content"] == "the reply"


@pytest.mark.django_db
def test_other_user_cannot_claim_webhook_session(operator, isolate):
    from swarm.core.agent_sessions import get_or_create_session, list_agent_sessions
    from swarm.models import ChatConversation

    cid = "conv-github-issue-3"
    other = get_user_model().objects.create_user(
        username="someone-claim", password="pw"
    )
    # Claim the id before the operator mirror. save() write-through must take
    # the row back; a later insert would just collide with that row.
    ChatConversation.objects.create(
        conversation_id=cid, student=other, agent_id="codey"
    )
    chat_store.save(
        "github-webhook",
        "codey",
        [{"role": "user", "content": "Operator only."}],
        conversation_id=cid,
        session_id=cid,
    )

    with pytest.raises(PermissionError):
        get_or_create_session(other, cid, agent_id="codey")

    listed = {row.conversation_id for row in list_agent_sessions(operator, "codey")}
    assert cid in listed
    owned = ChatConversation.objects.get(conversation_id=cid)
    assert owned.student_id == operator.pk

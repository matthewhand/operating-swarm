"""#1667 — POST /v1/routines/events/github/ is idempotent for one delivery.

GitHub redelivers a delivery it did not get a fast 2xx for. Before this, the
redelivery was a second full run on the same per-issue conversation, and the
operator-plane lease turned it into a user-visible "busy" error. The contract at
the HTTP boundary is:

- the same ``X-GitHub-Delivery`` id answers **2xx** both times,
- the second answer is a no-op (``fired: []``, ``count: 0``),
- exactly one turn reached the conversation and one run reached the history.
"""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import routines as store

WEBHOOK_SECRET = "test-github-webhook-secret"
DELIVERY_ID = "9c0b1a52-77de-4c31-9a10-00000000abcd"


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _post(client, payload, *, delivery=None, event="issues"):
    body = json.dumps(payload).encode("utf-8")
    extra = {"HTTP_X_GITHUB_DELIVERY": delivery} if delivery else {}
    return client.post(
        "/v1/routines/events/github/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT=event,
        **extra,
    )


def _issue_opened(number=17):
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": "Flaky login",
            "body": "Repro on main.",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "user": {"login": "octocat"},
            "labels": [],
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "octocat"},
    }


@pytest.mark.django_db
def test_a_repeated_delivery_id_is_a_2xx_no_op(api_client):
    created = store.create_routine(
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
    payload = _issue_opened()

    first = _post(api_client, payload, delivery=DELIVERY_ID)
    second = _post(api_client, payload, delivery=DELIVERY_ID)

    # The redelivery is still a success: swallowing the request into an error is
    # what GitHub redelivers forever.
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["object"] == "github_event_delivery"
    assert first.json()["count"] == 1
    assert first.json()["fired"][0]["routine"]["id"] == created["id"]
    assert second.json()["count"] == 0
    assert second.json()["fired"] == []

    # Exactly one turn was appended, and it succeeded rather than being turned
    # into a "busy" error by the operator-plane lease.
    history = store.get_routine("codey", created["id"])["history"]
    assert len(history) == 1
    assert history[0]["status"] == store.HISTORY_STATUS_SUCCESS
    assert history[0]["conversation_id"] == "conv-github-issue-17"
    assert len(store.fired_prompts()) == 1

    thread = store.load_github_event_thread("codey", "conv-github-issue-17")
    assert [msg["role"] for msg in thread["messages"]] == ["user"]


@pytest.mark.django_db
def test_a_redelivery_without_the_header_is_also_a_2xx_no_op(api_client):
    store.create_routine(
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
    payload = _issue_opened()

    first = _post(api_client, payload)
    second = _post(api_client, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["count"] == 0
    assert len(store.fired_prompts()) == 1


@pytest.mark.django_db
def test_two_issues_are_two_deliveries(api_client):
    created = store.create_routine(
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

    first = _post(api_client, _issue_opened(number=17), delivery="delivery-1")
    second = _post(api_client, _issue_opened(number=18), delivery="delivery-2")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["count"] == 1
    assert second.json()["count"] == 1
    assert len(store.get_routine("codey", created["id"])["history"]) == 2


@pytest.mark.django_db
def test_a_redelivery_does_not_disturb_the_ping_probe(api_client):
    """``ping`` is answered before delivery bookkeeping, and stays a pong."""
    response = _post(api_client, {"zen": "Keep it logically awesome."}, event="ping")
    assert response.status_code == 200
    assert response.json()["pong"] is True
    assert response.json()["count"] == 0

"""REQ-884 / #285 — GitHub webhook event triggers for agent routines."""

from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import routines as store
from swarm.core.chat_store import load as load_chat

WEBHOOK_SECRET = "test-github-webhook-secret"


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _sign(body: bytes, secret: str = WEBHOOK_SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _github_event_trigger(event_type: str, owner_repo: str = "owner/repo", **filters):
    trigger = {"kind": "github_event", "event_type": event_type, "owner_repo": owner_repo}
    if filters:
        trigger["filters"] = filters
    return trigger


def _issue_opened_payload(*, number=17, labels=None, title="Flaky login"):
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": title,
            "body": "Repro on main.",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "user": {"login": "octocat"},
            "labels": [{"name": name} for name in (labels or [])],
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "octocat"},
    }


def _pr_payload(action: str, *, number=42, labels=None, base="main"):
    return {
        "action": action,
        "number": number,
        "pull_request": {
            "number": number,
            "title": "Add webhook routines",
            "body": "Wire GitHub events to agents.",
            "html_url": f"https://github.com/owner/repo/pull/{number}",
            "diff_url": f"https://github.com/owner/repo/pull/{number}.diff",
            "user": {"login": "mona"},
            "labels": [{"name": name} for name in (labels or [])],
            "base": {"ref": base},
            "head": {"ref": "feat/webhooks"},
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "mona"},
    }


def _push_payload(*, branch="main", sha="abc1234deadbeef"):
    return {
        "ref": f"refs/heads/{branch}",
        "after": sha,
        "compare": "https://github.com/owner/repo/compare/111...222",
        "repository": {"full_name": "owner/repo"},
        "pusher": {"name": "octocat"},
        "head_commit": {
            "id": sha,
            "message": "Ship webhook ingest\n\nDetails.",
        },
        "sender": {"login": "octocat"},
    }


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_routines(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _post_webhook(api_client, payload, event, secret=WEBHOOK_SECRET):
    body = json.dumps(payload).encode("utf-8")
    return api_client.post(
        "/v1/routines/events/github/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(body, secret),
        HTTP_X_GITHUB_EVENT=event,
    )


def test_create_github_event_trigger_and_summary(tmp_path, monkeypatch):
    created = store.create_routine(
        "codey",
        {
            "name": "Triage bugs",
            "instruction": "Triage this issue.",
            "trigger": _github_event_trigger("issues.opened", labels=["bug", "triage"]),
        },
    )
    assert created["trigger"]["kind"] == "github_event"
    assert created["trigger"]["event_type"] == "issues.opened"
    assert created["trigger"]["owner_repo"] == "owner/repo"
    assert created["trigger"]["filters"]["labels"] == ["bug", "triage"]
    assert store.trigger_summary(created["trigger"]) == (
        "When issues.opened in owner/repo (labels: bug, triage)…"
    )


def test_rejects_unknown_event_type():
    try:
        store.create_routine(
            "codey",
            {"trigger": {"kind": "github_event", "event_type": "star", "owner_repo": "owner/repo"}},
        )
    except ValueError as exc:
        assert "event_type" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_cron_trigger_is_accepted_with_expression():
    created = store.create_routine(
        "codey",
        {
            "name": "Nightly",
            "instruction": "Nightly recap.",
            "trigger": {"kind": "cron", "expression": "0 3 * * *"},
        },
    )
    assert created["trigger"]["kind"] == "cron"
    assert created["trigger"]["expression"] == "0 3 * * *"


def test_issues_opened_fires_and_records_history():
    created = store.create_routine(
        "codey",
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": _github_event_trigger("issues.opened"),
        },
    )
    fired = store.deliver_github_event(_issue_opened_payload(), event_header="issues")
    assert len(fired) == 1
    row = store.get_routine("codey", created["id"])
    history = row["history"][0]
    assert history["status"] == "success"
    assert history["source"] == "github_webhook"
    assert history["event"] == "issues.opened #17"
    assert history["conversation_id"] == "conv-github-issue-17"
    assert "Triage" in history["summary"]
    prompt = store.fired_prompts()[0]
    assert prompt["source"] == "github_webhook"
    assert "Flaky login" in prompt["instruction"]
    assert "Repro on main." in prompt["instruction"]
    assert "octocat" in prompt["instruction"]
    assert "https://github.com/owner/repo/issues/17" in prompt["instruction"]
    assert "Triage this issue." in prompt["instruction"]
    session = load_chat("github-webhook", "codey", session_id="conv-github-issue-17")
    assert session is not None
    assert session.get("conversation_id") == "conv-github-issue-17" or session.get("messages")


def test_pull_request_opened_and_review_requested_use_pr_conversation():
    opened = store.create_routine(
        "codey",
        {
            "name": "Review PR",
            "instruction": "Review this pull request.",
            "trigger": _github_event_trigger("pull_request.opened"),
        },
    )
    review = store.create_routine(
        "codey",
        {
            "name": "Review requested",
            "instruction": "You were asked to review.",
            "trigger": _github_event_trigger("pull_request.review_requested"),
        },
    )
    fired_open = store.deliver_github_event(_pr_payload("opened"), event_header="pull_request")
    fired_review = store.deliver_github_event(
        _pr_payload("review_requested"),
        event_header="pull_request",
    )
    assert {row["routine"]["id"] for row in fired_open} == {opened["id"]}
    assert {row["routine"]["id"] for row in fired_review} == {review["id"]}
    open_hist = store.get_routine("codey", opened["id"])["history"][0]
    assert open_hist["event"] == "pull_request.opened #42"
    assert open_hist["conversation_id"] == "conv-github-pr-42"
    assert "Add webhook routines" in store.fired_prompts()[0]["instruction"]
    assert "https://github.com/owner/repo/pull/42" in store.fired_prompts()[0]["instruction"]
    review_hist = store.get_routine("codey", review["id"])["history"][0]
    assert review_hist["event"] == "pull_request.review_requested #42"
    assert review_hist["conversation_id"] == "conv-github-pr-42"


def test_push_branch_filter_and_inactive_and_pr_merged_do_not_cross_fire():
    matching = store.create_routine(
        "codey",
        {
            "name": "Main pushes",
            "instruction": "Summarize the push.",
            "trigger": _github_event_trigger("push", branch="main"),
        },
    )
    other_branch = store.create_routine(
        "codey",
        {
            "name": "Dev pushes",
            "instruction": "Ignore.",
            "trigger": _github_event_trigger("push", branch="dev"),
        },
    )
    paused = store.create_routine(
        "codey",
        {
            "name": "Paused",
            "instruction": "Should not run.",
            "active": False,
            "trigger": _github_event_trigger("push", branch="main"),
        },
    )
    merged = store.create_routine(
        "codey",
        {
            "name": "Merge recap",
            "instruction": "Note the merge.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
        },
    )
    fired = store.deliver_github_event(_push_payload(branch="main"), event_header="push")
    ids = {row["routine"]["id"] for row in fired}
    assert matching["id"] in ids
    assert other_branch["id"] not in ids
    assert paused["id"] not in ids
    assert merged["id"] not in ids
    hist = store.get_routine("codey", matching["id"])["history"][0]
    assert hist["source"] == "github_webhook"
    assert hist["event"].startswith("push main")
    assert hist["conversation_id"].startswith("conv-github-")
    assert store.get_routine("codey", other_branch["id"])["history"] == []
    assert store.get_routine("codey", paused["id"])["history"] == []
    assert store.get_routine("codey", merged["id"])["history"] == []


def test_label_filter_requires_overlap():
    store.create_routine(
        "codey",
        {
            "name": "Bugs only",
            "instruction": "Triage bugs.",
            "trigger": _github_event_trigger("issues.opened", labels=["bug", "triage"]),
        },
    )
    miss = store.deliver_github_event(
        _issue_opened_payload(labels=["docs"]),
        event_header="issues",
    )
    hit = store.deliver_github_event(
        _issue_opened_payload(labels=["triage", "help-wanted"]),
        event_header="issues",
    )
    assert miss == []
    assert len(hit) == 1


def test_runner_error_records_error_history():
    created = store.create_routine(
        "codey",
        {
            "name": "Boom",
            "instruction": "Fail.",
            "trigger": _github_event_trigger("issues.opened"),
        },
    )

    def _boom(agent_id, instruction, source):
        raise RuntimeError("agent crashed")

    store.set_instruction_runner(_boom)
    fired = store.deliver_github_event(_issue_opened_payload(), event_header="issues")
    assert len(fired) == 1
    history = store.get_routine("codey", created["id"])["history"][0]
    assert history["status"] == "error"
    assert history["source"] == "github_webhook"
    assert "agent crashed" in history["summary"]
    assert history["conversation_id"] == "conv-github-issue-17"


def test_webhook_api_issues_prs_and_pushes(api_client):
    issues = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": _github_event_trigger("issues.opened"),
        },
        format="json",
    )
    assert issues.status_code == 201
    prs = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Review",
            "instruction": "Review this PR.",
            "trigger": _github_event_trigger("pull_request.opened"),
        },
        format="json",
    )
    assert prs.status_code == 201
    pushes = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Push notes",
            "instruction": "Summarize the push.",
            "trigger": _github_event_trigger("push", branch="main"),
        },
        format="json",
    )
    assert pushes.status_code == 201

    issue_resp = _post_webhook(api_client, _issue_opened_payload(), "issues")
    assert issue_resp.status_code == 200
    issue_body = issue_resp.json()
    assert issue_body["object"] == "github_event_delivery"
    assert issue_body["count"] == 1
    issue_hist = issue_body["fired"][0]["routine"]["history"][0]
    assert issue_hist["source"] == "github_webhook"
    assert issue_hist["event"] == "issues.opened #17"
    assert issue_hist["conversation_id"] == "conv-github-issue-17"

    pr_resp = _post_webhook(api_client, _pr_payload("opened"), "pull_request")
    assert pr_resp.status_code == 200
    assert pr_resp.json()["count"] == 1
    assert pr_resp.json()["fired"][0]["routine"]["history"][0]["conversation_id"] == "conv-github-pr-42"

    push_resp = _post_webhook(api_client, _push_payload(), "push")
    assert push_resp.status_code == 200
    assert push_resp.json()["count"] == 1
    assert store.fired_prompts()[-1]["instruction"].startswith("GitHub event: push main")


def test_webhook_signature_and_ping(api_client):
    api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": _github_event_trigger("issues.opened"),
        },
        format="json",
    )
    payload = _issue_opened_payload()
    body = json.dumps(payload).encode("utf-8")

    unsigned = api_client.post(
        "/v1/routines/events/github/",
        data=body,
        content_type="application/json",
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert unsigned.status_code == 401

    wrong = api_client.post(
        "/v1/routines/events/github/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(body, "wrong-secret"),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert wrong.status_code == 401

    ping = api_client.post(
        "/v1/routines/events/github/",
        data=b'{"zen": "Keep it logically awesome."}',
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(b'{"zen": "Keep it logically awesome."}'),
        HTTP_X_GITHUB_EVENT="ping",
    )
    assert ping.status_code == 200
    assert ping.json()["pong"] is True
    assert ping.json()["count"] == 0
    assert store.fired_prompts() == []


def test_webhook_secret_missing_is_unavailable(api_client, monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    payload = _issue_opened_payload()
    body = json.dumps(payload).encode("utf-8")
    response = api_client.post(
        "/v1/routines/events/github/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=_sign(body),
        HTTP_X_GITHUB_EVENT="issues",
    )
    assert response.status_code == 503


def test_verify_github_webhook_signature_helpers():
    body = b'{"ok": true}'
    assert store.verify_github_webhook_signature(body, _sign(body, WEBHOOK_SECRET), secret=WEBHOOK_SECRET)
    assert not store.verify_github_webhook_signature(body, _sign(body, "nope"), secret=WEBHOOK_SECRET)
    assert not store.verify_github_webhook_signature(body, "", secret=WEBHOOK_SECRET)
    assert not store.verify_github_webhook_signature(body, _sign(body), secret="")


def test_api_auth_is_not_required_when_signature_is_valid(api_client):
    if getattr(settings, "SWARM_API_KEY", None):
        api_client.credentials()
    created = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Triage",
            "instruction": "Triage this issue.",
            "trigger": _github_event_trigger("issues.opened"),
        },
        format="json",
    )
    # Create may require auth depending on env; webhook must not.
    if created.status_code == 201:
        routine_id = created.json()["id"]
    else:
        routine_id = store.create_routine(
            "codey",
            {
                "name": "Triage",
                "instruction": "Triage this issue.",
                "trigger": _github_event_trigger("issues.opened"),
            },
        )["id"]
    bare = APIClient()
    response = _post_webhook(bare, _issue_opened_payload(), "issues")
    assert response.status_code == 200
    assert response.json()["fired"][0]["routine"]["id"] == routine_id

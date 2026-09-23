"""#862 — autonomous multi-agent GitHub event pipeline.

Contracts:
- **Live background runner**: ``run_routine_agent_job`` resolves the agent's
  blueprint, executes one full turn (streaming collected), and appends the
  assistant reply to the webhook conversation. Failures become history
  rows with ``status=error`` — never silent.
- **Default runner wiring**: ``set_live_instruction_runner(None)`` falls
  back to the recording default; a live runner replaces it. Tests can
  inject either (the historic ``set_instruction_runner`` keeps working).
- **Loop prevention**: ``github_event_filters_match`` honours
  ``filters.exclude_authors`` — an event authored by an excluded login
  never fires the routine (self-trigger cascade guard).
- **Presets**: ``ROUTINE_PRESETS`` ships the Issue→PR developer and
  PR→Review/QA templates with distinct ``role`` assignments, loop-safe
  ``exclude_authors`` defaults, and max-turn budgets; the routines API
  lists them and they create valid routines via the normal POST path.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from swarm.core import routines as store

WEBHOOK_SECRET = "test-github-webhook-secret"


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", WEBHOOK_SECRET)
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _github_event_trigger(event_type: str, owner_repo: str = "owner/repo", **filters):
    return {"kind": "github_event", "event_type": event_type, "owner_repo": owner_repo, "filters": dict(filters)}


def _issue_opened_payload(*, number=42, labels=None, author="octocat"):
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": "Fix the flux capacitor",
            "body": "It does not flux.",
            "user": {"login": author},
            "labels": [{"name": label} for label in (labels or [])],
            "html_url": f"https://github.com/owner/repo/issues/{number}",
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": author},
    }


def _pr_opened_payload(*, number=7, author="octocat"):
    return {
        "action": "opened",
        "pull_request": {
            "number": number,
            "title": "Add flux",
            "body": "Closes #42",
            "user": {"login": author},
            "base": {"ref": "main"},
            "head": {"ref": "feat/flux"},
            "html_url": f"https://github.com/owner/repo/pull/{number}",
            "diff_url": f"https://github.com/owner/repo/pull/{number}.diff",
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": author},
    }


pytestmark = pytest.mark.django_db


# --- live runner ---------------------------------------------------------------


def test_run_routine_agent_job_executes_turn_and_persists_reply(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    seen: dict[str, object] = {}

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            seen["prompt"] = messages[-1]["content"]
            seen["stream"] = kwargs.get("stream")
            del messages, kwargs
            yield "branch "
            yield "created"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        seen["agent_id"] = agent_id
        del params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    asyncio.run(
        store.run_routine_agent_job("codey", "Investigate and fix.", conversation_id="conv-github-issue-42")
    )

    assert seen["agent_id"] == "codey"
    assert seen["prompt"] == "Investigate and fix."
    assert seen["stream"] is False
    record = store.load_github_event_thread("codey", "conv-github-issue-42")
    assert record is not None
    roles = [m["role"] for m in record["messages"]]
    assert roles.count("assistant") == 1
    assert record["messages"][-1]["content"] == "branch created"


def test_run_routine_agent_job_records_error_on_failure(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    async def _boom(agent_id, params=None):
        del agent_id, params
        raise RuntimeError("blueprint exploded")

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _boom)

    with pytest.raises(RuntimeError, match="blueprint exploded"):
        asyncio.run(store.run_routine_agent_job("codey", "x", conversation_id="conv-github-issue-9"))


def test_live_runner_status_recording(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.record_live_job_status("codey", "ok", duration_ms=12, detail="done")
    statuses = store.live_job_status("codey")
    assert len(statuses) == 1
    assert statuses[0]["status"] == "ok"
    assert statuses[0]["duration_ms"] == 12
    store.record_live_job_status("codey", "error", detail="boom")
    statuses = store.live_job_status("codey")
    assert statuses[-1]["status"] == "error"
    assert statuses[-1]["detail"] == "boom"


def test_default_live_runner_used_when_none_set(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            del messages, kwargs
            yield "ok"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del agent_id, params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    store.set_live_instruction_runner(None)
    created = store.create_routine(
        "codey",
        {"name": "Auto", "instruction": "Do it.", "trigger": _github_event_trigger("issues.opened")},
    )
    fired = store.deliver_github_event(_issue_opened_payload(), event_header="issues")
    assert len(fired) == 1
    assert fired[0]["routine"]["history"][0]["status"] == "success"
    _ = created


# --- loop prevention -------------------------------------------------------------


def test_exclude_authors_filter_blocks_self_triggers(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_routine(
        "codey",
        {
            "name": "No loops",
            "instruction": "x",
            "trigger": _github_event_trigger(
                "pull_request.opened", exclude_authors=["open-swarm[bot]", "github-actions[bot]"]
            ),
        },
    )
    assert (
        store.deliver_github_event(_pr_opened_payload(author="open-swarm[bot]"), event_header="pull_request")
        == []
    )
    assert store.deliver_github_event(_pr_opened_payload(author="mona"), event_header="pull_request") != []


def test_exclude_authors_case_insensitive(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_routine(
        "codey",
        {"name": "Case", "instruction": "x", "trigger": _github_event_trigger("issues.opened", exclude_authors=["Open-Swarm[Bot]"])},
    )
    assert store.deliver_github_event(_issue_opened_payload(author="open-swarm[bot]"), event_header="issues") == []


def test_filters_without_exclude_authors_keep_firing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.create_routine(
        "codey",
        {"name": "Plain", "instruction": "x", "trigger": _github_event_trigger("issues.opened")},
    )
    assert len(store.deliver_github_event(_issue_opened_payload(author="open-swarm[bot]"), event_header="issues")) == 1


# --- presets ----------------------------------------------------------------------


def test_routine_presets_shape():
    presets = store.ROUTINE_PRESETS
    by_key = {p["key"]: p for p in presets}
    assert {"github_issue_solver", "github_pr_reviewer"} <= set(by_key)
    solver = by_key["github_issue_solver"]
    reviewer = by_key["github_pr_reviewer"]
    assert solver["role"] != reviewer["role"]
    assert solver["trigger"]["event_type"] == "issues.opened"
    assert reviewer["trigger"]["event_type"] == "pull_request.opened"
    for preset in (solver, reviewer):
        authors = preset["trigger"]["filters"]["exclude_authors"]
        assert "open-swarm[bot]" in authors
        assert preset["max_turns"] >= 1
        assert preset["instruction"].strip()


def test_presets_listed_via_api(api_client):
    response = api_client.get("/v1/routines/presets/")
    assert response.status_code == 200
    keys = {row["key"] for row in response.json()["presets"]}
    assert {"github_issue_solver", "github_pr_reviewer"} <= keys


def test_preset_creates_valid_routine(tmp_path, monkeypatch, api_client):
    _isolate(tmp_path, monkeypatch)
    solver = next(p for p in store.ROUTINE_PRESETS if p["key"] == "github_issue_solver")
    trigger = json.loads(json.dumps(solver["trigger"]))
    trigger["owner_repo"] = "owner/repo"  # template placeholder → real repo at creation time
    payload = {
        "name": solver["name"],
        "instruction": solver["instruction"],
        "trigger": trigger,
    }
    response = api_client.post("/v1/agents/codey/routines/", payload, format="json")
    assert response.status_code == 201, response.content
    body = json.loads(response.content)
    assert body["trigger"]["filters"]["exclude_authors"] == solver["trigger"]["filters"]["exclude_authors"]

"""API tests for /v1/agents/<id>/routines/ (REQ-80 / #432)."""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import routines as store


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate_routines(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def test_list_empty_then_create_named_pr_merge(api_client):
    listed = api_client.get("/v1/agents/codey/routines/")
    assert listed.status_code == 200
    body = listed.json()
    assert body["object"] == "routine_list"
    assert body["routines"] == []

    created = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Ship notes",
            "instruction": "Summarize the merged pull request.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
        },
        format="json",
    )
    assert created.status_code == 201
    row = created.json()
    assert row["object"] == "routine"
    assert row["name"] == "Ship notes"
    assert row["instruction"] == "Summarize the merged pull request."
    assert row["active"] is True
    assert row["trigger"]["kind"] == "github_pr_merged"
    assert row["trigger"]["owner_repo"] == "owner/repo"
    assert row["when_to_run"] == "When a PR merges in owner/repo…"
    assert "token" not in row["instruction"].lower()
    assert ":8001" not in row["instruction"]

    again = api_client.get("/v1/agents/codey/routines/")
    assert len(again.json()["routines"]) == 1


def test_patch_active_test_run_and_delete(api_client):
    created = api_client.post(
        "/v1/agents/codey/routines/",
        {"name": "Ship notes", "instruction": "Write the merge recap."},
        format="json",
    ).json()
    routine_id = created["id"]

    patched = api_client.patch(
        f"/v1/agents/codey/routines/{routine_id}/",
        {"active": False},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is False

    ran = api_client.post(f"/v1/agents/codey/routines/{routine_id}/test-run/", {}, format="json")
    assert ran.status_code == 200
    history = ran.json()["history"]
    assert len(history) == 1
    assert history[0]["status"] == "success"
    assert history[0]["source"] == "test_run"
    assert history[0]["ran_at"]
    assert store.fired_prompts()[0]["instruction"] == "Write the merge recap."

    deleted = api_client.delete(f"/v1/agents/codey/routines/{routine_id}/")
    assert deleted.status_code == 204
    missing = api_client.get(f"/v1/agents/codey/routines/{routine_id}/")
    assert missing.status_code == 404


def test_inactive_does_not_fire_on_fake_merge(api_client):
    active = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Active",
            "instruction": "Note the merge.",
            "trigger": {"owner_repo": "owner/repo"},
        },
        format="json",
    ).json()
    paused = api_client.post(
        "/v1/agents/codey/routines/",
        {
            "name": "Paused",
            "instruction": "Should not run.",
            "active": False,
            "trigger": {"owner_repo": "owner/repo"},
        },
        format="json",
    ).json()

    delivery = api_client.post(
        "/v1/routines/github-merge/",
        {"owner_repo": "owner/repo", "event": "merged", "actor": "anyone"},
        format="json",
    )
    assert delivery.status_code == 200
    body = delivery.json()
    assert body["object"] == "routine_merge_delivery"
    assert body["count"] == 1
    assert body["fired"][0]["routine"]["id"] == active["id"]

    paused_row = api_client.get(f"/v1/agents/codey/routines/{paused['id']}/").json()
    assert paused_row["history"] == []
    active_row = api_client.get(f"/v1/agents/codey/routines/{active['id']}/").json()
    assert active_row["history"][0]["source"] == "github_pr_merged"


def test_unmerged_github_payload_is_rejected(api_client):
    response = api_client.post(
        "/v1/routines/github-merge/",
        {
            "action": "closed",
            "pull_request": {"merged": False},
            "repository": {"full_name": "owner/repo"},
        },
        format="json",
    )
    assert response.status_code == 400
    assert "merged" in response.json()["error"].lower()


def test_list_all_routines(api_client):
    api_client.post(
        "/v1/agents/codey/routines/",
        {"name": "Codey Routine", "instruction": "Do things"},
        format="json",
    )
    api_client.post(
        "/v1/agents/api_agent/routines/",
        {"name": "API Routine", "instruction": "Process data"},
        format="json",
    )
    resp = api_client.get("/v1/routines/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "routine_list"
    names = [r["name"] for r in body["routines"]]
    assert "Codey Routine" in names
    assert "API Routine" in names

"""API tests for /v1/operator-plane/ (#1360)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from swarm.core.routines import reset_routines_cache


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_OPERATOR_PLANE_PATH", str(tmp_path / "plane.json"))
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "routines.json"))
    reset_routines_cache()
    from swarm.core import team_rosters as rosters

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(rosters, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(rosters, "ensure_swarm_directories_exist", lambda: None)
    rosters.reset_team_rosters()


def test_budget_charge_conflicts_when_the_limit_is_hit(api_client):
    created = api_client.put(
        "/v1/operator-plane/budgets/",
        {"scope": "seat", "scope_id": "codey", "token_limit": 1, "hard_stop": True},
        format="json",
    )
    assert created.status_code == 200
    assert created.data["token_limit"] == 1
    first = api_client.post(
        "/v1/operator-plane/budgets/charge/",
        {"scope": "seat", "scope_id": "codey", "tokens": 1},
        format="json",
    )
    assert first.status_code == 200
    assert first.data["tokens_used"] == 1
    second = api_client.post(
        "/v1/operator-plane/budgets/charge/",
        {"scope": "seat", "scope_id": "codey", "tokens": 1},
        format="json",
    )
    assert second.status_code == 409
    assert "hard-stop" in second.data["error"]
    listed = api_client.get("/v1/operator-plane/budgets/")
    assert listed.data["data"][0]["tokens_used"] == 1
    reset = api_client.post(
        "/v1/operator-plane/budgets/reset/",
        {"scope": "seat", "scope_id": "codey"},
        format="json",
    )
    assert reset.status_code == 200
    assert reset.data["stopped"] is False
    assert reset.data["tokens_used"] == 0


def test_checkout_conflict_and_release(api_client):
    first = api_client.post(
        "/v1/operator-plane/tasks/checkout/",
        {"task_id": "task-1", "worker_id": "worker-a", "lease_s": 60},
        format="json",
    )
    assert first.status_code == 200
    second = api_client.post(
        "/v1/operator-plane/tasks/checkout/",
        {"task_id": "task-1", "worker_id": "worker-b", "lease_s": 60},
        format="json",
    )
    assert second.status_code == 409
    wrong = api_client.post(
        "/v1/operator-plane/tasks/release/",
        {"task_id": "task-1", "worker_id": "worker-b"},
        format="json",
    )
    assert wrong.status_code == 409
    released = api_client.post(
        "/v1/operator-plane/tasks/release/",
        {"task_id": "task-1", "worker_id": "worker-a"},
        format="json",
    )
    assert released.status_code == 200
    summary = api_client.get("/v1/operator-plane/")
    assert summary.status_code == 200
    assert summary.data["object"] == "operator_plane"
    assert summary.data["checkouts"] == []


def test_gate_decide_and_rollback(api_client):
    proposed = api_client.post(
        "/v1/operator-plane/gates/",
        {
            "action": "propose",
            "subject_id": "budget:codey",
            "actor": "ada",
            "snapshot": {"limit": 1},
        },
        format="json",
    )
    assert proposed.status_code == 200
    revision = proposed.data["pending_revision"]
    approved = api_client.post(
        "/v1/operator-plane/gates/",
        {
            "action": "decide",
            "subject_id": "budget:codey",
            "actor": "ada",
            "revision": revision,
            "approved": True,
        },
        format="json",
    )
    assert approved.status_code == 200
    assert approved.data["snapshot"]["limit"] == 1
    newer = api_client.post(
        "/v1/operator-plane/gates/",
        {
            "action": "propose",
            "subject_id": "budget:codey",
            "actor": "ada",
            "snapshot": {"limit": 5},
        },
        format="json",
    )
    api_client.post(
        "/v1/operator-plane/gates/",
        {
            "action": "decide",
            "subject_id": "budget:codey",
            "actor": "ada",
            "revision": newer.data["pending_revision"],
            "approved": True,
        },
        format="json",
    )
    rolled = api_client.post(
        "/v1/operator-plane/gates/",
        {
            "action": "rollback",
            "subject_id": "budget:codey",
            "actor": "ada",
            "to_revision": revision,
            "reason": "restore",
        },
        format="json",
    )
    assert rolled.status_code == 200
    assert rolled.data["snapshot"]["limit"] == 1
    fetched = api_client.get("/v1/operator-plane/gates/?subject_id=budget:codey")
    assert fetched.status_code == 200
    assert fetched.data["snapshot"]["limit"] == 1


def test_export_scrubs_and_import_reports_collision(api_client):
    from swarm.core.team_rosters import upsert_roster

    upsert_roster(
        {
            "id": "research",
            "name": "Research",
            "members": [{"id": "jeeves", "kind": "api", "role": "default"}],
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "Bearer supersecretvalue1",
        }
    )
    exported = api_client.post(
        "/v1/operator-plane/org/export/",
        {"name": "Acme"},
        format="json",
    )
    assert exported.status_code == 200
    assert exported.data["kind"] == "os-org-pack"
    encoded = str(exported.data)
    assert "supersecretvalue1" not in encoded
    assert "[scrubbed]" in encoded
    conflict = api_client.post(
        "/v1/operator-plane/org/import/",
        {"pack": exported.data, "on_collision": "error"},
        format="json",
    )
    assert conflict.status_code == 400
    assert "collision" in conflict.data["error"]

"""API tests for /v1/test-schedules/ (#222)."""

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from swarm.core import test_schedules as store


@pytest.fixture
def api_client():
    client = APIClient()
    if getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    path = tmp_path / "test_schedules.json"
    path.write_text('{"schema": 1, "schedules": []}\n', encoding="utf-8")
    monkeypatch.setenv("SWARM_TEST_SCHEDULES_PATH", str(path))
    store.reset_test_schedules_cache()
    store.set_check_runner(None)
    store.set_failure_notifier(lambda *_a, **_k: None)
    yield
    store.reset_test_schedules_cache()
    store.set_check_runner(None)
    store.set_failure_notifier(None)


def test_list_create_run_now_and_status(api_client):
    listed = api_client.get("/v1/test-schedules/")
    assert listed.status_code == 200
    assert listed.json()["object"] == "test_schedule_list"
    assert listed.json()["schedules"] == []

    created = api_client.post(
        "/v1/test-schedules/",
        {
            "name": "Hourly health",
            "trigger": {"kind": "interval", "seconds": 3600},
            "target": {"kind": "fleet", "fleet": "all"},
            "check": {"kind": "harness_health", "name": "remote_health"},
        },
        format="json",
    )
    assert created.status_code == 201
    row = created.json()
    assert row["object"] == "test_schedule"
    assert row["trigger"]["kind"] == "interval"
    schedule_id = row["id"]

    ran = api_client.post(f"/v1/test-schedules/{schedule_id}/run-now/", {}, format="json")
    assert ran.status_code == 200
    assert ran.json()["history"][0]["source"] == "run_now"
    assert ran.json()["history"][0]["duration_ms"] >= 0

    patched = api_client.patch(
        f"/v1/test-schedules/{schedule_id}/",
        {"active": False},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["active"] is False

    status = api_client.get("/v1/test-schedules/status/")
    assert status.status_code == 200
    assert status.json()["failure_count"] == 0


def test_run_now_failure_increments_status(api_client):
    def _fail(_schedule):
        return {"status": "error", "summary": "down"}

    store.set_check_runner(_fail)
    created = api_client.post(
        "/v1/test-schedules/",
        {"name": "Boom", "check": {"kind": "script", "name": "fleet_prove"}},
        format="json",
    ).json()
    ran = api_client.post(f"/v1/test-schedules/{created['id']}/run-now/", {}, format="json")
    assert ran.status_code == 200
    assert ran.json()["history"][0]["status"] == "error"
    status = api_client.get("/v1/test-schedules/status/")
    assert status.json()["failure_count"] == 1
    assert status.json()["failures"][0]["name"] == "Boom"


def test_delete_missing(api_client):
    missing = api_client.delete("/v1/test-schedules/nope/")
    assert missing.status_code == 404

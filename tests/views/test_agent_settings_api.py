"""API tests for /v1/agents/<id>/settings/ (REQ-65)."""

import pytest
from rest_framework.test import APIClient

from swarm.core import agent_settings as store
from swarm.core import session_policy as policy


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    policy.clear_active_sessions()
    yield
    store.reset_agent_settings_cache()
    policy.clear_active_sessions()


def test_get_defaults_off(api_client):
    response = api_client.get("/v1/agents/worker/settings/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "agent_settings"
    assert body["agent_id"] == "worker"
    assert body["new_chat_per_task"] is False
    assert body.get("folder") is None
    assert body["speech_mode"] == "inherit"
    assert body["auto_speak_replies"] is False


def test_patch_folder_roundtrip(api_client):
    response = api_client.patch(
        "/v1/agents/cli_agent/settings/",
        {"folder": " /tmp/ws "},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["folder"] == "/tmp/ws"
    again = api_client.get("/v1/agents/cli_agent/settings/")
    assert again.json()["folder"] == "/tmp/ws"


def test_patch_toggle_on(api_client):
    response = api_client.patch(
        "/v1/agents/worker/settings/",
        {"new_chat_per_task": True},
        format="json",
    )
    assert response.status_code == 200
    assert response.json()["new_chat_per_task"] is True
    again = api_client.get("/v1/agents/worker/settings/")
    assert again.json()["new_chat_per_task"] is True


@pytest.mark.django_db
def test_allocate_session_reuses_when_off(api_client):
    first = api_client.post("/v1/agents/worker/sessions/", {}, format="json")
    second = api_client.post("/v1/agents/worker/sessions/", {}, format="json")
    assert first.status_code == 200
    assert first.json()["new_chat_per_task"] is False
    assert first.json()["conversation_id"] == second.json()["conversation_id"]


def test_list_and_create_django_sessions(api_client, django_user_model, db, tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    user = django_user_model.objects.create_user(username="sess-api", password="pw")
    api_client.force_authenticate(user=user)
    created = [
        api_client.post("/v1/agents/codey/sessions/", {"new": True}, format="json")
        for _ in range(3)
    ]
    assert all(row.status_code == 200 for row in created)
    ids = {row.json()["conversation_id"] for row in created}
    assert len(ids) == 3
    listed = api_client.get("/v1/agents/codey/sessions/")
    assert listed.status_code == 200
    body = listed.json()
    assert body["object"] == "agent_session_list"
    listed_ids = {row["id"] for row in body["sessions"]}
    assert ids <= listed_ids
    assert all(row["agent_id"] == "codey" for row in body["sessions"])
    empty = created[0].json()
    assert empty["empty"] is True
    assert empty["title"] == "New session"


@pytest.mark.django_db
def test_allocate_session_mints_when_on(api_client):
    api_client.patch(
        "/v1/agents/worker/settings/",
        {"new_chat_per_task": True},
        format="json",
    )
    first = api_client.post(
        "/v1/agents/worker/sessions/",
        {"task_id": "alpha"},
        format="json",
    )
    second = api_client.post(
        "/v1/agents/worker/sessions/",
        {"task_id": "beta"},
        format="json",
    )
    assert first.json()["empty"] is True
    assert first.json()["conversation_id"] != second.json()["conversation_id"]

"""API tests for /v1/agents/<id>/settings/ (REQ-65)."""

import pytest
from rest_framework.test import APIClient

from swarm.core import agent_settings as store
from swarm.core import session_policy as policy


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


def test_command_allowlist_default_and_roundtrip(api_client):
    default = api_client.get("/v1/agents/worker/settings/")
    assert default.status_code == 200
    assert default.json()["command_allowlist"] == {"allow": [], "deny": [], "ask": []}

    policy = {"allow": ["git status", "pytest"], "deny": ["rm", "curl"], "ask": ["git push"]}
    saved = api_client.patch(
        "/v1/agents/worker/settings/",
        {"command_allowlist": policy},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.json()["command_allowlist"] == policy

    again = api_client.get("/v1/agents/worker/settings/")
    assert again.json()["command_allowlist"] == policy
    # Per-bot: another agent is unaffected.
    other = api_client.get("/v1/agents/other/settings/")
    assert other.json()["command_allowlist"] == {"allow": [], "deny": [], "ask": []}


def test_mcp_tool_grants_default_and_roundtrip(api_client):
    default = api_client.get("/v1/agents/worker/settings/")
    assert default.status_code == 200
    assert default.json()["mcp_tool_grants"] == []
    assert default.json()["mcp_tool_grants_set"] is False

    saved = api_client.patch(
        "/v1/agents/worker/settings/",
        {"mcp_tool_grants": ["web_search", "web_fetch", "web_search"]},
        format="json",
    )
    assert saved.status_code == 200
    assert saved.json()["mcp_tool_grants"] == ["web_search", "web_fetch"]
    assert saved.json()["mcp_tool_grants_set"] is True

    again = api_client.get("/v1/agents/worker/settings/")
    assert again.json()["mcp_tool_grants"] == ["web_search", "web_fetch"]
    other = api_client.get("/v1/agents/other/settings/")
    assert other.json()["mcp_tool_grants"] == []
    assert other.json()["mcp_tool_grants_set"] is False

    cleared = api_client.patch(
        "/v1/agents/worker/settings/",
        {"mcp_tool_grants": []},
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["mcp_tool_grants"] == []
    assert cleared.json()["mcp_tool_grants_set"] is True

    undone = api_client.patch(
        "/v1/agents/worker/settings/",
        {"mcp_tool_grants_set": False},
        format="json",
    )
    assert undone.status_code == 200
    assert undone.json()["mcp_tool_grants"] == []
    assert undone.json()["mcp_tool_grants_set"] is True

    forced = api_client.patch(
        "/v1/agents/fresh/settings/",
        {"mcp_tool_grants_set": True, "use_suggestions": True},
        format="json",
    )
    assert forced.status_code == 200
    assert forced.json()["mcp_tool_grants"] == []
    assert forced.json()["mcp_tool_grants_set"] is False
    assert forced.json()["use_suggestions"] is True


def test_mcp_tool_grants_rejects_malformed(api_client):
    response = api_client.patch(
        "/v1/agents/worker/settings/",
        {"mcp_tool_grants": {"web_search": True}},
        format="json",
    )
    assert response.status_code == 400
    assert "mcp_tool_grants" in response.json()["error"]


def test_command_allowlist_rejects_malformed(api_client):
    response = api_client.patch(
        "/v1/agents/worker/settings/",
        {"command_allowlist": {"block": ["rm"]}},
        format="json",
    )
    assert response.status_code == 400
    assert "command_allowlist" in response.json()["error"]


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

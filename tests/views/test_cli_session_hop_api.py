"""API tests for /v1/cli-sessions/hop/ (REQ-138 / #531)."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from swarm.core import agent_settings as store
from swarm.core import chat_store
from swarm.core.cli_sessions import get_cli_session


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    yield
    store.reset_agent_settings_cache()


def test_get_capability_matrix(api_client):
    response = api_client.get("/v1/cli-sessions/hop/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "cli_session_hop_capabilities"
    assert body["automated_failover"] is False
    assert body["always_new_session"] is True
    assert "summary" in body["modes"]
    assert body["clis"]["grok"]["export"] == "summary"
    assert body["clis"]["agy"]["hop"] == "new_session_plus_inject"
    assert ":8001" not in str(body)


def test_post_hop_seeds_same_conversation(api_client, tmp_path):
    chat_store.save(
        "u0",
        "cli_agent",
        [
            {"role": "user", "content": "Design a rate limiter"},
            {"role": "assistant", "content": "Token bucket."},
        ],
        conversation_id="agt-guest-cli_agent",
        cli_sessions={"agy": "sid-old"},
        active_cli="grok",
        base_dir=tmp_path,
    )
    response = api_client.post(
        "/v1/cli-sessions/hop/",
        {
            "agent": "cli_agent",
            "from_cli": "grok",
            "to_cli": "agy",
            "conversation_id": "agt-guest-cli_agent",
            "mode": "summary",
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "cli_session_hop"
    assert body["conversation_id"] == "agt-guest-cli_agent"
    assert body["cli_session_id"] is None
    assert body["from_cli"] == "grok"
    assert body["to_cli"] == "agy"
    assert body["status"].startswith("Started a new agy session (grok → agy).")
    assert "Carried summary context" in body["status"]
    assert "sk-" not in body["injection"]["text"]
    assert "Token bucket" in body["injection"]["text"] or "rate limiter" in body["injection"]["text"].lower()
    assert get_cli_session("u0", "cli_agent", "agy") is None


def test_post_same_cli_is_400(api_client):
    response = api_client.post(
        "/v1/cli-sessions/hop/",
        {"agent": "cli_agent", "from_cli": "grok", "to_cli": "grok"},
        format="json",
    )
    assert response.status_code == 400
    assert "differ" in response.json()["error"]

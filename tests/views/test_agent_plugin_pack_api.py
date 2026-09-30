"""API tests for /v1/agents/<id>/plugins/ pack + import (#1396). No tokens."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core import agent_mcp as mcp
from swarm.core import agent_memory, agent_settings
from swarm.core import agent_plugin_pack as pack
from swarm.core.marketplace_catalog import MarketplaceCatalogError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_plugin_pack.json"

HOST_CONFIG = {
    "mcpServers": {
        "fetch": {
            "command": "uvx",
            "args": ["mcp-server-fetch"],
            "label": "fetch",
            "note": "Fetch a URL",
            "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            "registry_name": "io.github.example/fetch",
        }
    }
}


@pytest.fixture
def api_client():
    return APIClient()


def _marketplace_missing(_kind, _item_id, **_kwargs):
    raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    monkeypatch.setenv("SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json"))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    pack.reset_agent_plugin_pack_cache()
    mcp.reset_agent_mcp_cache()
    agent_memory.reset_memories_cache()
    agent_settings.reset_agent_settings_cache()
    monkeypatch.setattr("swarm.core.marketplace_catalog.install_item", _marketplace_missing)
    yield
    pack.reset_agent_plugin_pack_cache()
    mcp.reset_agent_mcp_cache()
    agent_memory.reset_memories_cache()
    agent_settings.reset_agent_settings_cache()


def test_plugin_pack_urls_accept_trailing_slash():
    assert resolve("/v1/agents/worker/plugins").url_name == "agent-plugins-api-no-slash"
    assert resolve("/v1/agents/worker/plugins/").url_name == "agent-plugins-api"
    assert resolve("/v1/agents/worker/plugins/pack").url_name == "agent-plugin-pack-api-no-slash"
    assert resolve("/v1/agents/worker/plugins/pack/").url_name == "agent-plugin-pack-api"
    assert resolve("/v1/agents/worker/plugins/import").url_name == "agent-plugin-pack-import-api-no-slash"
    assert resolve("/v1/agents/worker/plugins/import/").url_name == "agent-plugin-pack-import-api"


def test_export_empty_then_import_status_without_tokens(api_client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        empty = api_client.get("/v1/agents/worker/plugins/pack/")
        assert empty.status_code == 200
        assert empty.json()["object"] == "agent_plugin_pack"
        assert empty.json()["plugins"] == []

        imported = api_client.post(
            "/v1/agents/worker/plugins/import/",
            json.loads(FIXTURE.read_text(encoding="utf-8")),
            format="json",
        )
        assert imported.status_code == 200
        body = imported.json()
        dumped = json.dumps(body)
        assert "${GITHUB_TOKEN}" not in dumped
        assert "sk-" not in dumped
        assert "uvx" not in dumped
        assert "command" not in dumped
        assert "present-for-test" not in dumped
        assert body["object"] == "agent_plugin_pack_import"
        assert "mcp:io.github.example/fetch" in body["enabled"]
        assert "web_search" in body["enabled"]
        assert body["missing"] == []
        assert mcp.get_mcp("worker")["mcp_servers"] == ["fetch"]

        listed = api_client.get("/v1/agents/worker/plugins/")
        assert listed.status_code == 200
        assert listed.json()["object"] == "agent_plugins"
        assert {row["pluginId"] for row in listed.json()["plugins"]} == {
            "mcp:io.github.example/fetch",
            "web_search",
        }

        exported = api_client.get("/v1/agents/worker/plugins/pack/")
        assert exported.status_code == 200
        assert "uvx" not in json.dumps(exported.json())
        assert {row["pluginId"] for row in exported.json()["plugins"]} == {
            "mcp:io.github.example/fetch",
            "web_search",
        }


def test_import_missing_plugin_has_status_and_no_tokens(api_client, monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        response = api_client.post(
            "/v1/agents/copy/plugins/import/",
            {"plugins": ["unknown-plugin-id", "fetch"]},
            format="json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] == ["fetch"]
    assert body["missing"] == ["unknown-plugin-id"]
    assert body["missing_plugin"] == ["unknown-plugin-id"]
    assert body["missing_auth"] == []
    row = next(item for item in body["plugins"] if item["pluginId"] == "unknown-plugin-id")
    assert row["status"] == "missing-plugin"
    assert "token" not in row
    assert "url" not in row
    dumped = json.dumps(body)
    assert "command" not in dumped
    assert "present-for-test" not in dumped


def test_import_missing_auth_when_env_unset(api_client):
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        response = api_client.post(
            "/v1/agents/copy/plugins/import/",
            {"plugins": ["mcp:io.github.example/fetch"]},
            format="json",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] == []
    assert body["missing_auth"] == ["mcp:io.github.example/fetch"]
    assert body["missing_plugin"] == []
    row = body["plugins"][0]
    assert row["status"] == "missing-auth"
    assert row["connect_needed"] is True
    dumped = json.dumps(body)
    assert "${GITHUB_TOKEN}" not in dumped
    assert "uvx" not in dumped
    assert "command" not in dumped


def test_import_refuses_url_command_and_tokens(api_client):
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        leaked = api_client.post(
            "/v1/agents/worker/plugins/import/",
            {
                "plugins": [
                    {
                        "pluginId": "leaky",
                        "url": "https://example.invalid/mcp",
                        "headers": {"Authorization": "Bearer sk-notarealkeyABCDEFGH"},
                    }
                ]
            },
            format="json",
        )
    assert leaked.status_code == 400
    assert leaked.json()["code"] == "plugin_pack_secrets"
    assert "sk-notarealkeyABCDEFGH" not in json.dumps(leaked.json())
    assert pack.export_pack("worker")["plugins"] == []


def _post_design(api_client, body):
    from types import SimpleNamespace

    fake = SimpleNamespace(_config={}, load_designed_agents=lambda **_k: None)
    with patch(
        "swarm.views.agent_router_views.get_agent_router_blueprint",
        return_value=fake,
    ):
        return api_client.post("/v1/agents/design/", body, format="json")


def test_designed_agent_create_keeps_seat_when_plugin_missing(api_client, monkeypatch):
    """POST /v1/agents/design/ must 201 and report a miss without deleting the seat."""
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        created = _post_design(
            api_client,
            {
                "kind": "personality",
                "name": "Pack Seat",
                "instructions": "Stay up when a plugin is missing.",
                "plugins": ["not-a-plugin", "web_search"],
            },
        )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "success"
    assert body["agent"]["agent_id"] == "pack-seat"
    plugins = body["plugins"]
    by_id = {row["pluginId"]: row["status"] for row in plugins["plugins"]}
    assert by_id["not-a-plugin"] == "missing-plugin"
    assert by_id["web_search"] == "enabled"
    assert plugins["ok"] is True
    assert plugins["partial"] is True
    assert "not-a-plugin" in plugins["missing_plugin"]
    assert "present-for-test" not in json.dumps(body)
    from swarm.core.router_designs import load_designs

    assert any(row.get("agent_id") == "pack-seat" for row in load_designs())


def test_designed_agent_create_reports_secret_refusal_and_keeps_seat(api_client):
    """A refused secret field is on the payload, and the new agent still exists."""
    secret = "sk-notarealkeyABCDEFGH"
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=HOST_CONFIG):
        created = _post_design(
            api_client,
            {
                "kind": "personality",
                "name": "Safe Seat",
                "instructions": "Do not store credentials.",
                "plugins": [
                    {
                        "pluginId": "leaky",
                        "command": "npx",
                        "env": {"TOKEN": secret},
                    }
                ],
            },
        )
    assert created.status_code == 201
    body = created.json()
    dumped = json.dumps(body)
    assert body["agent"]["agent_id"] == "safe-seat"
    assert body["plugins"]["ok"] is False
    assert body["plugins"]["partial"] is True
    assert body["plugins"]["code"] == "plugin_pack_secrets"
    assert "refused field" in body["plugins"]["error"]
    assert secret not in dumped
    assert pack.export_pack("safe-seat")["plugins"] == []
    from swarm.core.router_designs import load_designs

    assert any(row.get("agent_id") == "safe-seat" for row in load_designs())

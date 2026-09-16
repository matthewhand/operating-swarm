"""API tests for /v1/agents/<id>/mcp/ (#142). No live MCP hosts."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.core import agent_mcp as store


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    store.reset_agent_mcp_cache()
    yield
    store.reset_agent_mcp_cache()


def _config():
    return {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [
                    {
                        "name": "web_fetch",
                        "description": "Fetch a URL",
                        "input_schema": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                        },
                    }
                ],
            }
        }
    }


def test_mcp_urls_accept_trailing_slash():
    assert resolve("/v1/agents/worker/mcp").url_name == "agent-mcp-api-no-slash"
    assert resolve("/v1/agents/worker/mcp/").url_name == "agent-mcp-api"
    assert resolve("/v1/agents/worker/mcp/tools/").url_name == "agent-mcp-tools-api"
    assert resolve("/v1/agents/worker/mcp/tools/web_fetch/").url_name == "agent-mcp-tool-detail-api"
    assert (
        resolve("/v1/agents/worker/mcp/tools/web_fetch/execute/").url_name
        == "agent-mcp-tool-execute-api"
    )


def test_get_defaults_off(api_client):
    response = api_client.get("/v1/agents/worker/mcp/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "agent_mcp"
    assert body["mcp_mode"] == "off"
    assert body["enabled"] is False


def test_patch_mode_and_list_tools(api_client):
    patched = api_client.patch(
        "/v1/agents/worker/mcp/",
        {"mcp_mode": "all"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["mcp_mode"] == "all"
    again = api_client.get("/v1/agents/worker/mcp/")
    assert again.json()["mcp_mode"] == "all"

    with patch("swarm.core.mcp_plugins.swarm_config", return_value=_config()):
        listed = api_client.get("/v1/agents/worker/mcp/tools/")
    assert listed.status_code == 200
    assert listed.json()["object"] == "mcp_tool_list"
    assert listed.json()["tools"][0]["name"] == "web_fetch"


def test_list_unauthorized_when_off(api_client):
    response = api_client.get("/v1/agents/worker/mcp/tools/")
    assert response.status_code == 403
    assert response.json()["code"] == "unauthorized"


def test_progressive_inspect_and_execute(api_client):
    api_client.patch(
        "/v1/agents/worker/mcp/",
        {"mcp_mode": "progressive", "mcp_servers": ["fetch"]},
        format="json",
    )
    with patch("swarm.core.mcp_plugins.swarm_config", return_value=_config()):
        inspect = api_client.get("/v1/agents/worker/mcp/tools/web_fetch/")
        assert inspect.status_code == 200
        assert inspect.json()["name"] == "web_fetch"
        assert "url" in inspect.json()["input_schema"]["properties"]

        denied = api_client.get("/v1/agents/worker/mcp/tools/not-a-tool/")
        assert denied.status_code == 403
        assert denied.json()["code"] == "unauthorized"

        with patch(
            "swarm.core.agent_mcp.call_plugin_mcp_tool",
            create=True,
        ):
            # execute_tool imports call_plugin_mcp_tool from mcp_plugins.
            with patch(
                "swarm.core.mcp_plugins.call_plugin_mcp_tool",
                return_value={"text": "ok"},
            ):
                executed = api_client.post(
                    "/v1/agents/worker/mcp/tools/web_fetch/execute/",
                    {"arguments": {"url": "https://example.invalid"}},
                    format="json",
                )
    assert executed.status_code == 200
    assert executed.json()["ok"] is True
    assert executed.json()["result"]["text"] == "ok"


def test_register_via_design_api(api_client):
    from types import SimpleNamespace

    fake = SimpleNamespace(_config={}, load_designed_agents=lambda **_k: None)
    with patch(
        "swarm.views.agent_router_views.get_agent_router_blueprint",
        return_value=fake,
    ):
        created = api_client.post(
            "/v1/agents/design/",
            {
                "kind": "api",
                "name": "Night Editor",
                "instructions": "Tighten prose.",
                "mcp_mode": "all",
                "mcp_servers": ["fetch"],
            },
            format="json",
        )
    assert created.status_code == 201
    agent = created.json()["agent"]
    assert agent["mcp_mode"] == "all"
    assert agent["mcp_servers"] == ["fetch"]
    listed = api_client.get("/v1/agents/night-editor/mcp/")
    assert listed.json()["mcp_mode"] == "all"
    assert listed.json()["mcp_servers"] == ["fetch"]

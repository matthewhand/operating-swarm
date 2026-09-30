"""GET/PATCH /v1/agents/<id>/mcp/ persists mcp_tools (#1313)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from swarm.core import agent_mcp as store
from swarm.core.agent_mcp import apply_mcp_to_agent, register_mcp


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    store.reset_agent_mcp_cache()
    yield
    store.reset_agent_mcp_cache()


def _config():
    return {
        "mcpServers": {
            "serverA": {
                "command": "uvx",
                "args": ["mcp-server-a"],
                "discovered_tools": [
                    {"name": "tool1", "description": "one"},
                    {"name": "tool2", "description": "two"},
                ],
            }
        }
    }


def test_patch_mcp_tools_roundtrip_matches_register(api_client):
    created = api_client.patch(
        "/v1/agents/worker/mcp/",
        {"mcp_mode": "all", "mcp_tools": {"serverA": ["tool1"]}},
        format="json",
    )
    assert created.status_code == 200
    assert created.json()["mcp_tools"] == {"serverA": ["tool1"]}
    again = api_client.get("/v1/agents/worker/mcp/")
    assert again.status_code == 200
    assert again.json()["mcp_tools"] == {"serverA": ["tool1"]}

    register_mcp("cli-bot", mode="all", mcp_tools={"serverA": ["tool1"]})
    api_agent = SimpleNamespace(functions=[], tools=[])
    cli_agent = SimpleNamespace(functions=[], tools=[])
    apply_mcp_to_agent(api_agent, "worker", config=_config())
    apply_mcp_to_agent(cli_agent, "cli-bot", config=_config())
    api_names = sorted(fn.name for fn in api_agent.functions)
    cli_names = sorted(fn.name for fn in cli_agent.functions)
    assert api_names == cli_names == ["tool1"]


def test_patch_rejects_malformed_mcp_tools(api_client):
    response = api_client.patch(
        "/v1/agents/worker/mcp/",
        {"mcp_tools": ["tool1"]},
        format="json",
    )
    assert response.status_code == 400
    assert "mcp_tools" in response.json()["error"]

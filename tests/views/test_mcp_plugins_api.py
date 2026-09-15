"""API tests for /v1/mcp-plugins/ (#502). No live hosts. No secrets."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from django.urls import resolve
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


def test_mcp_plugins_urls_accept_trailing_slash():
    assert resolve("/v1/mcp-plugins").url_name == "mcp-plugins-api-no-slash"
    assert resolve("/v1/mcp-plugins/").url_name == "mcp-plugins-api"
    assert resolve("/v1/mcp-plugins/discover/").url_name == "mcp-plugins-discover"
    assert resolve("/v1/mcp-plugins/fetch/").url_name == "mcp-plugins-detail"


def test_list_upsert_remove_and_refuse_plaintext(api_client, tmp_path: Path):
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps({"llm": {}, "mcpServers": {}}), encoding="utf-8")
    with (
        patch("swarm.core.remotes.load_raw_config", return_value=({"llm": {}, "mcpServers": {}}, path)),
        # GET reads plugins.swarm_config() → AppConfig.config (server mode);
        # pin it to the tmp file so the dev machine's real XDG servers cannot
        # leak in and persists inside the test are reflected in responses.
        patch("swarm.core.mcp_plugins.swarm_config", side_effect=lambda: json.loads(path.read_text(encoding="utf-8"))),
    ):
        listed = api_client.get("/v1/mcp-plugins/")
        assert listed.status_code == 200
        assert listed.json()["object"] == "mcp_plugins"
        assert listed.json()["servers"] == []

        created = api_client.post(
            "/v1/mcp-plugins/",
            {
                "name": "fetch",
                "kind": "local",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
            },
            format="json",
        )
        assert created.status_code == 200
        names = {row["name"] for row in created.json()["servers"]}
        assert "fetch" in names
        assert "sk-" not in json.dumps(created.json())

        bad = api_client.post(
            "/v1/mcp-plugins/",
            {
                "name": "leaky",
                "kind": "remote",
                "url": "https://example.invalid/mcp",
                "headers": {"Authorization": "Bearer sk-live"},
            },
            format="json",
        )
        assert bad.status_code == 400
        assert bad.json()["code"] == "plaintext_secret"
        assert "sk-live" not in path.read_text(encoding="utf-8")

        removed = api_client.delete("/v1/mcp-plugins/fetch/")
        assert removed.status_code == 200
        assert all(row["name"] != "fetch" for row in removed.json()["servers"])


def test_discover_local_and_remote_mocks(api_client, tmp_path: Path):
    path = tmp_path / "swarm_config.json"
    cfg = {
        "llm": {},
        "mcpServers": {
            "fetch": {"command": "uvx", "args": ["mcp-server-fetch"]},
            "proxy": {"url": "https://example.invalid/mcp", "kind": "remote"},
        },
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")

    def fake_list(spec):
        if spec.get("kind") == "remote" or spec.get("url"):
            return [{"name": "search_docs", "description": "Search remote docs"}]
        return [{"name": "fetch", "description": "Fetch a URL"}]

    with (
        patch("swarm.core.remotes.load_raw_config", return_value=(cfg, path)),
        patch("swarm.core.mcp_plugins.swarm_config", return_value=cfg),
        patch("swarm.core.mcp_plugins.list_tools_for_spec", side_effect=lambda spec, **_k: fake_list(spec)),
    ):
        local = api_client.post("/v1/mcp-plugins/discover/", {"name": "fetch"}, format="json")
        assert local.status_code == 200
        assert local.json()["tools"][0]["name"] == "fetch"

        remote = api_client.post(
            "/v1/mcp-plugins/discover/",
            {"name": "proxy", "kind": "remote", "url": "https://example.invalid/mcp"},
            format="json",
        )
        assert remote.status_code == 200
        assert remote.json()["tools"][0]["name"] == "search_docs"
        assert "sk-" not in json.dumps(remote.json())

    from swarm.core.mcp_plugins import McpPluginError

    with (
        patch("swarm.core.mcp_plugins.swarm_config", return_value=cfg),
        patch(
            "swarm.core.mcp_plugins.list_tools_for_spec",
            side_effect=McpPluginError(
                "mock MCP refused connect",
                code="mcp_discover_failed",
                status=502,
            ),
        ),
    ):
        failed = api_client.post(
            "/v1/mcp-plugins/discover/",
            {"name": "fetch"},
            format="json",
        )
        assert failed.status_code == 502
        assert failed.json()["code"] == "mcp_discover_failed"
        assert "refused" in failed.json()["error"]


def test_upsert_and_discover_openapi_mock(api_client, tmp_path: Path):
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps({"llm": {}, "mcpServers": {}}), encoding="utf-8")

    def fake_list(spec):
        assert spec.get("source") == "openapi"
        assert spec.get("openapi_spec_url") == "https://example.invalid/openapi.json"
        return [
            {"name": "list_pets", "description": "List pets"},
            {"name": "get_pet", "description": "Get a pet"},
        ]

    cfg = {"llm": {}, "mcpServers": {}}
    with (
        patch("swarm.core.remotes.load_raw_config", return_value=(cfg, path)),
        patch("swarm.core.mcp_plugins.swarm_config", return_value=cfg),
    ):
        created = api_client.post(
            "/v1/mcp-plugins/",
            {
                "name": "pets",
                "source": "openapi",
                "kind": "local",
                "openapi_spec_url": "https://example.invalid/openapi.json",
                "env": {"API_KEY": "${API_KEY}"},
            },
            format="json",
        )
        assert created.status_code == 200
        pets = next(row for row in created.json()["servers"] if row["name"] == "pets")
        assert pets["source"] == "openapi"
        assert pets["command"] == "uvx"
        assert pets["args"] == ["mcp-openapi-proxy"]
        assert pets["openapi_spec_url"] == "https://example.invalid/openapi.json"
        assert "sk-" not in json.dumps(created.json())

        missing = api_client.post(
            "/v1/mcp-plugins/",
            {"name": "no-spec", "source": "openapi", "kind": "local"},
            format="json",
        )
        assert missing.status_code == 400
        assert missing.json()["code"] == "bad_payload"

    cfg = {
        "llm": {},
        "mcpServers": {
            "pets": {
                "source": "openapi",
                "kind": "local",
                "command": "uvx",
                "args": ["mcp-openapi-proxy"],
                "openapi_spec_url": "https://example.invalid/openapi.json",
            }
        },
    }
    path.write_text(json.dumps(cfg), encoding="utf-8")
    with (
        patch("swarm.core.remotes.load_raw_config", return_value=(cfg, path)),
        patch("swarm.core.mcp_plugins.swarm_config", return_value=cfg),
        patch("swarm.core.mcp_plugins.list_tools_for_spec", side_effect=lambda spec, **_k: fake_list(spec)),
    ):
        discovered = api_client.post(
            "/v1/mcp-plugins/discover/",
            {
                "name": "pets",
                "source": "openapi",
                "kind": "local",
                "openapi_spec_url": "https://example.invalid/openapi.json",
            },
            format="json",
        )
        assert discovered.status_code == 200
        assert [row["name"] for row in discovered.json()["tools"]] == ["list_pets", "get_pet"]
        assert discovered.json()["source"] == "openapi"

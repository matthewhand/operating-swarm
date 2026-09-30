"""Client tests: real payload shapes, auth, honest failures — no live network."""

from __future__ import annotations

import httpx
import pytest

from os_marchy_systray.client import (
    OSAPIError,
    OSAuthError,
    OSClient,
    OSConnectionError,
)
from tests.fixtures import (
    AGENTS_PAYLOAD,
    CLI_PAYLOAD,
    HEALTH_PAYLOAD,
    REMOTES_PAYLOAD,
    ROSTERS_PAYLOAD,
    TEAMS_PAYLOAD,
)

BASE = "http://os.test"


def _router(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        table = {
            "/health": HEALTH_PAYLOAD,
            "/v1/agents/": AGENTS_PAYLOAD,
            "/v1/teams/": TEAMS_PAYLOAD,
            "/v1/team-rosters/": ROSTERS_PAYLOAD,
            "/v1/cli-agents/": CLI_PAYLOAD,
            "/v1/remotes/": REMOTES_PAYLOAD,
        }
        if path in table:
            return httpx.Response(200, json=table[path])
        return httpx.Response(404, json={"error": "not found"})

    return handler


def _client(handler, token: str | None = None) -> OSClient:
    return OSClient(BASE, token, transport=httpx.MockTransport(handler))


def test_agents_parses_real_payload_shape():
    seen: list[httpx.Request] = []
    with _client(_router(seen)) as client:
        agents = client.agents()
    assert [row["agent_id"] for row in agents] == ["cos", "research", "lonely"]
    assert seen[-1].url.path == "/v1/agents/"


def test_list_endpoints_parse_data_envelopes():
    seen: list[httpx.Request] = []
    with _client(_router(seen)) as client:
        assert [row["id"] for row in client.teams()] == ["fast"]
        assert [row["id"] for row in client.team_rosters()] == ["newsroom"]
        cli = client.cli_agents()
        assert cli["rail"][0]["id"] == "cli_agent"
        remotes = client.remotes()
        assert [row["id"] for row in remotes["configured"]] == ["omb", "herdr-x"]


def test_bearer_token_sent_and_never_leaked():
    seen: list[httpx.Request] = []
    with _client(_router(seen), token="s3cr3t-token") as client:
        client.agents()
    assert seen[-1].headers["Authorization"] == "Bearer s3cr3t-token"
    # The secret never appears in the client's public surface.
    assert "s3cr3t-token" not in repr(client)
    assert "s3cr3t-token" not in str(client.base_url)


def test_unauthorized_is_honest_and_does_not_echo_token():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "token required"})

    with _client(handler, token="s3cr3t-token") as client:
        with pytest.raises(OSAuthError) as excinfo:
            client.agents()
    assert excinfo.value.status_code == 401
    assert "s3cr3t-token" not in str(excinfo.value)


def test_connection_refused_maps_to_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with _client(handler) as client, pytest.raises(OSConnectionError):
        client.agents()


def test_timeout_maps_to_connection_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with _client(handler) as client, pytest.raises(OSConnectionError):
        client.health()


def test_server_error_maps_to_api_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    with _client(handler) as client, pytest.raises(OSAPIError) as excinfo:
        client.agents()
    assert excinfo.value.status_code == 500
    assert "boom" in str(excinfo.value)


def test_health_ok():
    seen: list[httpx.Request] = []
    with _client(_router(seen)) as client:
        health = client.health()
    assert health.ok is True
    assert health.status == "ok"
    assert health.version == "0.5.4"


def test_test_connection_ok():
    seen: list[httpx.Request] = []
    with _client(_router(seen)) as client:
        result = client.test_connection()
    assert result.ok is True
    assert result.state == "ok"
    assert result.base_url == BASE


def test_test_connection_offline_is_honest():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with _client(handler) as client:
        result = client.test_connection()
    assert result.ok is False
    assert result.state == "offline"
    assert result.base_url == BASE


def test_test_connection_unauthorized():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        return httpx.Response(401, json={"error": "token required"})

    with _client(handler) as client:
        result = client.test_connection()
    assert result.ok is False
    assert result.state == "unauthorized"


def test_base_url_required():
    with pytest.raises(ValueError):
        OSClient("")

"""REQ-131: OpenMousBot List bots — progressive populate (slow, not hung).

Intent: If health is up, listing bots must complete (success or clear error)
within a bounded timeout (<=10-15s) — never an infinite spinner.
"""

from pathlib import Path
from unittest.mock import patch
from swarm.core.remotes import RemoteSpec, _omb_list, HttpResult
from swarm.core.remote_teams import _DISCOVERY_PATHS

REPO_ROOT = Path(__file__).resolve().parents[2]
REMOTES_SETTINGS_TSX = REPO_ROOT / "webui" / "frontend" / "src" / "components" / "RemotesSettings.tsx"
API_TS = REPO_ROOT / "webui" / "frontend" / "src" / "lib" / "api.ts"


def test_discovery_paths_includes_openmousbot_and_omb():
    assert "openmousbot" in _DISCOVERY_PATHS
    assert "omb" in _DISCOVERY_PATHS
    assert _DISCOVERY_PATHS["openmousbot"][0] == "/api/bots?messages=0"
    assert _DISCOVERY_PATHS["omb"][0] == "/api/bots?messages=0"


def test_omb_list_strips_trailing_slash_and_bounds_timeout():
    spec = RemoteSpec(id="omb", title="OpenMousBot", host_label="OMB", base_url="http://example.com:8000/", api_key="secret")
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=200,
            body={"bots": [{"id": "bot-1", "name": "Agent 1"}]},
            url="http://example.com:8000/api/bots",
        )
        res = _omb_list(spec, timeout=30.0)

        # Timeout should be bounded to <= 10.0s
        mock_http.assert_called_once()
        _, kwargs = mock_http.call_args
        assert kwargs["timeout"] <= 10.0
        # URL must not contain double slashes
        assert mock_http.call_args[0][1] == "http://example.com:8000/api/bots?messages=0"
        assert res.ok is True
        assert "1 bot(s)" in res.detail


def test_omb_list_handles_alternate_response_shapes():
    spec = RemoteSpec(id="omb", title="OpenMousBot", host_label="OMB", base_url="http://example.com:8000")
    with patch("swarm.core.remotes.http_json") as mock_http:
        # Array response
        mock_http.return_value = HttpResult(
            status=200,
            body=[{"id": "bot-a"}, {"id": "bot-b"}],
            url="http://example.com:8000/api/bots",
        )
        res = _omb_list(spec, timeout=5.0)
        assert res.ok is True
        assert "2 bot(s)" in res.detail

        # Agents key response
        mock_http.return_value = HttpResult(
            status=200,
            body={"agents": [{"id": "agent-1"}]},
            url="http://example.com:8000/api/bots",
        )
        res = _omb_list(spec, timeout=5.0)
        assert res.ok is True
        assert "1 bot(s)" in res.detail


def test_omb_list_handles_http_error_gracefully():
    spec = RemoteSpec(id="omb", title="OpenMousBot", host_label="OMB", base_url="http://example.com:8000")
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=504,
            error="Gateway Timeout",
            url="http://example.com:8000/api/bots",
        )
        res = _omb_list(spec, timeout=5.0)
        assert res.ok is False
        assert "Gateway Timeout" in res.detail


def test_frontend_operate_remote_bounded_timeout():
    content = API_TS.read_text(encoding="utf-8")
    assert "timeoutMs" in content
    assert "AbortController" in content
    assert "signal: controller.signal" in content
    # REQ-131 / #302: list abort stays short; send is longer and named.
    assert "Remote operate operation timed out" in content
    assert "OPERATE_LIST_TIMEOUT_MS = 12_000" in content
    assert "OPERATE_SEND_TIMEOUT_MS = 180_000" in content
    assert "Remote operate send timed out" in content


def test_frontend_remotes_settings_bots_from_operate():
    content = REMOTES_SETTINGS_TSX.read_text(encoding="utf-8")
    assert "botsFromOperate" in content
    assert "'agents' in raw" in content
    assert "'sessions' in raw" in content
    assert "'data' in raw" in content
    assert "OPERATE_LIST_TIMEOUT_MS" in content
    assert "OPERATE_SEND_TIMEOUT_MS" in content

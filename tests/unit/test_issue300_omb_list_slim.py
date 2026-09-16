"""Issue #300 — OpenMousBot list uses slim GET /api/bots?messages=0."""
from unittest.mock import patch

from swarm.core.remote_teams import _DISCOVERY_PATHS
from swarm.core.remotes import HttpResult, RemoteSpec, _OMB_LIST_PATH, _omb_list


def _spec(**kwargs) -> RemoteSpec:
    defaults = dict(
        id="omb",
        title="OpenMousBot",
        host_label="OMB",
        base_url="http://10.0.0.32:8800",
    )
    defaults.update(kwargs)
    return RemoteSpec(**defaults)


def test_omb_list_path_omits_transcripts():
    assert _OMB_LIST_PATH == "/api/bots?messages=0"


def test_omb_list_requests_slim_bots_not_fat_dump():
    spec = _spec(api_key="secret")
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=200,
            body={"bots": [{"id": "b1", "name": "Alpha"}]},
            url="http://10.0.0.32:8800/api/bots?messages=0",
        )
        res = _omb_list(spec, timeout=30.0)
    mock_http.assert_called_once()
    method, url = mock_http.call_args[0][:2]
    assert method == "GET"
    assert url == "http://10.0.0.32:8800/api/bots?messages=0"
    assert "messages=0" in url
    assert not url.rstrip("/").endswith("/api/bots")
    assert mock_http.call_args.kwargs["timeout"] <= 10.0
    assert res.ok is True
    assert res.http_status == 200
    assert "1 bot(s)" in res.detail
    assert "slow or hung" not in res.detail.lower()


def test_omb_list_401_is_honest_auth_not_timeout():
    spec = _spec(api_key="")
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=401,
            error="http 401",
            body={"error": "Unauthorized"},
            url="http://10.0.0.32:8800/api/bots?messages=0",
        )
        res = _omb_list(spec, timeout=12.0)
    mock_http.assert_called_once()
    assert mock_http.call_args[0][1].endswith("/api/bots?messages=0")
    assert res.ok is False
    assert res.http_status == 401
    assert "OMB_API_KEY" in res.detail
    assert "slow or hung" not in res.detail.lower()
    assert "timed out" not in res.detail.lower()


def test_omb_list_403_is_honest_auth():
    spec = _spec(api_key="wrong")
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=403,
            error="http 403",
            url="http://10.0.0.32:8800/api/bots?messages=0",
        )
        res = _omb_list(spec, timeout=5.0)
    assert res.ok is False
    assert res.http_status == 403
    assert "OMB_API_KEY" in res.detail


def test_discovery_prefers_slim_omb_bots_path():
    for kind in ("omb", "openmousbot", "openmausbot"):
        assert _DISCOVERY_PATHS[kind][0] == "/api/bots?messages=0"

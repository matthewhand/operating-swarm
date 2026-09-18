"""#541 — OMB names the real cause, not a guessed config fault.

OpenMousBot's server enforces a loopback / device-pairing policy: calling it
over the LAN with a *valid* key answers 403
``{"error": "forbidden: loopback host required (pair this device to use the
server remotely)"}``. The old message claimed auth was missing and told the
operator to set a key that was already set — a dead end.

Acceptance (from the issue):
- a 403 whose body names loopback/pairing produces a message that says so and
  never mentions settings or keys;
- a genuinely missing key still produces the "set remotes.omb.api_key or
  OMB_API_KEY" sentence (no regression);
- the harness's own message is carried through; our text is fallback only;
- reachability and authorisation stay separate facts (health 200 vs operate 403).
"""
from unittest.mock import patch

from swarm.core.remotes import HttpResult, RemoteSpec, _omb_list

_OMB_URL = "http://198.51.100.32:8802/api/bots?messages=0"

# The exact body the live OpenMousBot returns over the LAN (#541 evidence).
_LOOPBACK_403_BODY = {
    "error": "forbidden: loopback host required (pair this device to use the server remotely)",
}


def _spec(**kwargs) -> RemoteSpec:
    defaults = {
        "id": "omb",
        "title": "OpenMousBot",
        "host_label": "OMB",
        "base_url": "http://198.51.100.32:8802",
    }
    defaults.update(kwargs)
    return RemoteSpec(**defaults)


def _list_with_status_and_body(status: int, body, spec: RemoteSpec):
    with patch("swarm.core.remotes.http_json") as mock_http:
        mock_http.return_value = HttpResult(
            status=status,
            error=f"http {status}",
            body=body,
            url=_OMB_URL,
        )
        return _omb_list(spec, timeout=5.0)


def test_loopback_403_names_pairing_not_keys():
    """The live #541 case: key is set and accepted; the policy is the cause."""
    res = _list_with_status_and_body(403, _LOOPBACK_403_BODY, _spec(api_key="valid-key"))
    assert res.ok is False
    assert res.http_status == 403
    lowered = res.detail.lower()
    assert "loopback" in lowered or "pair" in lowered
    assert "OMB_API_KEY" not in res.detail
    assert "api_key" not in lowered
    assert "settings" not in lowered
    # The harness's own sentence is carried through verbatim somewhere in the
    # detail — never paraphrased away.
    assert "loopback host required" in lowered


def test_plain_403_with_key_set_does_not_demand_a_key():
    """403 without a shaped body and with a key configured: do not claim a
    config fault; report the rejection honestly."""
    res = _list_with_status_and_body(403, {"error": "forbidden"}, _spec(api_key="valid-key"))
    assert res.ok is False
    assert res.http_status == 403
    assert "OMB_API_KEY" not in res.detail


def test_missing_key_still_advises_the_env_var():
    """No key configured + auth-shaped rejection → the classic, correct hint."""
    res = _list_with_status_and_body(401, {"error": "Unauthorized"}, _spec(api_key=""))
    assert res.ok is False
    assert res.http_status == 401
    assert "remotes.omb.api_key" in res.detail
    assert "OMB_API_KEY" in res.detail


def test_loopback_403_keeps_body_out_of_the_bubble():
    """Raw JSON is never dumped; the structured message is rendered as text."""
    import json

    res = _list_with_status_and_body(403, _LOOPBACK_403_BODY, _spec(api_key="valid-key"))
    assert "{" not in res.detail
    json.dumps(res.data)  # data still carries the structured body for callers


def test_existing_401_with_key_set_remains_auth_shaped():
    """401 with a key present is a *rejected* key — mention auth, not pairing."""
    res = _list_with_status_and_body(401, {"error": "Unauthorized"}, _spec(api_key="valid-key"))
    assert res.ok is False
    assert "loopback" not in res.detail.lower()
    assert "pair" not in res.detail.lower()


def test_health_distinguishes_up_but_unpaired_from_auth_required():
    """Reachability vs authorisation stay separate facts (#541 acceptance)."""
    from swarm.core.remotes import _check_health_spec

    spec = _spec(api_key="valid-key")
    with (
        patch("swarm.core.remotes.http_json") as mock_http,
        patch("swarm.core.remotes._tcp_probe", return_value=2),
    ):
        responses = {
            "http://198.51.100.32:8802/api/health": HttpResult(
                status=200, body={"ok": True}, url="http://198.51.100.32:8802/api/health"
            ),
            # Same health path, but authorised-probe style answer varies by
            # deployment; cover the branch where the alive endpoint answers 403
            # with the pairing body (e.g. a stricter reverse proxy).
            "http://198.51.100.32:8802/forbidden": HttpResult(
                status=403, error="http 403", body=_LOOPBACK_403_BODY,
                url="http://198.51.100.32:8802/forbidden",
            ),
        }

        def fake_http(_method, url, **_kwargs):
            if url.endswith("/api/health"):
                return responses[url]
            return responses["http://198.51.100.32:8802/forbidden"]

        mock_http.side_effect = fake_http
        res = _check_health_spec(spec)
    assert res.ok is True
    assert res.state == "UP"

    # Now the health endpoint itself answers with the pairing 403: still UP
    # (reachable), but the detail must name the policy, not "auth required".
    with (
        patch("swarm.core.remotes.http_json") as mock_http,
        patch("swarm.core.remotes._tcp_probe", return_value=2),
    ):
        mock_http.return_value = HttpResult(
            status=403, error="http 403", body=_LOOPBACK_403_BODY,
            url="http://198.51.100.32:8802/api/health",
        )
        res2 = _check_health_spec(spec)
    assert res2.ok is True
    assert res2.state == "UP"
    lowered = res2.detail.lower()
    assert "pairing" in lowered or "refuses" in lowered
    assert "auth required" not in lowered

"""#1273 — OpenMausBot device pairing is an operator affordance, not a curl dance.

The harness's pairing flow (read from its own UI source): the server shows a
6-char code (5-min TTL, one-time); the client POSTs it to ``/api/auth/pair``
with ``{code, label, cookie: true}`` and receives a session cookie that
authenticates every later call. The loopback policy rejects everything else
from non-loopback callers (#541 evidence).

Operating Swarm integration:

1. ``POST /v1/remotes/omb/pair/`` with ``{"code": "AB12CD"}`` performs the
   harness exchange, persists the returned session cookie into
   ``remotes.omb.cookie`` (config ownership treats it as a secret), and
   returns ``{"ok": true}``.
2. A wrong/expired code surfaces the harness's own sentence with 401 —
   the operator is sent back to the server for a fresh code.
3. The remote must be the ``omb`` kind; other kinds answer 400 (the
   pairing flow is MausBot-specific).
4. After a successful pair, ``load_remote`` resolves ``spec.cookie`` so
   ``_auth_headers`` carries it on every later call.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from swarm.core import remotes as remotes_core

OMB_BASE = "http://127.0.0.1:8802"


@pytest.fixture(autouse=True)
def _clean_cookie_env(monkeypatch):
    """The pair path writes the cookie into the *real* process env (that is
    the product). Snapshot it away per-test so runs are order-independent."""
    monkeypatch.delenv("OMB_SESSION_COOKIE", raising=False)


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="omb-pair-user", password="pw")


@pytest.fixture
def client(user):
    c = Client()
    c.login(username="omb-pair-user", password="pw")
    return c


@pytest.fixture
def omb_config(tmp_path: Path) -> Path:
    """A config file with the omb remote already added (base_url, no cookie)."""
    cfg = {
        "remotes": {
            "omb": {"kind": "omb", "base_url": OMB_BASE, "api_key_env": "OMB_API_KEY"}
        }
    }
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def _pair(client, config_path: Path, code: str = "AB12CD"):
    with mock.patch(
        "swarm.core.remotes.resolve_config_path", return_value=config_path
    ):
        return client.post(
            "/v1/remotes/omb/pair/",
            data=json.dumps({"code": code, "label": "operating-swarm"}),
            content_type="application/json",
        )


def _harness_exchange(result):
    """MausBot-side exchange: 200 + Set-Cookie on a good code, 401 otherwise."""
    response = mock.Mock(status=200 if result == "ok" else 401)
    response.headers = (
        {"set-cookie": "mausbot_session=st-123; Path=/; HttpOnly"}
        if result == "ok"
        else {}
    )
    response.body = (
        {"ok": True, "id": "st-123", "label": "operating-swarm"}
        if result == "ok"
        else {"error": "pairing code is wrong or has expired; create a new one on the server"}
    )
    return response


@pytest.mark.django_db
def test_pair_exchanges_code_and_persists_cookie(client, omb_config):
    """Good code → cookie into the XDG env store; config records ${ENV}."""

    def fake_http_json(method, url, **kwargs):
        assert method == "POST"
        assert url.endswith("/api/auth/pair")
        assert kwargs["json"]["code"] == "AB12CD"
        assert kwargs["json"]["label"] == "operating-swarm"
        return _harness_exchange("ok")

    with (
        mock.patch("swarm.core.remotes.resolve_config_path", return_value=omb_config),
        mock.patch("swarm.core.remotes.http_json", side_effect=fake_http_json),
        mock.patch.object(remotes_core, "load_remote") as load_remote,
    ):
        spec = mock.Mock(base_url=OMB_BASE, id="omb", kind="omb", session_cookie_env="")
        load_remote.return_value = spec
        resp = client.post(
            "/v1/remotes/omb/pair/",
            data=json.dumps({"code": "AB12CD", "label": "operating-swarm"}),
            content_type="application/json",
        )
    assert resp.status_code == 200, resp.content.decode()
    body = resp.json()
    assert body["ok"] is True

    # #460 doctrine: the cookie lives in the XDG swarm .env (the secret
    # store), never as plaintext in the config. The config records the
    # ${ENV} placeholder + env name; the process env carries the value.
    import os

    from swarm.utils.dotenv_load import xdg_swarm_env_path

    env_text = xdg_swarm_env_path().read_text(encoding="utf-8")
    assert "mausbot_session=st-123" in env_text
    assert os.environ.get("OMB_SESSION_COOKIE", "").startswith("mausbot_session=st-123")

    cfg = json.loads(omb_config.read_text(encoding="utf-8"))
    assert cfg["remotes"]["omb"]["cookie"] == "${OMB_SESSION_COOKIE}"
    assert cfg["remotes"]["omb"]["session_cookie_env"] == "OMB_SESSION_COOKIE"

    # And load_remote resolves it for _auth_headers.
    with mock.patch("swarm.core.remotes.resolve_config_path", return_value=omb_config):
        spec2 = remotes_core.load_remote("omb")
    assert "mausbot_session=st-123" in (spec2.cookie or "")


@pytest.mark.django_db
def test_pair_wrong_code_surfaces_harness_sentence(client, omb_config):
    """401 from the harness → 401 here, the harness's own sentence, no persist."""
    with (
        mock.patch("swarm.core.remotes.resolve_config_path", return_value=omb_config),
        mock.patch("swarm.core.remotes.http_json", return_value=_harness_exchange("bad")),
        mock.patch("swarm.core.remotes.load_remote") as load_remote,
    ):
        load_remote.return_value = mock.Mock(base_url=OMB_BASE, id="omb", kind="omb", session_cookie_env="")
        resp = client.post(
            "/v1/remotes/omb/pair/",
            data=json.dumps({"code": "000000"}),
            content_type="application/json",
        )
    assert resp.status_code == 401
    assert "wrong or has expired" in resp.json()["error"]
    # Nothing was persisted: config untouched, no cookie env var written.
    cfg = json.loads(omb_config.read_text(encoding="utf-8"))
    assert not cfg["remotes"]["omb"].get("cookie")
    assert not cfg["remotes"]["omb"].get("session_cookie_env")
    import os

    assert not os.environ.get("OMB_SESSION_COOKIE")


@pytest.mark.django_db
def test_pair_rejects_non_omb_remote(client, omb_config):
    """Pairing is a MausBot flow — other kinds answer 400, no harness call."""
    with (
        mock.patch("swarm.core.remotes.resolve_config_path", return_value=omb_config),
        mock.patch("swarm.core.remotes.http_json") as probe,
    ):
        resp = client.post(
            "/v1/remotes/rakazo/pair/",
            data=json.dumps({"code": "AB12CD"}),
            content_type="application/json",
        )
    assert resp.status_code == 400
    assert probe.call_count == 0

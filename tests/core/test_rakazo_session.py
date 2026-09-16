"""Rakazo Better Auth session from env/secret-store (#160).

Operate list sends Cookie / Authorization from RAKAZO_SESSION_COOKIE
and/or RAKAZO_API_KEY. Tests assert header names on the wire and that
values never appear in logs or stdout. HTTP is respx-mocked — no live LAN.
"""
from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx

from swarm.core import remotes as remotes_core

_COOKIE = "better-auth.session_token=test-session-$literal-DO-NOT-LOG"
_API_KEY = "rkz_test_key_DO_NOT_LOG"
_BASE = "http://rakazo.test"


def _cfg() -> dict:
    return {
        "llm": {},
        "remotes": {
            "rakazo": {
                "base_url": _BASE,
                "api_key": "${RAKAZO_API_KEY}",
                "api_key_env": "RAKAZO_API_KEY",
                "cookie": "${RAKAZO_SESSION_COOKIE}",
                "session_cookie_env": "RAKAZO_SESSION_COOKIE",
            }
        },
    }


def _joined_output(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> str:
    captured = capsys.readouterr()
    parts = [caplog.text, captured.out, captured.err]
    for rec in caplog.records:
        parts.append(rec.getMessage())
        parts.append(str(rec.msg))
        parts.append(repr(rec.args))
    return "\n".join(parts)


def _assert_secret_silent(blob: str) -> None:
    assert _COOKIE not in blob
    assert _API_KEY not in blob


@pytest.fixture(autouse=True)
def _clean_rakazo_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("RAKAZO_SESSION_COOKIE", "RAKAZO_API_KEY", "RAKAZO_BASE_URL"):
        monkeypatch.delenv(var, raising=False)


def _header_names(request: httpx.Request) -> set[str]:
    return {k.lower() for k in request.headers.keys()}


@respx.mock
def test_operate_list_sends_cookie_and_authorization_from_env(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAKAZO_SESSION_COOKIE", _COOKIE)
    monkeypatch.setenv("RAKAZO_API_KEY", _API_KEY)
    route = respx.post(f"{_BASE}/rpc/bots/list").mock(
        return_value=httpx.Response(200, json={"json": [{"id": "bot-1", "name": "alpha"}]})
    )
    with caplog.at_level(logging.DEBUG):
        result = remotes_core.operate("rakazo", "list", config=_cfg())
    assert result.ok is True
    assert route.called
    req = route.calls.last.request
    names = _header_names(req)
    assert "cookie" in names
    assert "authorization" in names
    assert req.headers["cookie"] == _COOKIE
    assert req.headers["authorization"] == f"Bearer {_API_KEY}"
    blob = _joined_output(caplog, capsys) + (result.detail or "")
    _assert_secret_silent(blob)


@respx.mock
def test_operate_list_cookie_only_preserves_dollar_in_cookie(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAKAZO_SESSION_COOKIE", _COOKIE)
    route = respx.post(f"{_BASE}/rpc/bots/list").mock(
        return_value=httpx.Response(200, json={"json": []})
    )
    with caplog.at_level(logging.DEBUG):
        result = remotes_core.operate("rakazo", "list", config=_cfg())
    assert result.ok is True
    req = route.calls.last.request
    names = _header_names(req)
    assert "cookie" in names
    assert "authorization" not in names
    assert req.headers["cookie"] == _COOKIE
    assert "$literal" in req.headers["cookie"]
    _assert_secret_silent(_joined_output(caplog, capsys) + (result.detail or ""))


@respx.mock
def test_operate_list_api_key_only_sends_authorization(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAKAZO_API_KEY", _API_KEY)
    route = respx.post(f"{_BASE}/rpc/bots/list").mock(
        return_value=httpx.Response(200, json={"json": [{"id": "bot-2"}]})
    )
    with caplog.at_level(logging.DEBUG):
        result = remotes_core.operate("rakazo", "list", config=_cfg())
    assert result.ok is True
    req = route.calls.last.request
    names = _header_names(req)
    assert "authorization" in names
    assert "cookie" not in names
    assert req.headers["authorization"] == f"Bearer {_API_KEY}"
    _assert_secret_silent(_joined_output(caplog, capsys) + (result.detail or ""))


@respx.mock
def test_operate_list_without_env_is_honest_401_and_omits_auth_headers(
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    route = respx.post(f"{_BASE}/rpc/bots/list").mock(
        return_value=httpx.Response(401, json={"error": "UNAUTHORIZED"})
    )
    with caplog.at_level(logging.DEBUG):
        result = remotes_core.operate("rakazo", "list", config=_cfg())
    assert result.ok is False
    assert result.http_status == 401
    assert result.gap == "rakazo_rpc_requires_better_auth_session"
    assert "Better Auth" in result.detail
    assert "RAKAZO_SESSION_COOKIE" in result.detail
    req = route.calls.last.request
    names = _header_names(req)
    assert "cookie" not in names
    assert "authorization" not in names
    _assert_secret_silent(_joined_output(caplog, capsys) + (result.detail or ""))


def test_load_remote_public_dict_redacts_cookie_and_key(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAKAZO_SESSION_COOKIE", _COOKIE)
    monkeypatch.setenv("RAKAZO_API_KEY", _API_KEY)
    with caplog.at_level(logging.DEBUG):
        spec = remotes_core.load_remote("rakazo", _cfg())
        pub = spec.public_dict()
    assert spec.cookie == _COOKIE
    assert spec.api_key == _API_KEY
    assert pub["cookie_set"] is True
    assert pub["api_key_set"] is True
    assert pub["session_cookie_env"] == "RAKAZO_SESSION_COOKIE"
    assert pub["api_key_env"] == "RAKAZO_API_KEY"
    assert "cookie" not in pub
    assert "api_key" not in pub
    dumped = json.dumps(pub)
    _assert_secret_silent(dumped)
    _assert_secret_silent(_joined_output(caplog, capsys))


def test_get_secret_reads_env_and_does_not_log(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("RAKAZO_SESSION_COOKIE", _COOKIE)
    with caplog.at_level(logging.DEBUG):
        value = remotes_core.get_secret("RAKAZO_SESSION_COOKIE")
    assert value == _COOKIE
    assert remotes_core.get_secret("") == ""
    assert remotes_core.get_secret("  ") == ""
    _assert_secret_silent(_joined_output(caplog, capsys))

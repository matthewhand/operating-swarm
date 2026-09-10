"""Issue #152 — POST /v1/chat/completions model=gawd must not HTTP 500 EOFError.

Matrix pass-2 CODE seat on gawd returned 500 EOFError. Reproduction is the
live (non-SWARM_TEST_MODE) path: closed stdin used to call input(). Tests mock
the LLM client and assert CSRF or Bearer POST returns HTTP 200 with a
non-empty assistant reply (or an honest non-500 body).
"""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from django.contrib.auth.models import User
from django.test import Client

ISSUE152_BEARER = "issue152-test-bearer-not-a-secret"


def _boom_input(*_a, **_k):
    raise EOFError("EOF when reading a line")


@pytest.fixture(autouse=True)
def _live_gawd_path(monkeypatch):
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.setattr("builtins.input", _boom_input)
    monkeypatch.setattr(
        "swarm.blueprints.gawd.blueprint_gawd.GAWDBlueprint._stdin_is_interactive",
        staticmethod(lambda: False),
    )
    from django.apps import apps

    monkeypatch.setattr(apps.get_app_config("swarm"), "config", {}, raising=False)


def _assistant_text(response) -> str:
    payload = response.json()
    return (payload["choices"][0]["message"]["content"] or "").strip()


def _post(
    client: Client,
    *,
    bearer: str | None = None,
    csrf: str | None = None,
    referer: str | None = None,
):
    extra: dict = {}
    if bearer:
        extra["HTTP_AUTHORIZATION"] = f"Bearer {bearer}"
    if csrf:
        extra["HTTP_X_CSRFTOKEN"] = csrf
    if referer:
        extra["HTTP_REFERER"] = referer
        extra["HTTP_ORIGIN"] = referer.rstrip("/")
    return client.post(
        "/v1/chat/completions",
        data=json.dumps(
            {
                "model": "gawd",
                "messages": [{"role": "user", "content": "ping"}],
            }
        ),
        content_type="application/json",
        **extra,
    )


def _assert_gawd_ok(response):
    assert response.status_code != 500, (
        f"gawd must not 500 (EOFError leak): {response.content[:300]!r}"
    )
    assert response.status_code == 200, response.content[:300]
    payload = response.json()
    assert "EOFError" not in json.dumps(payload)
    text = _assistant_text(response)
    assert text, "empty assistant reply"


@pytest.mark.django_db
def test_gawd_tiny_prompt_returns_200_not_eoferror_500(client):
    """Live path + closed stdin (input() would EOFError) → HTTP 200 reply."""
    response = _post(client)
    _assert_gawd_ok(response)
    assert "ping" in _assistant_text(response)


@pytest.mark.django_db
def test_gawd_bearer_tiny_prompt_returns_200(settings):
    settings.ENABLE_API_AUTH = True
    settings.SWARM_API_KEY = ISSUE152_BEARER
    settings.SWARM_API_KEYS = [ISSUE152_BEARER]
    client = Client(enforce_csrf_checks=True)
    response = _post(client, bearer=ISSUE152_BEARER)
    _assert_gawd_ok(response)


@pytest.mark.django_db
def test_gawd_csrf_session_tiny_prompt_returns_200(settings):
    settings.ENABLE_API_AUTH = True
    settings.SWARM_API_KEY = ISSUE152_BEARER
    settings.SWARM_API_KEYS = [ISSUE152_BEARER]
    client = Client(enforce_csrf_checks=True)
    User.objects.create_user(username="issue152-session", password="issue152-pass")
    assert client.login(username="issue152-session", password="issue152-pass")
    login_page = client.get("/login/")
    assert login_page.status_code == 200
    token = client.cookies.get("csrftoken")
    assert token is not None
    response = _post(
        client,
        csrf=token.value,
        referer="http://testserver/",
    )
    _assert_gawd_ok(response)


def _install_coordinator_on_discovered_instance(monkeypatch, coordinator):
    """Discovery may load a different class object than a direct import.

    Patch the view helper so the live HTTP instance gets the mocked agent.
    """
    from swarm.views.chat_views import get_blueprint_instance as real_get

    async def _get(*args, **kwargs):
        inst = await real_get(*args, **kwargs)
        inst.coordinator = coordinator
        return inst

    monkeypatch.setattr("swarm.views.chat_views.get_blueprint_instance", _get)


@pytest.mark.django_db
def test_gawd_mocked_llm_eoferror_is_honest_not_500(client, monkeypatch):
    async def _eof(*_a, **_k):
        raise EOFError("incomplete stream")

    monkeypatch.setitem(
        sys.modules,
        "agents",
        SimpleNamespace(Runner=SimpleNamespace(run=_eof)),
    )
    _install_coordinator_on_discovered_instance(monkeypatch, object())
    response = _post(client)
    _assert_gawd_ok(response)
    text = _assistant_text(response)
    assert "could not finish reading the model stream" in text


@pytest.mark.django_db
def test_gawd_mocked_llm_reply_is_returned(client, monkeypatch):
    fake_run = AsyncMock(
        return_value=SimpleNamespace(final_output="mocked-gawd:ok", complete=True)
    )
    monkeypatch.setitem(
        sys.modules,
        "agents",
        SimpleNamespace(Runner=SimpleNamespace(run=fake_run)),
    )
    _install_coordinator_on_discovered_instance(monkeypatch, object())
    response = _post(client)
    _assert_gawd_ok(response)
    assert _assistant_text(response) == "mocked-gawd:ok"

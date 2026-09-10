"""Issue #136 — authenticated kind-chat matrix (CLI / API / Blueprint / Team).

Proves legitimate clients can complete a turn on ``/v1/chat/completions``:

* Bearer REST is CSRF-exempt (no cookie cycle).
* Session cookie + CSRF token cycle is accepted.
* Guest / anonymous stays denied when API auth is on (honest FAIL).
* Each claimed kind returns a streamed or final reply (cheap local backends;
  no paid providers). Missing models / unconfigured CLIs are named errors,
  not garbage-as-success.

See ``docs/qa/ISSUE-136-kind-chat-e2e.md``.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest
from django.contrib.auth.models import User
from django.test import Client

from swarm.core.agent_kind import API_AGENT_BLUEPRINT_ID, API_AGENT_RAIL_ID

PY = sys.executable
ISSUE136_BEARER = "issue136-test-bearer-not-a-secret"


def _echo_cli(prefix: str) -> dict:
    return {
        "cmd": [
            PY,
            "-c",
            f"import sys; print('{prefix}:' + sys.argv[1])",
            "{prompt}",
        ]
    }


@pytest.fixture
def kind_env(monkeypatch, settings):
    """Hermetic cheap backends + API auth on (Bearer required unless session)."""
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-dummy-test-mode")
    from django.apps import apps

    cfg = {"cli_agents": {"echo": _echo_cli("CLI-ECHO")}}
    monkeypatch.setattr(apps.get_app_config("swarm"), "config", cfg, raising=False)
    settings.ENABLE_API_AUTH = True
    settings.SWARM_API_KEY = ISSUE136_BEARER
    settings.SWARM_API_KEYS = [ISSUE136_BEARER]
    return cfg


def _csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


def _prime_csrf(client: Client) -> str:
    client.get("/login/")
    token = client.cookies.get("csrftoken")
    assert token is not None, "GET /login/ must set csrftoken for the session cycle"
    return token.value


def _post(
    client: Client,
    model: str,
    content: str,
    *,
    stream: bool = False,
    params: dict | None = None,
    bearer: str | None = None,
    csrf: str | None = None,
    referer: str | None = None,
):
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "stream": stream,
    }
    if params is not None:
        body["params"] = params
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
        data=json.dumps(body),
        content_type="application/json",
        **extra,
    )


def _assistant_text(response) -> str:
    payload = response.json()
    return (payload["choices"][0]["message"]["content"] or "").strip()


def _sse_body(response) -> str:
    stream = getattr(response, "streaming_content", None)
    if stream is None:
        return response.content.decode("utf-8", errors="replace")
    if hasattr(stream, "__aiter__"):

        async def _collect():
            return b"".join([chunk async for chunk in stream])

        return asyncio.run(_collect()).decode("utf-8", errors="replace")
    return b"".join(stream).decode("utf-8", errors="replace")


@pytest.mark.django_db
def test_guest_without_credentials_is_denied(kind_env):
    """Guest/anon remains FAIL when the product requires auth — do not weaken."""
    client = _csrf_client()
    response = _post(client, "support", "ping")
    assert response.status_code == 403
    detail = response.json().get("detail") or response.content.decode()
    assert "CSRF" not in str(detail)
    assert "Authentication credentials were not provided" in str(detail)


@pytest.mark.django_db
def test_session_without_csrf_is_denied(kind_env):
    """Login ≠ CSRF bypass (existing hardening; LAN preview hits this too)."""
    client = _csrf_client()
    User.objects.create_user(username="issue136-session", password="issue136-pass")
    assert client.login(username="issue136-session", password="issue136-pass")
    response = _post(client, "support", "ping")
    assert response.status_code == 403
    assert b"CSRF" in response.content


@pytest.mark.django_db
def test_login_and_accounts_login_prime_csrftoken(kind_env):
    """Live look-only: GET /login/ and /accounts/login/ set csrftoken."""
    client = _csrf_client()
    for path in ("/login/", "/accounts/login/"):
        other = _csrf_client()
        response = other.get(path)
        assert response.status_code == 200, path
        assert other.cookies.get("csrftoken") is not None, path
    # Landing GET / may be SPA or Django; cookie priming is not required there.
    client.get("/")


@pytest.mark.django_db
def test_session_csrf_cycle_completes_a_turn(kind_env):
    """SPA path: credentials cookie jar + X-CSRFToken from csrftoken + Referer."""
    client = _csrf_client()
    User.objects.create_user(username="issue136-csrf", password="issue136-pass")
    assert client.login(username="issue136-csrf", password="issue136-pass")
    csrf = _prime_csrf(client)
    response = _post(
        client,
        "support",
        "create a team",
        csrf=csrf,
        referer="http://testserver/",
    )
    assert response.status_code == 200, response.content[:400]
    body = _assistant_text(response)
    assert body
    assert "unavailable" not in body.lower()
    assert "Internal server error" not in body


@pytest.mark.django_db
def test_bearer_without_csrf_cookie_completes_a_turn(kind_env):
    """AUTH.md REST path: valid Bearer, no cookie jar — must not be CSRF 403."""
    client = _csrf_client()
    assert client.cookies.get("csrftoken") is None
    assert client.cookies.get("sessionid") is None
    response = _post(
        client,
        "support",
        "create a team",
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, response.content[:400]
    assert b"CSRF" not in response.content
    assert client.cookies.get("csrftoken") is None
    body = _assistant_text(response)
    assert body
    assert "CSRF" not in body


@pytest.mark.django_db
def test_bearer_plus_session_cookie_does_not_need_csrf(kind_env):
    """Token REST stays CSRF-exempt even when a session cookie is also present."""
    client = _csrf_client()
    User.objects.create_user(username="issue136-both", password="issue136-pass")
    assert client.login(username="issue136-both", password="issue136-pass")
    response = _post(
        client,
        "support",
        "create a team",
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, response.content[:400]
    assert _assistant_text(response)


@pytest.mark.django_db
def test_invalid_bearer_does_not_open_the_api(kind_env):
    """Fake token without cookies is auth failure, not the live 'CSRF cookie not set'."""
    client = _csrf_client()
    response = _post(client, "support", "ping", bearer="not-the-configured-token")
    assert response.status_code in (401, 403)
    detail = str(response.json().get("detail") or response.content)
    assert "CSRF cookie not set" not in detail
    assert "Invalid API Key" in detail or "Authentication credentials" in detail


def test_spa_chat_fetch_sends_credentials_and_csrf_header():
    """Login→session prove at the SPA contract (credentials:include + csrftoken)."""
    root = Path(__file__).resolve().parents[2]
    api = (root / "webui" / "frontend" / "src" / "lib" / "api.ts").read_text(
        encoding="utf-8"
    )
    assert "credentials: 'include'" in api
    assert "X-CSRFToken" in api
    assert "getCookie('csrftoken')" in api
    assert "ensureCsrfCookie" in api
    assert "/login/" in api


@pytest.mark.django_db
@pytest.mark.parametrize(
    "kind,model,content,params,must_include",
    [
        (
            "cli",
            "cli_agent",
            "hello-from-cli",
            {"cli": "echo", "failover": False},
            "CLI-ECHO:",
        ),
        (
            "api",
            API_AGENT_RAIL_ID,
            "hello-from-api",
            None,
            "You said:",
        ),
        (
            "blueprint",
            "support",
            "create a team",
            None,
            "team",
        ),
        (
            "team",
            "software_dev",
            "status",
            {"seat": "cos", "action": "status"},
            "software_dev",
        ),
    ],
    ids=["cli_agent", "api_agent", "support", "software_dev"],
)
def test_kind_turn_bearer_final_reply(
    kind_env, kind, model, content, params, must_include
):
    client = _csrf_client()
    response = _post(
        client,
        model,
        content,
        params=params,
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, (kind, model, response.content[:400])
    payload = response.json()
    assert payload.get("object") == "chat.completion"
    body = _assistant_text(response)
    assert body, f"{kind} ({model}) returned an empty reply"
    assert must_include.lower() in body.lower(), body[:400]
    assert "Internal server error" not in body
    if model == API_AGENT_RAIL_ID:
        # Recipe is chatbot; the requested model id stays on the wire.
        assert payload["model"] == API_AGENT_RAIL_ID
        assert API_AGENT_BLUEPRINT_ID == "chatbot"


@pytest.mark.django_db
def test_kind_turn_software_dev_handoff_as_tool(kind_env):
    """CoS quote → engineer blocked without feasibility (as-tool gate, no LLM)."""
    client = _csrf_client()
    quoted = (
        "## Intent\nProve software_dev as-tool seats.\n"
        "## Success\nCoS quotes; engineer stays gated.\n"
        "## Constraints\nNo paid providers.\n"
        "## Owner\nIssue 136 tests.\n"
        "Fixes #136"
    )
    response = _post(
        client,
        "software_dev",
        f"quote {quoted}",
        params={"seat": "cos", "action": "quote", "issue": quoted},
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, response.content[:400]
    body = _assistant_text(response)
    assert "Intent" in body
    assert "Success" in body

    blocked = _post(
        client,
        "software_dev",
        "implement the success criteria",
        params={"seat": "engineer", "action": "implement"},
        bearer=ISSUE136_BEARER,
    )
    assert blocked.status_code == 200, blocked.content[:400]
    blocked_body = _assistant_text(blocked)
    assert "BLOCKED" in blocked_body or "feasibility" in blocked_body.lower()


@pytest.mark.django_db
def test_kind_turn_streamed_sse(kind_env):
    """One path streams: send → SSE deltas or final + [DONE], no crash."""
    client = _csrf_client()
    response = _post(
        client,
        "support",
        "create a team",
        stream=True,
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, response.content[:400]
    ctype = response.get("Content-Type") or ""
    assert "text/event-stream" in ctype
    body = _sse_body(response)
    assert "data: " in body
    assert "[DONE]" in body
    assert "create a team" in body.lower() or "team" in body.lower()
    assert "Internal server error" not in body


@pytest.mark.django_db
def test_unknown_model_is_honest_not_found(kind_env):
    client = _csrf_client()
    response = _post(
        client,
        "definitely-not-a-blueprint-136",
        "ping",
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 404
    detail = str(response.json().get("detail") or response.content)
    assert "definitely-not-a-blueprint-136" in detail
    assert "was not found" in detail.lower() or "not found" in detail.lower()


@pytest.mark.django_db
def test_cli_unconfigured_is_honest_error(kind_env, monkeypatch):
    from django.apps import apps

    monkeypatch.setattr(
        apps.get_app_config("swarm"), "config", {"cli_agents": {}}, raising=False
    )
    client = _csrf_client()
    response = _post(
        client,
        "cli_agent",
        "hello",
        params={"failover": False},
        bearer=ISSUE136_BEARER,
    )
    assert response.status_code == 200, response.content[:400]
    body = _assistant_text(response)
    assert body
    assert "no cli" in body.lower() or "not configured" in body.lower()
    assert "Internal server error" not in body


def test_chat_completions_url_is_csrf_exempt_for_asgi():
    """Live ASGI must see csrf_exempt on the routed callback (Bearer-no-cookie)."""
    from django.urls import resolve

    for path in ("/v1/chat/completions", "/v1/chat/completions/"):
        view = resolve(path).func
        assert getattr(view, "csrf_exempt", False) is True, path


@pytest.mark.django_db
def test_models_list_includes_api_agent_rail_id(kind_env):
    """GET /v1/models must advertise api_agent (live host was missing it)."""
    from swarm.views import utils as view_utils

    view_utils._blueprint_meta_cache = None
    client = _csrf_client()
    response = client.get("/v1/models/", HTTP_AUTHORIZATION=f"Bearer {ISSUE136_BEARER}")
    assert response.status_code == 200, response.content[:300]
    ids = {row.get("id") for row in response.json().get("data") or []}
    assert API_AGENT_RAIL_ID in ids
    assert API_AGENT_BLUEPRINT_ID in ids
    assert "cli_agent" in ids
    assert "support" in ids
    assert "software_dev" in ids


def test_checklist_doc_exists_and_names_deviations():
    root = Path(__file__).resolve().parents[2]
    doc = root / "docs" / "qa" / "ISSUE-136-kind-chat-e2e.md"
    text = doc.read_text(encoding="utf-8")
    assert "Fixes #136" in text or "Issue #136" in text
    assert "Guest" in text or "anonymous" in text.lower()
    assert "Bearer" in text
    assert "CSRF" in text
    assert "cli_agent" in text
    assert "api_agent" in text
    assert "support" in text
    assert "software_dev" in text
    assert "Deviation" in text or "deviation" in text

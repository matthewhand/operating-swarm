"""#325: /v1/agents/* mutators share the REST auth + CSRF contract."""
from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.test import Client, override_settings

TOKEN = "agent-router-auth-token-xyz"


@pytest.fixture
def dummy_router(monkeypatch):
    class Dummy:
        def set_params(self, params):
            self.params = params

        def route_message(self, message):
            return "coder"

        async def run(self, messages, stream=False):
            yield {"content": "ok", "agent": "coder"}

    dummy = Dummy()
    monkeypatch.setattr(
        "swarm.views.agent_router_views.get_agent_router_blueprint",
        lambda: dummy,
    )
    return dummy


@pytest.mark.django_db
def test_route_anonymous_denied_when_auth_on(dummy_router):
    client = Client()
    with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN]):
        response = client.post(
            "/v1/agents/route/",
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
    assert response.status_code in (401, 403)


@pytest.mark.django_db
def test_route_session_without_csrf_is_denied(dummy_router):
    User = get_user_model()
    User.objects.create_user(username="agent_csrf", password="x")
    client = Client(enforce_csrf_checks=True)
    assert client.login(username="agent_csrf", password="x")
    with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN]):
        response = client.post(
            "/v1/agents/route/",
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
        )
    assert response.status_code == 403
    assert b"CSRF" in response.content


@pytest.mark.django_db
def test_route_bearer_succeeds_without_csrf(dummy_router):
    client = Client(enforce_csrf_checks=True)
    with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN]):
        response = client.post(
            "/v1/agents/route/",
            data=json.dumps({"message": "hi"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {TOKEN}",
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"


@pytest.mark.django_db
def test_launch_remote_framework_anonymous_denied():
    client = Client()
    with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEY=TOKEN, SWARM_API_KEYS=[TOKEN]):
        response = client.post(
            "/v1/agents/remote-launch/",
            data=b"{}",
            content_type="application/json",
        )
    assert response.status_code in (401, 403)

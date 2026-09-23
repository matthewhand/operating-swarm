"""#905 — GET /v1/diagnostics/ serves the sanitized tech-support bundle.

The view is a thin read-only shell over ``tech_support_dump()`` (#904): it
must never un-mask, never mutate state, and clamp the requested log window.
"""

from __future__ import annotations

import logging

import pytest
from django.urls import resolve, reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db


def _auth_client(client) -> APIClient:
    api = APIClient()
    api.cookies = client.cookies
    return api


def test_urls_resolve():
    assert resolve("/v1/diagnostics/").url_name == "diagnostics"


def test_get_returns_three_sections(client):
    api = APIClient()
    api.cookies = client.cookies
    resp = api.get(reverse("diagnostics"))
    assert resp.status_code == 200
    data = resp.json()
    assert set(data) == {"recent_logs", "config_dump", "server_facts"}
    assert set(data["recent_logs"]) == {"lines", "counts", "unavailable"}
    assert "app_version" in data["server_facts"]
    assert "config_path" in data["config_dump"]


def test_lines_param_is_clamped(client, monkeypatch):
    from swarm.core import log_capture

    fake = log_capture.LogCapture()
    lg = logging.getLogger("swarm.test.clamp")
    lg.handlers = [fake]
    lg.propagate = False
    log_capture.LogCapture._installed.append(fake)
    try:
        for i in range(600):
            lg.warning("line-%03d", i)
        api = APIClient()
        api.cookies = client.cookies

        resp = api.get(reverse("diagnostics"), {"lines": "5"})
        assert resp.status_code == 200
        assert len(resp.json()["recent_logs"]["lines"]) <= 5

        resp = api.get(reverse("diagnostics"), {"lines": "99999"})
        assert resp.status_code == 200
        assert len(resp.json()["recent_logs"]["lines"]) <= 500

        resp = api.get(reverse("diagnostics"), {"lines": "-3"})
        assert resp.status_code == 200
    finally:
        log_capture.LogCapture._installed.remove(fake)
        lg.handlers = []
        lg.propagate = True


def test_secrets_stay_masked_end_to_end(client, monkeypatch):
    """The masking rule (#904) survives the HTTP hop."""
    import swarm.core.mcp_plugins as mcp_plugins

    monkeypatch.setattr(
        mcp_plugins,
        "swarm_config",
        lambda: {"providers": {"x": {"api_key": "sk-ant-supersecret-000"}}},
        raising=False,
    )
    api = APIClient()
    api.cookies = client.cookies
    body = api.get(reverse("diagnostics")).content.decode()
    assert "supersecret" not in body


def test_unauthenticated_is_rejected(client):
    """With API auth enabled, an anonymous request must not read diagnostics."""
    from django.test import override_settings

    with override_settings(ENABLE_API_AUTH=True, SWARM_API_KEYS=[]):
        api = APIClient()
        resp = api.get(reverse("diagnostics"))
        assert resp.status_code in (401, 403)


def test_in_openapi_schema(client):
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    op = schema["paths"].get("/v1/diagnostics/", {}).get("get")
    assert op is not None
    assert op["operationId"] == "v1_diagnostics"

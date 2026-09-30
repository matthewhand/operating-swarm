"""#1358 — API tests for the TrueForge navbar catalog endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    client = APIClient()
    from django.conf import settings

    if getattr(settings, "ENABLE_API_AUTH", False) and getattr(settings, "SWARM_API_KEY", None):
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.SWARM_API_KEY}")
    return client


def _catalog(**overrides):
    payload = {
        "object": "trueforge.catalog",
        "remote": "trueforge",
        "kind": "trueforge",
        "ok": True,
        "detail": "TrueForge listed 1 agent(s)",
        "http_status": 200,
        "rows_are": "agents",
        "resume_key": "session_id",
        "agents": [{"id": "agent-1", "label": "orchestrator", "name": "orchestrator"}],
        "sessions": [{"id": "sess-9", "title": "refactor the parser", "agent": "orchestrator"}],
    }
    payload.update(overrides)
    return payload


@patch("swarm.views.remotes_api.remotes_core.trueforge_catalog")
def test_trueforge_catalog_get(mock_catalog, api_client):
    mock_catalog.return_value = _catalog()
    resp = api_client.get("/v1/remotes/trueforge/trueforge/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["object"] == "trueforge.catalog"
    assert body["kind"] == "trueforge"
    assert body["ok"] is True
    assert [row["id"] for row in body["agents"]] == ["agent-1"]
    assert [row["id"] for row in body["sessions"]] == ["sess-9"]
    mock_catalog.assert_called_once_with("trueforge")


@patch("swarm.views.remotes_api.remotes_core.trueforge_catalog")
def test_trueforge_catalog_down_is_200_empty(mock_catalog, api_client):
    """A down endpoint is an honest empty catalog, not an error status."""
    mock_catalog.return_value = _catalog(
        ok=False,
        detail="TrueForge list failed (http 503)",
        http_status=503,
        agents=[],
        sessions=[],
    )
    resp = api_client.get("/v1/remotes/trueforge/trueforge/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["agents"] == []
    assert body["sessions"] == []


@patch("swarm.views.remotes_api.remotes_core.trueforge_catalog")
def test_trueforge_catalog_refuses_foreign_remote(mock_catalog, api_client):
    mock_catalog.return_value = _catalog(
        remote="hermes",
        ok=False,
        detail="'hermes' is not a TrueForge remote — the TrueForge pickers never fall back to another provider.",
        error="not_trueforge",
        agents=[],
        sessions=[],
    )
    resp = api_client.get("/v1/remotes/hermes/trueforge/")
    assert resp.status_code == 400
    assert "not a TrueForge remote" in resp.json()["error"]


def test_trueforge_catalog_unknown_remote_404(api_client):
    resp = api_client.get("/v1/remotes/nonexistent_xyz/trueforge/")
    assert resp.status_code == 404

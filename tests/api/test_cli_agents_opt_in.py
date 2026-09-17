"""GET /v1/cli-agents/ — opt-in configured list + PATH discovery (REQ-157)."""

from __future__ import annotations

import pytest
from django.apps import apps

from swarm.core import cli_catalog

FAKE_CLIS = ("echo", "fake", "dummy", "mock", "testcli", "placeholder")


@pytest.mark.django_db
def test_cli_agents_endpoint_empty_configured_with_path_suggestions(client, monkeypatch):
    monkeypatch.setattr(cli_catalog.shutil, "which", lambda exe, path=None: "/bin/grok" if exe == "grok" else None)
    app = apps.get_app_config("swarm")
    orig = getattr(app, "config", {})
    app.config = {"cli_agents": {}}
    try:
        resp = client.get("/v1/cli-agents/")
    finally:
        app.config = orig
    assert resp.status_code == 200
    data = resp.json()
    assert data["configured"] == []
    assert data["discovered"] == ["grok"]
    assert data["installed"] == ["grok"]
    assert {row["id"] for row in data["rail"]} == {"cli_agent"}
    assert data["modes"]["cli"] is True
    assert data["modes"]["api"] is False
    assert "grok" in data["suggestions"]
    assert data["suggestions"]["grok"]["cmd"][0] == "grok"
    assert "sk-" not in str(data)
    assert ":8001" not in str(data)
    assert "auth_check" not in str(data.get("suggestions", {}))


@pytest.mark.django_db
def test_cli_agents_endpoint_configured_excludes_from_suggestions(client, monkeypatch):
    monkeypatch.setattr(cli_catalog.shutil, "which", lambda exe, path=None: "/bin/" + exe)
    app = apps.get_app_config("swarm")
    orig = getattr(app, "config", {})
    app.config = {"cli_agents": {"claude": {"cmd": ["claude", "-p", "{prompt}"]}}}
    try:
        resp = client.get("/v1/cli-agents/")
    finally:
        app.config = orig
    data = resp.json()
    assert data["configured"] == ["claude"]
    assert "claude" not in data["suggestions"]
    assert "grok" in data["suggestions"]


@pytest.mark.django_db
def test_cli_agents_endpoint_discovered_excludes_fake_and_absent(client, monkeypatch):
    """Issue #147: GET /v1/cli-agents/ start set is PATH-discovered, no fake CLIs."""
    monkeypatch.setattr(
        cli_catalog.shutil, "which", lambda exe, path=None: "/bin/grok" if exe == "grok" else None
    )
    app = apps.get_app_config("swarm")
    orig = getattr(app, "config", {})
    app.config = {"cli_agents": {}}
    try:
        resp = client.get("/v1/cli-agents/")
    finally:
        app.config = orig
    assert resp.status_code == 200
    data = resp.json()
    assert data["discovered"] == ["grok"]
    assert data["installed"] == ["grok"]
    for fake in FAKE_CLIS:
        assert fake not in data["discovered"]
        assert fake not in data.get("installed", [])
        assert fake not in (data.get("suggestions") or {})
    assert "pi" not in data["discovered"]
    assert "sk-" not in str(data)
    assert ":8001" not in str(data)

"""#1185 — /team_rosters.json must serve the roster registry, not a stale static demo file.

The SPA's first fetch candidate is /team_rosters.json. The view served
webui/frontend/public/team_rosters.json (five demo fixtures) whenever it
existed, so rosters created via POST /v1/team-rosters/ or the Teams designer
never reached the rail: a static file shadowed the live registry. The demo
fixtures are a fallback for an empty registry, not the source of truth.
"""

from __future__ import annotations

import json

import pytest
from django.test import Client

from swarm.core import team_rosters as rosters_core


@pytest.fixture
def client() -> Client:
    return Client()


def _empty_registry(monkeypatch):
    monkeypatch.setattr(rosters_core, "load_team_rosters", lambda: {})


def test_registry_rosters_are_served(client, monkeypatch):
    registry = {
        "dev-mixed": {
            "id": "dev-mixed",
            "name": "Dev Mixed",
            "members": [
                {"id": "api-demo-litellm", "name": "API Demo", "kind": "api",
                 "role": "chief_of_staff", "source": "blueprint:api-demo-litellm"},
                {"id": "agy", "name": "CLI Demo (agy)", "kind": "cli",
                 "role": "engineer", "source": "cli:agy"},
            ],
            "wires": {"handoff": True, "as_tool": True},
        },
    }
    monkeypatch.setattr(rosters_core, "load_team_rosters", lambda: registry)

    response = client.get("/team_rosters.json")
    assert response.status_code == 200
    payload = json.loads(response.content)
    ids = [r["id"] for r in payload["data"]]
    assert "dev-mixed" in ids
    # The static demo fixture must NOT shadow the registry.
    assert "demo-team" not in ids


def test_empty_registry_falls_back_to_demo_stub(client, monkeypatch):
    _empty_registry(monkeypatch)
    response = client.get("/team_rosters.json")
    assert response.status_code == 200
    payload = json.loads(response.content)
    assert payload["data"], "demo fallback keeps the sidepane populated"



def test_nonempty_registry_excludes_static_demo_fixtures(client, monkeypatch):
    """A non-empty registry serves registry entries ONLY — demo fixtures are a
    fallback for an empty registry, not an appendable supplement."""
    static_demo = {"object": "list", "data": [
        {"id": "demo-team", "name": "Demo Team", "members": []},
        {"id": "demo-bridge", "name": "Demo Bridge", "members": []},
    ]}
    monkeypatch.setattr(
        "swarm.views.web_views._static_team_rosters_payload", lambda: static_demo
    )
    registry = {
        "dev-sequence": {"id": "dev-sequence", "name": "Dev Sequence",
                         "members": [{"id": "ba", "name": "BA", "kind": "api"}]},
    }
    monkeypatch.setattr("swarm.views.web_views.load_team_rosters_safe", lambda: registry)

    payload = json.loads(client.get("/team_rosters.json").content)
    ids = [r["id"] for r in payload["data"]]
    assert ids == ["dev-sequence"]

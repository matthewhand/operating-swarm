"""API tests for /v1/team-rosters/<id>/topology/ — OpenRig nodes + wires (#1222).

Hermetic: the roster store is isolated to a tmp config dir, no network, no
secrets.
"""

import pytest
from rest_framework.test import APIClient

from swarm.core.rig_topology import build_rig_topology
from swarm.core.team_rosters import reset_team_rosters


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture(autouse=True)
def _isolate_rosters(tmp_path, monkeypatch):
    from swarm.core import team_rosters as store

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(store, "ensure_swarm_directories_exist", lambda: None)
    reset_team_rosters()
    yield
    reset_team_rosters()


def _create(api_client, body):
    response = api_client.post("/v1/team-rosters/", body, format="json")
    assert response.status_code == 201, response.json()
    return response.json()


def test_topology_maps_tools_to_openrig_edges(api_client):
    _create(
        api_client,
        {
            "name": "Build Rig",
            "members": [
                {"id": "lead", "kind": "api", "role": "default", "source": "blueprint:lead"},
                {"id": "impl", "kind": "api", "role": "default", "source": "blueprint:impl"},
                {"id": "qa", "kind": "cli", "role": "default", "source": "cli:qa"},
            ],
            "tools": [
                {"type": "handoff", "from": "lead", "to": "impl"},
                {"type": "handoff", "from": "impl", "to": "qa"},
                {"type": "as_tool", "agent": "qa"},
            ],
            "chief_of_staff_id": "lead",
        },
    )

    response = api_client.get("/v1/team-rosters/build-rig/topology/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "rig_topology"
    assert body["id"] == "build-rig"
    assert body["lead_id"] == "lead"

    nodes = {node["id"]: node for node in body["nodes"]}
    assert set(nodes) == {"lead", "impl", "qa"}
    assert nodes["lead"]["lead"] is True
    assert nodes["impl"]["lead"] is False
    assert nodes["qa"]["kind"] == "cli"
    assert nodes["qa"]["role"] == "default"

    edges = {(edge["from"], edge["to"]): edge for edge in body["edges"]}
    assert edges[("lead", "impl")]["kind"] == "delegates_to"
    assert edges[("lead", "impl")]["channel"] == "handoff"
    assert edges[("impl", "qa")]["kind"] == "delegates_to"
    assert edges[("lead", "qa")]["kind"] == "collaborates_with"
    assert edges[("lead", "qa")]["channel"] == "as_tool"


def test_topology_falls_back_to_legacy_wires_when_no_tools(api_client):
    _create(
        api_client,
        {
            "name": "Legacy Rig",
            "members": [
                {"id": "lead", "kind": "api", "role": "default"},
                {"id": "helper", "kind": "api", "role": "default"},
            ],
            "wires": {"handoff": True, "as_tool": False},
        },
    )
    response = api_client.get("/v1/team-rosters/legacy-rig/topology/")
    assert response.status_code == 200
    body = response.json()
    kinds = sorted(edge["kind"] for edge in body["edges"])
    assert kinds == ["delegates_to"]
    assert body["edges"][0]["from"] == "lead"
    assert body["edges"][0]["to"] == "helper"


def test_topology_unknown_roster_is_404(api_client):
    response = api_client.get("/v1/team-rosters/does-not-exist/topology/")
    assert response.status_code == 404


def test_build_rig_topology_never_invents_edges():
    payload = build_rig_topology(
        {
            "id": "solo",
            "name": "Solo",
            "members": [{"id": "only", "kind": "api", "role": "default"}],
            "tools": [{"type": "as_tool", "agent": "ghost"}],
        }
    )
    assert payload["nodes"][0]["lead"] is True
    assert payload["edges"] == []

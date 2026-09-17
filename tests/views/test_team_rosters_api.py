"""API tests for /v1/team-rosters/ (composition, not LLM aliases)."""

import pytest
from rest_framework.test import APIClient

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


def test_create_and_list_nested_roster_with_cos(api_client):
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Office",
            "members": [
                {"id": "cos", "kind": "api", "role": "cos", "source": "blueprint:cos"},
                {"id": "research", "kind": "team", "team_id": "research", "role": "default"},
                {"id": "w3p1", "kind": "herdr", "role": "default"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["object"] == "team_roster"
    assert body["id"] == "office"
    roles = {m["id"]: m for m in body["members"]}
    assert roles["cos"]["role"] == "chief_of_staff"
    assert roles["research"]["kind"] == "team"
    assert roles["research"]["team_id"] == "research"
    assert roles["w3p1"]["kind"] == "herdr"

    listed = api_client.get("/v1/team-rosters/")
    assert listed.status_code == 200
    assert listed.json()["object"] == "list"
    assert listed.json()["data"][0]["id"] == "office"


def test_does_not_write_teams_json_aliases(api_client, monkeypatch):
    """Roster POST must not touch the LLM-alias registry."""
    called = {"register": False}

    def boom(*_a, **_k):
        called["register"] = True
        raise AssertionError("must not register a dynamic team alias")

    monkeypatch.setattr("swarm.views.utils.register_dynamic_team", boom)
    response = api_client.post(
        "/v1/team-rosters/",
        {"name": "solo", "members": [{"id": "a", "kind": "api", "role": "default"}]},
        format="json",
    )
    assert response.status_code == 201
    assert called["register"] is False


def test_create_roster_with_blueprint_id_attaches_personas(api_client):
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Dev squad",
            "blueprint_id": "software_dev",
            "members": [{"id": "cos", "kind": "api", "role": "cos"}],
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["blueprint_id"] == "software_dev"
    assert body["persona_count"] == 3
    assert [p["name"] for p in body["personas"]] == [
        "engineer",
        "skeptic",
        "coding-requirements-gate",
    ]


def test_create_roster_with_cos_instructions_and_reload(api_client):
    members = [
        {"id": "jeeves", "kind": "api", "role": "default", "source": "blueprint:jeeves"},
        {"id": "grok_agent", "kind": "cli", "role": "default", "source": "cli:grok_agent"},
        {"id": "skeptic", "kind": "api", "role": "skeptic", "source": "blueprint:skeptic"},
    ]
    created = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Research Squad",
            "members": members,
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "prefer grok_agent for revision control",
        },
        format="json",
    )
    assert created.status_code == 201
    body = created.json()
    assert body["chief_of_staff_id"] == "jeeves"
    assert body["chief_of_staff_instructions"] == "prefer grok_agent for revision control"
    assert {m["id"]: m["role"] for m in body["members"]}["jeeves"] == "chief_of_staff"

    loaded = api_client.get("/v1/team-rosters/research-squad/")
    assert loaded.status_code == 200
    again = loaded.json()
    assert again["chief_of_staff_id"] == "jeeves"
    assert again["chief_of_staff_instructions"] == "prefer grok_agent for revision control"

    cleared = api_client.put(
        "/v1/team-rosters/research-squad/",
        {
            "name": "Research Squad",
            "members": members,
            "chief_of_staff_id": None,
            "chief_of_staff_instructions": "",
        },
        format="json",
    )
    assert cleared.status_code == 200
    assert cleared.json()["chief_of_staff_id"] is None
    assert cleared.json()["chief_of_staff_instructions"] == ""


def test_create_roster_rejects_remote_cos(api_client):
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Harness",
            "members": [
                {"id": "hermes", "kind": "remote", "role": "default"},
                {"id": "jeeves", "kind": "api", "role": "default"},
            ],
            "chief_of_staff_id": "hermes",
        },
        format="json",
    )
    assert response.status_code == 400
    assert "API or CLI" in response.json()["error"]


def test_team_agents_palette(api_client, monkeypatch):
    from swarm.views import team_rosters_api as api

    monkeypatch.setattr(
        api,
        "list_team_agents",
        lambda: [
            {
                "id": "jeeves",
                "name": "jeeves",
                "kind": "api",
                "source": "blueprint:jeeves",
                "placeholder": False,
            }
        ],
    )
    response = api_client.get("/v1/team-agents/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "list"
    assert body["data"][0]["id"] == "jeeves"
    assert "api_key" not in str(body).lower()


def test_create_roster_with_remote_members(api_client):
    """PR #318: POST /v1/team-rosters/ accepts Hermes/OMB/Rakazo as kind=remote."""
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Harness",
            "members": [
                {"id": "hermes", "kind": "remote", "role": "default"},
                {"id": "omb", "kind": "remote", "role": "default"},
                {"id": "rakazo", "kind": "remote", "role": "default"},
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["object"] == "team_roster"
    kinds = {m["id"]: m["kind"] for m in body["members"]}
    assert kinds == {"hermes": "remote", "omb": "remote", "rakazo": "remote"}
    listed = api_client.get("/v1/team-rosters/")
    assert listed.status_code == 200
    assert listed.json()["data"][0]["id"] == "harness"


def test_create_showoff_roster_keeps_kind_clear_names(api_client):
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Demo Harness Kinds",
            "members": [
                {"id": "grok-cli", "name": "Grok CLI", "kind": "cli", "role": "default"},
                {
                    "id": "openmousbot-remote",
                    "name": "OpenMousBot Remote",
                    "kind": "remote",
                    "role": "default",
                },
            ],
        },
        format="json",
    )
    assert response.status_code == 201
    names = {m["id"]: m["name"] for m in response.json()["members"]}
    assert names["grok-cli"] == "Grok CLI"
    assert names["openmousbot-remote"] == "OpenMousBot Remote"
    loaded = api_client.get("/v1/team-rosters/demo-harness-kinds/")
    assert loaded.status_code == 200
    again = {m["id"]: m["name"] for m in loaded.json()["members"]}
    assert again == names
    assert "OMB" not in again.values()


def test_create_roster_persists_tools_and_derived_wires(api_client):
    response = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Lab",
            "members": [{"id": "jeeves", "kind": "api", "role": "default"}],
            "tools": [
                {"type": "handoff", "to": "jeeves"},
                {"type": "mcp", "server": "github", "agents": []},
            ],
            "wires": {"handoff": False, "as_tool": True},
        },
        format="json",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["tools"] == [
        {"type": "handoff", "to": "jeeves"},
        {"type": "mcp", "server": "github", "agents": []},
    ]
    assert body["wires"] == {"handoff": True, "as_tool": False}

    locked = api_client.put(
        "/v1/team-rosters/lab/",
        {
            "name": "Lab",
            "members": [{"id": "jeeves", "kind": "api", "role": "default"}],
            "tools": [{"type": "mcp", "server": "github", "agents": ["jeeves"]}],
        },
        format="json",
    )
    assert locked.status_code == 200
    assert locked.json()["tools"] == [{"type": "mcp", "server": "github", "agents": ["jeeves"]}]
    assert locked.json()["wires"] == {"handoff": False, "as_tool": False}

    rejected = api_client.post(
        "/v1/team-rosters/",
        {
            "name": "Nope",
            "tools": [{"type": "mcp", "server": "github", "env": {"TOKEN": "secret"}}],
        },
        format="json",
    )
    assert rejected.status_code == 400
    assert "secret-shaped" in rejected.json()["error"]

"""#1311 — HTTP publish/import, permission denial, and personal default."""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient

from swarm.core.team_rosters import get_roster, reset_team_rosters, upsert_roster
from swarm.views.blueprint_library_views import (
    get_user_blueprint_library,
    save_user_blueprint_library,
)


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(
        "swarm.views.blueprint_library_views.get_user_config_dir_for_swarm",
        lambda: cfg,
    )
    monkeypatch.setattr(
        "swarm.core.team_rosters.get_user_config_dir_for_swarm",
        lambda: cfg,
    )
    monkeypatch.setattr("swarm.core.team_rosters.ensure_swarm_directories_exist", lambda: None)
    reset_team_rosters({})
    save_user_blueprint_library({"installed": ["chatbot"], "custom": []})
    yield cfg
    reset_team_rosters({})


@pytest.fixture
def users(db):  # noqa: ARG001
    User = get_user_model()
    ada = User.objects.create_user("ada", password="not-used")
    bob = User.objects.create_user("bob", password="not-used")
    return ada, bob


@pytest.mark.django_db
def test_personal_scope_default_is_unchanged(isolated, users):
    del isolated
    ada, _bob = users
    client = APIClient()
    client.force_authenticate(user=ada)
    plain = client.get("/v1/library/")
    scoped = client.get("/v1/library/?scope=personal")
    assert plain.status_code == status.HTTP_200_OK
    assert scoped.status_code == status.HTTP_200_OK
    assert plain.json() == scoped.json()
    assert plain.json()["data"][0]["object"] == "library.blueprint"
    assert plain.json()["data"][0]["id"] == "chatbot"


@pytest.mark.django_db
def test_publish_import_and_cross_principal_http(isolated, users):
    del isolated
    ada, bob = users
    client = APIClient()
    anon = client.post(
        "/v1/library/",
        {"action": "publish", "scope": "org", "kind": "plugin", "id": "maps", "name": "Maps"},
        format="json",
    )
    assert anon.status_code == status.HTTP_401_UNAUTHORIZED

    client.force_authenticate(user=ada)
    created = client.post(
        "/v1/library/",
        {
            "action": "publish",
            "scope": "org",
            "kind": "blueprint",
            "id": "helper",
            "name": "Helper",
            "payload": {"description": "shared"},
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    personal = client.post(
        "/v1/library/",
        {"action": "publish", "scope": "personal", "kind": "plugin", "id": "ada-only", "name": "Ada only"},
        format="json",
    )
    assert personal.status_code == status.HTTP_201_CREATED, personal.content

    client.force_authenticate(user=bob)
    listed = client.get("/v1/library/?scope=org")
    assert listed.status_code == status.HTTP_200_OK
    assert [row["item_key"] for row in listed.json()["data"]] == ["helper"]
    denied = client.post(
        "/v1/library/",
        {"action": "import", "id": personal.json()["id"]},
        format="json",
    )
    assert denied.status_code == status.HTTP_403_FORBIDDEN
    unpublish = client.post(
        "/v1/library/",
        {"action": "unpublish", "id": created.json()["id"]},
        format="json",
    )
    assert unpublish.status_code == status.HTTP_403_FORBIDDEN
    imported = client.post(
        "/v1/library/",
        {"action": "import", "id": created.json()["id"]},
        format="json",
    )
    assert imported.status_code == status.HTTP_200_OK, imported.content
    assert imported.json()["imported"] is True
    assert "helper" in get_user_blueprint_library().get("installed", [])
    mine = client.get("/v1/library/?scope=personal")
    ids = [row["id"] for row in mine.json()["data"]]
    assert "ada-only" not in ids
    assert "chatbot" in ids


@pytest.mark.django_db
def test_roster_pack_publish_import_reports_missing(isolated, users):
    del isolated
    ada, bob = users
    upsert_roster(
        {
            "id": "field",
            "name": "Field",
            "members": [
                {
                    "id": "scout",
                    "name": "Scout",
                    "kind": "api",
                    "role": "default",
                    "source": "blueprint:not-on-this-install",
                }
            ],
            "tools": [{"type": "mcp", "server": "notes", "agents": ["scout"]}],
        }
    )
    client = APIClient()
    client.force_authenticate(user=ada)
    published = client.post(
        "/v1/team-rosters/",
        {
            "action": "publish",
            "scope": "org",
            "roster_id": "field",
            "skill_ids": ["field-notes"],
        },
        format="json",
    )
    assert published.status_code == status.HTTP_201_CREATED, published.content
    pack = published.json()["payload"]
    assert pack["members"][0]["kind"] == "api"
    assert "not-on-this-install" in pack["blueprint_ids"]
    assert "notes" in pack["mcp_server_ids"]
    assert pack["skill_ids"] == ["field-notes"]

    from swarm.core.team_rosters import delete_roster

    delete_roster("field")
    client.force_authenticate(user=bob)
    visible = client.get("/v1/team-rosters/?scope=org")
    assert visible.status_code == status.HTTP_200_OK
    assert visible.json()["data"][0]["item_key"] == "field"
    imported = client.post(
        "/v1/team-rosters/",
        {"action": "import", "id": published.json()["id"]},
        format="json",
    )
    assert imported.status_code == status.HTTP_200_OK, imported.content
    body = imported.json()
    assert body["imported"] is True
    assert any(row["id"] == "scout" for row in body["needs_configuration"])
    assert any(row["id"] == "notes" and "MCP" in row["reason"] for row in body["needs_configuration"])
    assert any(row["id"] == "field-notes" and "Skill" in row["reason"] for row in body["needs_configuration"])
    roster = get_roster("field")
    assert roster is not None
    assert roster["members"][0]["id"] == "scout"
    assert roster["members"][0]["role"] == "default"


@pytest.fixture(autouse=True)
def isolated_plugins(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))
    from swarm.core.agent_plugin_pack import reset_agent_plugin_pack_cache
    from swarm.core.marketplace_catalog import MarketplaceCatalogError

    def _missing(_plugin_id):
        raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)

    monkeypatch.setattr("swarm.core.agent_plugin_pack.install_marketplace_plugin", _missing)
    reset_agent_plugin_pack_cache()
    yield
    reset_agent_plugin_pack_cache()


@pytest.mark.django_db
def test_team_scope_http_is_isolated_to_that_roster(isolated, users):
    del isolated
    ada, bob = users
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    upsert_roster({"id": "sales", "name": "Sales", "members": []})
    client = APIClient()
    client.force_authenticate(user=ada)
    missing_team = client.post(
        "/v1/library/",
        {"action": "publish", "scope": "team", "kind": "blueprint", "id": "helper", "name": "Helper"},
        format="json",
    )
    assert missing_team.status_code == status.HTTP_400_BAD_REQUEST
    unknown = client.post(
        "/v1/library/",
        {
            "action": "publish",
            "scope": "team",
            "team_id": "no-such-team",
            "kind": "blueprint",
            "id": "helper",
            "name": "Helper",
        },
        format="json",
    )
    assert unknown.status_code == status.HTTP_404_NOT_FOUND
    created = client.post(
        "/v1/library/",
        {
            "action": "publish",
            "scope": "team",
            "team_id": "eng",
            "kind": "blueprint",
            "id": "helper",
            "name": "Helper",
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    client.force_authenticate(user=bob)
    eng = client.get("/v1/library/?scope=team&team_id=eng")
    sales = client.get("/v1/library/?scope=team&team_id=sales")
    assert eng.status_code == status.HTTP_200_OK
    assert sales.status_code == status.HTTP_200_OK
    assert [row["item_key"] for row in eng.json()["data"]] == ["helper"]
    assert sales.json()["data"] == []


@pytest.mark.django_db
def test_team_import_http_rejects_a_bare_id(isolated, users):
    del isolated
    upsert_roster({"id": "rig-a", "name": "Rig A", "members": []})
    ada, bob = users
    client = APIClient()
    client.force_authenticate(user=ada)
    created = client.post(
        "/v1/library/",
        {
            "action": "publish",
            "scope": "team",
            "team_id": "rig-a",
            "kind": "plugin",
            "id": "maps",
            "name": "Maps",
        },
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    client.force_authenticate(user=bob)
    bare = client.post(
        "/v1/library/",
        {"action": "import", "id": created.json()["id"]},
        format="json",
    )
    assert bare.status_code == status.HTTP_403_FORBIDDEN
    imported = client.post(
        "/v1/library/",
        {"action": "import", "id": created.json()["id"], "team_id": "rig-a"},
        format="json",
    )
    assert imported.status_code == status.HTTP_200_OK, imported.content
    assert imported.json()["imported"] is True


@pytest.mark.django_db
def test_create_preset_lands_in_rail_response(isolated, users):
    del isolated
    ada, _bob = users
    from swarm.models.company import Company

    Company.objects.create(
        name="Acme",
        slug="acme",
        model_policy={
            "mode": "allow_all",
            "allowed_models": [],
            "denied_models": [],
            "default_model": "",
        },
    )
    client = APIClient()
    client.force_authenticate(user=ada)
    created = client.post(
        "/v1/library/",
        {"action": "create_preset", "preset_id": "preset-support"},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    seat = created.json()
    assert seat["id"] == "preset-support"
    assert seat["rail"] is True
    assert seat["provider"]
    assert seat["model"]
    assert seat["plugins"] == ["support-tools"]
    assert seat["role"] == "support"
    assert seat["provider"] == "openai"
    assert seat["model"] == "gpt-4o-mini"
    assert seat["plugin_pack"]["ok"] is True
    assert [row["pluginId"] for row in seat["plugin_pack"]["plugins"]] == ["support-tools"]
    custom = get_user_blueprint_library().get("custom") or []
    assert any(row.get("id") == "preset-support" and row.get("rail") is True for row in custom)
    listed = client.get("/v1/blueprints/")
    assert listed.status_code == status.HTTP_200_OK, listed.content
    rail = next(row for row in listed.json()["data"] if row["id"] == "preset-support")
    assert rail["rail"] is True
    assert rail["role"] == "support"
    assert rail["provider"] == "openai"
    assert rail["model"] == "gpt-4o-mini"
    assert rail["plugins"] == ["support-tools"]
    assert rail["required_mcp_servers"] == ["support-tools"]

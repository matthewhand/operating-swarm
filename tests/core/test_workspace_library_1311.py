"""#1311 — scoped publish, import, permission denial, cross-principal isolation."""

from __future__ import annotations

import pytest

from swarm.core.team_rosters import get_roster, reset_team_rosters, upsert_roster
from swarm.core.workspace_library import (
    LibraryError,
    LibraryPermissionError,
    import_item,
    list_items,
    publish,
    resolve_scope,
    share_team,
    unpublish,
)
from swarm.views.blueprint_library_views import get_user_blueprint_library


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
    yield cfg
    reset_team_rosters({})


@pytest.mark.django_db
def test_resolve_scope_defaults_to_personal():
    resolved = resolve_scope(None, principal="user:ada")
    assert resolved["scope"] == "personal"
    assert resolved["team_id"] == ""


@pytest.mark.django_db
def test_personal_publish_is_hidden_from_other_principal(isolated):
    del isolated
    own = publish(
        kind="blueprint",
        item_key="ada-recipe",
        principal="user:ada",
        scope="personal",
        title="Ada recipe",
        payload={"description": "private"},
    )
    ada = list_items(scope="personal", principal="user:ada")
    bob = list_items(scope="personal", principal="user:bob")
    assert [row["item_key"] for row in ada] == ["ada-recipe"]
    assert bob == []
    with pytest.raises(LibraryPermissionError):
        import_item(item_id=own["id"], principal="user:bob")
    with pytest.raises(LibraryPermissionError):
        unpublish(item_id=own["id"], principal="user:bob")


@pytest.mark.django_db
def test_org_publish_is_visible_and_importable(isolated):
    assert isolated.is_dir()
    published = publish(
        kind="blueprint",
        item_key="shared-helper",
        principal="user:ada",
        scope="org",
        title="Shared helper",
        payload={"description": "org recipe"},
    )
    visible = list_items(scope="org", principal="user:bob")
    assert [row["id"] for row in visible] == [published["id"]]
    imported = import_item(item_id=published["id"], principal="user:bob")
    assert imported["imported"] is True
    assert imported["item"]["scope"] == "personal"
    assert imported["item"]["owner_principal"] == "user:bob"
    assert "shared-helper" in get_user_blueprint_library().get("installed", [])
    bob_personal = list_items(scope="personal", principal="user:bob")
    assert any(row["item_key"] == "shared-helper" for row in bob_personal)
    assert list_items(scope="personal", principal="user:ada") == []


@pytest.mark.django_db
def test_team_import_requires_the_published_team_id(isolated):
    del isolated
    upsert_roster({"id": "rig-a", "name": "Rig A", "members": []})
    published = publish(
        kind="plugin",
        item_key="maps",
        principal="user:ada",
        scope="team",
        team_id="rig-a",
        title="Maps",
        payload={"description": "team plugin"},
    )
    with pytest.raises(LibraryPermissionError):
        import_item(item_id=published["id"], principal="user:bob")
    with pytest.raises(LibraryPermissionError):
        import_item(item_id=published["id"], principal="user:bob", team_id="rig-b")
    imported = import_item(item_id=published["id"], principal="user:bob", team_id="rig-a")
    assert imported["imported"] is True
    assert imported["item"]["scope"] == "personal"
    assert imported["item"]["owner_principal"] == "user:bob"


@pytest.mark.django_db
def test_missing_principal_is_denied():
    with pytest.raises(LibraryPermissionError) as caught:
        publish(kind="plugin", item_key="maps", principal=None, scope="org", payload={})
    assert caught.value.status == 401


@pytest.mark.django_db
def test_share_team_pack_imports_members_and_reports_missing(isolated):
    del isolated
    upsert_roster(
        {
            "id": "ops",
            "name": "Ops",
            "members": [
                {
                    "id": "lead",
                    "name": "Lead",
                    "kind": "api",
                    "role": "default",
                    "source": "blueprint:missing_recipe",
                }
            ],
            "tools": [{"type": "mcp", "server": "files", "agents": []}],
        }
    )
    packed = share_team(
        roster_id="ops",
        principal="user:ada",
        scope="org",
        skill_ids=["review-skill"],
        mcp_server_ids=["files"],
    )
    payload = packed["payload"]
    assert payload["object"] == "team_roster_pack"
    assert payload["members"][0]["kind"] == "api"
    assert payload["members"][0]["role"] == "default"
    assert payload["blueprint_ids"] == ["missing_recipe"]
    assert payload["mcp_server_ids"] == ["files"]
    assert payload["skill_ids"] == ["review-skill"]

    from swarm.core.team_rosters import delete_roster

    assert delete_roster("ops") is True
    imported = import_item(item_id=packed["id"], principal="user:bob")
    restored = get_roster("ops")
    assert restored is not None
    assert restored["members"][0]["id"] == "lead"
    assert restored["members"][0]["kind"] == "api"
    reasons = imported["needs_configuration"]
    assert any(row["id"] == "lead" for row in reasons)
    assert any(row["id"] == "files" and "MCP" in row["reason"] for row in reasons)
    assert any(row["id"] == "review-skill" and "Skill" in row["reason"] for row in reasons)


@pytest.mark.django_db
def test_team_scope_requires_a_real_roster_and_stays_isolated(isolated):
    del isolated
    upsert_roster({"id": "eng", "name": "Engineering", "members": []})
    upsert_roster({"id": "sales", "name": "Sales", "members": []})
    with pytest.raises(LibraryError, match="team_id"):
        publish(
            kind="blueprint",
            item_key="helper",
            principal="user:ada",
            scope="team",
            title="Helper",
            payload={},
        )
    with pytest.raises(LibraryError, match="was not found"):
        list_items(scope="team", principal="user:ada", team_id="missing-team")
    published = publish(
        kind="blueprint",
        item_key="helper",
        principal="user:ada",
        scope="team",
        team_id="eng",
        title="Helper",
        payload={"description": "eng only"},
    )
    eng = list_items(scope="team", principal="user:bob", team_id="eng")
    sales = list_items(scope="team", principal="user:bob", team_id="sales")
    assert [row["id"] for row in eng] == [published["id"]]
    assert sales == []


@pytest.mark.django_db
def test_failed_dependency_check_is_not_an_empty_import(isolated, monkeypatch):
    del isolated
    upsert_roster(
        {
            "id": "ops",
            "name": "Ops",
            "members": [
                {
                    "id": "lead",
                    "name": "Lead",
                    "kind": "api",
                    "role": "default",
                    "source": "blueprint:missing_recipe",
                }
            ],
        }
    )
    packed = share_team(roster_id="ops", principal="user:ada", scope="org")

    def _boom(_roster):
        raise RuntimeError("annotate down")

    monkeypatch.setattr("swarm.core.marketplace_catalog.annotate_team_preview", _boom)
    imported = import_item(item_id=packed["id"], principal="user:bob")
    reasons = imported["needs_configuration"]
    assert reasons
    assert any("Dependency check failed" in row["reason"] for row in reasons)


@pytest.mark.django_db
def test_failed_pack_lookup_is_not_reported_as_missing(isolated, monkeypatch):
    """A crashed MCP or skill lookup is a failed check, not 'not installed'."""
    del isolated
    upsert_roster({"id": "ops", "name": "Ops", "members": []})
    packed = share_team(
        roster_id="ops",
        principal="user:ada",
        scope="org",
        mcp_server_ids=["files"],
        skill_ids=["review-skill"],
    )

    def _boom(*_args, **_kwargs):
        raise RuntimeError("lookup down")

    monkeypatch.setattr("swarm.core.mcp_plugins.enabled_mcp_servers", _boom)
    monkeypatch.setattr("swarm.core.skills.discover_skills", _boom)
    imported = import_item(item_id=packed["id"], principal="user:bob")
    reasons = imported["needs_configuration"]
    assert any(row["id"] == "mcp" and "Dependency check failed" in row["reason"] for row in reasons)
    assert any(row["id"] == "skills" and "Dependency check failed" in row["reason"] for row in reasons)
    assert not any("MCP server not configured" in row["reason"] for row in reasons)
    assert not any("Skill not installed" in row["reason"] for row in reasons)

"""#1311 — REST contract for the org-shared bot library."""

from __future__ import annotations

import pytest
from django.urls import resolve
from rest_framework import status
from rest_framework.test import APIClient

from swarm.core import org_bot_library as store
from swarm.core.org_bot_library import (
    PRESET_SUPPORT_ID,
    reset_org_bot_library,
)
from swarm.core import team_rosters as roster_store
from swarm.core.team_rosters import get_roster, reset_team_rosters, upsert_roster


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(store, "ensure_swarm_directories_exist", lambda: None)
    # Share writes team_rosters.json through that module's own path helper.
    monkeypatch.setattr(roster_store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(roster_store, "ensure_swarm_directories_exist", lambda: None)
    monkeypatch.setenv(store.ENV_LIBRARY_PATH, str(cfg / "org_bot_library.json"))
    reset_org_bot_library()
    reset_team_rosters()
    yield
    reset_org_bot_library()
    reset_team_rosters()


@pytest.fixture
def client():
    return APIClient()


def test_org_library_routes_resolve():
    assert resolve("/v1/org-library/").url_name == "org-library-api"
    assert resolve("/v1/org-library/preset-support/").url_name == "org-library-detail"
    assert resolve("/v1/org-library/preset-support/share/").url_name == "org-library-share"


def test_list_includes_preset_bots(client):
    response = client.get("/v1/org-library/")
    assert response.status_code == status.HTTP_200_OK
    body = response.json()
    assert body["object"] == "list"
    ids = {row["id"] for row in body["data"]}
    assert PRESET_SUPPORT_ID in ids
    support = next(row for row in body["data"] if row["id"] == PRESET_SUPPORT_ID)
    assert support["object"] == "org_library.bot"
    assert support["preset"] is True
    assert support["visibility"] == "org"


def test_publish_get_and_delete_user_bot(client):
    created = client.post(
        "/v1/org-library/",
        {"id": "talent-scout", "name": "Talent Scout", "description": "Screen candidates."},
        format="json",
    )
    assert created.status_code == status.HTTP_201_CREATED, created.content
    assert created.json()["id"] == "talent-scout"
    assert created.json()["visibility"] == "org"

    fetched = client.get("/v1/org-library/talent-scout/")
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["name"] == "Talent Scout"

    listed = {row["id"] for row in client.get("/v1/org-library/").json()["data"]}
    assert "talent-scout" in listed

    deleted = client.delete("/v1/org-library/talent-scout/")
    assert deleted.status_code == status.HTTP_204_NO_CONTENT
    assert client.get("/v1/org-library/talent-scout/").status_code == status.HTTP_404_NOT_FOUND


def test_cannot_delete_or_overwrite_preset(client):
    assert client.delete(f"/v1/org-library/{PRESET_SUPPORT_ID}/").status_code == status.HTTP_409_CONFLICT
    hijack = client.post(
        "/v1/org-library/",
        {"id": PRESET_SUPPORT_ID, "name": "Hijack"},
        format="json",
    )
    assert hijack.status_code == status.HTTP_409_CONFLICT


def test_publish_rejects_secrets(client):
    response = client.post(
        "/v1/org-library/",
        {"id": "leaky", "name": "Leaky", "instructions": "use sk-abcdefghijklmnopqrstuvwxyz"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "secret" in response.json()["error"].lower()


def test_whole_team_share_via_api(client):
    upsert_roster(
        {
            "id": "eng",
            "name": "Engineering",
            "members": [{"id": "pat", "kind": "api", "role": "engineer"}],
        }
    )
    client.post(
        "/v1/org-library/",
        {"id": "bug-repro", "name": "Bug Reproduction"},
        format="json",
    )
    shared = client.post(
        "/v1/org-library/bug-repro/share/",
        {"scope": "team", "team_id": "eng"},
        format="json",
    )
    assert shared.status_code == status.HTTP_200_OK, shared.content
    body = shared.json()
    assert body["object"] == "org_library.share"
    assert body["scope"] == "team"
    assert body["team_id"] == "eng"
    assert body["bot"]["visibility"] == "team"
    assert "eng" in body["bot"]["team_ids"]

    roster = get_roster("eng")
    assert "bug-repro" in {row["id"] for row in roster["members"]}

    filtered = client.get("/v1/org-library/?team_id=eng")
    assert "bug-repro" in {row["id"] for row in filtered.json()["data"]}
    org_only = client.get("/v1/org-library/")
    assert "bug-repro" not in {row["id"] for row in org_only.json()["data"]}


def test_share_unknown_team_is_404(client):
    client.post("/v1/org-library/", {"id": "ops-bot", "name": "Ops"}, format="json")
    response = client.post(
        "/v1/org-library/ops-bot/share/",
        {"scope": "team", "team_id": "missing"},
        format="json",
    )
    assert response.status_code == status.HTTP_404_NOT_FOUND
    fetched = client.get("/v1/org-library/ops-bot/")
    assert fetched.status_code == status.HTTP_200_OK
    assert fetched.json()["visibility"] == "org"
    assert fetched.json()["team_ids"] == []
    listed = {row["id"] for row in client.get("/v1/org-library/").json()["data"]}
    assert "ops-bot" in listed


def test_share_rejects_non_team_scope(client):
    client.post("/v1/org-library/", {"id": "ops-bot", "name": "Ops"}, format="json")
    response = client.post(
        "/v1/org-library/ops-bot/share/",
        {"scope": "public", "team_id": "eng"},
        format="json",
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST

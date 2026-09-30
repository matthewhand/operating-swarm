"""#1388 — /v1/agents/<id>/profile/ and settings GET identity fields."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import agent_settings as store

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_template_pack.json"
SECRET_NEEDLES = ("sk-", "api_key", "ghp_", "Bearer ", "password")


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()
    yield
    store.reset_agent_settings_cache()


def test_get_defaults_include_rail_header_fields(api_client):
    response = api_client.get("/v1/agents/worker/profile/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "agent_profile"
    assert body["agent_id"] == "worker"
    assert body["display_name"] == ""
    assert body["description"] == ""
    assert body["title"] == ""
    assert body["role"] == ""
    assert body["avatar_shape"] == "circle"
    assert body["avatar_color"] == ""
    assert body["avatar_path"] is None
    assert body["profile"]["avatar_shape"] == "circle"
    assert body["pack"]["profile"]["avatar_shape"] == "circle"
    assert body["pack"]["kind"] == "agent_template"


def test_settings_get_exposes_the_same_identity_fields(api_client):
    settings = api_client.get("/v1/agents/worker/settings/")
    assert settings.status_code == 200
    body = settings.json()
    for key in (
        "display_name",
        "description",
        "title",
        "role",
        "avatar_shape",
        "avatar_color",
        "avatar_path",
        "profile",
    ):
        assert key in body
    assert body["avatar_shape"] == "circle"


def test_create_update_read_via_profile_api(api_client):
    created = api_client.put(
        "/v1/agents/bee/profile/",
        {
            "display_name": "Bee",
            "description": "Short storefront blurb",
            "title": "Guide",
            "role": "support",
            "avatar_shape": "hexagon",
            "avatar_color": "#F59E0B",
            "avatar_path": "/avatars/bee/missing.png",
        },
        format="json",
    )
    assert created.status_code == 200
    body = created.json()
    assert body["display_name"] == "Bee"
    assert body["description"] == "Short storefront blurb"
    assert body["title"] == "Guide"
    assert body["role"] == "support"
    assert body["avatar_shape"] == "hexagon"
    assert body["avatar_color"] == "#f59e0b"
    assert body["avatar_path"] == "/avatars/bee/missing.png"
    assert body["pack"]["profile"]["display_name"] == "Bee"

    patched = api_client.patch(
        "/v1/agents/bee/profile/",
        {"display_name": "Honey Bee"},
        format="json",
    )
    assert patched.status_code == 200
    assert patched.json()["display_name"] == "Honey Bee"
    assert patched.json()["description"] == "Short storefront blurb"

    read = api_client.get("/v1/agents/bee/profile/")
    assert read.json()["display_name"] == "Honey Bee"
    assert read.json()["avatar_shape"] == "hexagon"

    settings = api_client.get("/v1/agents/bee/settings/")
    assert settings.json()["display_name"] == "Honey Bee"
    assert settings.json()["profile"]["role"] == "support"


def test_settings_patch_accepts_flat_and_nested_profile(api_client):
    nested = api_client.patch(
        "/v1/agents/desk/settings/",
        {"profile": {"display_name": "Desk", "avatar_shape": "square"}},
        format="json",
    )
    assert nested.status_code == 200
    assert nested.json()["display_name"] == "Desk"
    assert nested.json()["avatar_shape"] == "square"

    flat = api_client.patch(
        "/v1/agents/desk/settings/",
        {"storefront_description": "Lobby greeter", "avatar_color": "#112233"},
        format="json",
    )
    assert flat.status_code == 200
    assert flat.json()["description"] == "Lobby greeter"
    assert flat.json()["display_name"] == "Desk"
    assert flat.json()["avatar_color"] == "#112233"


def test_invalid_shape_and_color_are_400(api_client):
    shape = api_client.patch(
        "/v1/agents/worker/profile/",
        {"avatar_shape": "triangle"},
        format="json",
    )
    assert shape.status_code == 400
    assert "avatar_shape" in shape.json()["error"]

    color = api_client.put(
        "/v1/agents/worker/profile/",
        {"display_name": "Worker", "avatar_color": "not-a-color"},
        format="json",
    )
    assert color.status_code == 400
    assert "avatar_color" in color.json()["error"]
    assert api_client.get("/v1/agents/worker/profile/").json()["display_name"] == ""


def test_live_token_rejected_on_profile(api_client):
    response = api_client.patch(
        "/v1/agents/worker/profile/",
        {"display_name": "Bee", "api_key": "sk-live-secret"},
        format="json",
    )
    assert response.status_code == 400
    dumped = ""
    settings_path = store.settings_path()
    if settings_path.is_file():
        dumped = settings_path.read_text(encoding="utf-8")
    assert "sk-live" not in dumped
    assert "sk-live" not in json.dumps(response.json())


def test_pack_section_matches_secret_free_fixture(api_client):
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    response = api_client.put(
        "/v1/agents/storefront-bee/profile/",
        fixture["profile"],
        format="json",
    )
    assert response.status_code == 200
    pack = response.json()["pack"]
    assert pack["kind"] == "agent_template"
    assert pack["agent_id"] == "storefront-bee"
    assert pack["profile"]["display_name"] == fixture["profile"]["display_name"]
    assert pack["profile"]["avatar_shape"] == "hexagon"
    assert pack["profile"]["avatar_color"] == "#f59e0b"
    blob = json.dumps(pack)
    for needle in SECRET_NEEDLES:
        assert needle not in blob
    for needle in SECRET_NEEDLES:
        assert needle not in FIXTURE.read_text(encoding="utf-8")

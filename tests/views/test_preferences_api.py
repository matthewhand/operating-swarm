"""API tests for GET/PATCH /v1/preferences/ (REQ-144 / #540)."""

from __future__ import annotations

import json

import pytest
from django.contrib.auth import get_user_model
from django.urls import resolve
from rest_framework.test import APIClient

from swarm.models import UserPreference
from swarm.core.user_preferences import primary_operator_principal

User = get_user_model()


@pytest.fixture(autouse=True)
def disable_api_auth(settings):
    settings.ENABLE_API_AUTH = False


@pytest.fixture
def api_client():
    return APIClient()


def test_preferences_urls_accept_trailing_slash():
    assert resolve("/v1/preferences").url_name == "user-preferences-api-no-slash"
    assert resolve("/v1/preferences/").url_name == "user-preferences-api"


@pytest.mark.django_db
def test_get_empty_when_no_row(api_client):
    response = api_client.get("/v1/preferences/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "user_preferences"
    assert body["empty"] is True
    assert body["favourites"] == []
    assert body["hidden_agents"] == []
    assert body["hostname_override"] == ""
    keys = [item["key"] for item in body["registry"]]
    assert keys == [
        "favourites",
        "hidden_agents",
        "hostname_override",
        "context_auto_compress_pct",
        "context_strategy",
        "context_cull_trigger_pct",
        "context_cull_fraction_pct",
        "context_compress_api_only",
        "theme",
        "theme_navbar_mode",
        "bubble_theme",
        "rail_sections",
    ]
    assert body["context_auto_compress_pct"] == 80
    assert body["context_strategy"] == "compress"
    assert body["context_cull_trigger_pct"] == 90
    assert body["context_cull_fraction_pct"] == 50
    assert body["theme"] == "system"
    assert body["theme_navbar_mode"] == "if_not_system"
    assert body["bubble_theme"] == ""
    blob = json.dumps(body)
    assert "api_key" not in blob
    assert "sk-" not in blob


@pytest.mark.django_db
def test_patch_empty_is_400(api_client):
    response = api_client.patch("/v1/preferences/", {}, format="json")
    assert response.status_code == 400


@pytest.mark.django_db
def test_set_favourite_reload_same_order(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {
            "favourites": [
                {"id": "codey", "name": "Codey"},
                {"id": "support", "name": "Support"},
            ]
        },
        format="json",
    )
    assert response.status_code == 200
    assert [pin["id"] for pin in response.json()["favourites"]] == ["codey", "support"]
    assert response.json()["empty"] is False

    again = api_client.get("/v1/preferences/")
    assert again.status_code == 200
    assert [pin["id"] for pin in again.json()["favourites"]] == ["codey", "support"]
    assert again.json()["empty"] is False


@pytest.mark.django_db
def test_hide_visible_to_other_client_same_user():
    user = User.objects.create_user("alice", password="pw")
    writer = APIClient()
    writer.force_login(user)
    reader = APIClient()
    reader.force_login(user)

    writer.patch(
        "/v1/preferences/",
        {"hidden_agents": ["gate", "skeptic"]},
        format="json",
    )
    seen = reader.get("/v1/preferences/").json()
    assert seen["hidden_agents"] == ["gate", "skeptic"]
    assert seen["guest"] is False
    assert seen["principal"] == "user:alice"
    assert UserPreference.objects.filter(user=user).count() == 1


@pytest.mark.django_db
def test_prefs_are_isolated_per_user():
    alice = User.objects.create_user("alice", password="pw")
    bob = User.objects.create_user("bob", password="pw")
    alice_client = APIClient()
    alice_client.force_login(alice)
    bob_client = APIClient()
    bob_client.force_login(bob)

    alice_client.patch(
        "/v1/preferences/",
        {"favourites": [{"id": "codey", "name": "Codey"}]},
        format="json",
    )
    bob_client.patch(
        "/v1/preferences/",
        {"hidden_agents": ["stewie"]},
        format="json",
    )

    alice_body = alice_client.get("/v1/preferences/").json()
    bob_body = bob_client.get("/v1/preferences/").json()
    assert [pin["id"] for pin in alice_body["favourites"]] == ["codey"]
    assert alice_body["hidden_agents"] == []
    assert bob_body["favourites"] == []
    assert bob_body["hidden_agents"] == ["stewie"]
    assert UserPreference.objects.count() == 2


@pytest.mark.django_db
def test_guests_share_the_primary_operator_bag_when_auth_off():
    """#786: with API auth disabled, guest browsers resolve to the primary
    operator principal — one shared bag per installation, so an operator's
    rail layout follows them across devices. (Per-identity isolation above
    still holds for authenticated users/tokens.)"""
    first = APIClient()
    second = APIClient()
    first.patch(
        "/v1/preferences/",
        {"hidden_agents": ["codey"]},
        format="json",
    )
    other = second.get("/v1/preferences/").json()
    assert other["empty"] is False
    assert other["hidden_agents"] == ["codey"]
    assert other["guest"] is True
    assert other["principal"] == primary_operator_principal()


@pytest.mark.django_db
def test_rejects_secret_shaped_extra_keys(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {
            "favourites": [{"id": "support", "name": "Support"}],
            "values": {"custom_note": "hello", "api_key": "sk-secret", "openai_token": "x"},
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["values"] == {"custom_note": "hello"}
    blob = json.dumps(body)
    assert "sk-secret" not in blob
    assert "openai_token" not in blob
    row = UserPreference.objects.get()
    assert "api_key" not in row.values
    assert row.values.get("custom_note") == "hello"


@pytest.mark.django_db
def test_theme_and_display_preferences_roundtrip(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {
            "theme": "dark",
            "theme_navbar_mode": "always",
            "bubble_theme": "modern",
        },
        format="json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["theme"] == "dark"
    assert body["theme_navbar_mode"] == "always"
    assert body["bubble_theme"] == "modern"

    again = api_client.get("/v1/preferences/")
    assert again.status_code == 200
    assert again.json()["theme"] == "dark"
    assert again.json()["theme_navbar_mode"] == "always"
    assert again.json()["bubble_theme"] == "modern"


@pytest.mark.django_db
def test_patch_normalizes_duplicate_and_string_pins(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {"favourites": ["codey", {"id": "codey", "name": "Codey"}, {"id": "stewie"}]},
        format="json",
    )
    assert [pin["id"] for pin in response.json()["favourites"]] == ["codey", "stewie"]
    assert response.json()["favourites"][1]["name"] == "stewie"


@pytest.mark.django_db
def test_agent_dropdowns_roundtrip_and_drop_secrets(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {
            "values": {
                "agent_dropdowns": {
                    "cli_agent": {"cli": "grok", "model": "grok-4", "token": "x"},
                    "starter-remote": {"remote": "omb", "blueprint": "codey"},
                }
            }
        },
        format="json",
    )
    assert response.status_code == 200
    dropdowns = response.json()["values"]["agent_dropdowns"]
    assert dropdowns["cli_agent"] == {"cli": "grok", "model": "grok-4"}
    assert dropdowns["starter-remote"] == {"remote": "omb", "blueprint": "codey"}
    blob = json.dumps(response.json())
    assert "token" not in dropdowns["cli_agent"]
    assert "sk-" not in blob

    again = api_client.get("/v1/preferences/")
    assert again.json()["values"]["agent_dropdowns"]["cli_agent"]["cli"] == "grok"


@pytest.mark.django_db
def test_hostname_override_must_be_a_string(api_client):
    response = api_client.patch(
        "/v1/preferences/",
        {"hostname_override": 12},
        format="json",
    )
    assert response.status_code == 400


@pytest.mark.django_db
def test_hostname_override_visible_to_other_client_same_user():
    user = User.objects.create_user("alice", password="pw")
    writer = APIClient()
    writer.force_login(user)
    reader = APIClient()
    reader.force_login(user)

    writer.patch(
        "/v1/preferences/",
        {"hostname_override": "  lab-box\n"},
        format="json",
    )
    seen = reader.get("/v1/preferences/").json()
    assert seen["hostname_override"] == "lab-box"
    assert seen["empty"] is False
    blob = json.dumps(seen)
    assert "api_key" not in blob
    assert "sk-" not in blob


# ---------------------------------------------------------------------------
# #786 — rail_sections server persistence + admin-principal fallback
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_rail_sections_roundtrip(api_client):
    client = APIClient()
    state = {
        "sections": [
            {"id": "sec_a", "name": "Fancy", "collapsed": False, "internalOnly": True},
            {"id": "sec_b", "name": "CLI", "collapsed": True},
        ],
        "membership": {"jeeves": "sec_a", "grok": "sec_b"},
        "unassignedCollapsed": True,
    }
    resp = client.patch("/v1/preferences/", {"rail_sections": state}, format="json")
    assert resp.status_code == 200, resp.content
    # Server canonicalizes: boolean flags are always materialized.
    canonical = {
        **state,
        "sections": [
            {**s, "internalOnly": s.get("internalOnly", False)} for s in state["sections"]
        ],
    }
    assert resp.json()["rail_sections"] == canonical

    again = APIClient()
    seen = again.get("/v1/preferences/").json()
    assert seen["rail_sections"] == canonical


@pytest.mark.django_db
def test_rail_sections_shape_is_validated(api_client):
    client = APIClient()
    # sections must be a list of objects; membership an id->id map
    resp = client.patch(
        "/v1/preferences/",
        {"rail_sections": {"sections": ["nope"], "membership": "nope"}},
        format="json",
    )
    assert resp.status_code == 200
    seen = resp.json()["rail_sections"]
    assert seen["sections"] == []
    assert seen["membership"] == {}

    bad = client.patch("/v1/preferences/", {"rail_sections": "nope"}, format="json")
    assert bad.status_code == 400


@pytest.mark.django_db
def test_unauthenticated_great_falls_back_to_admin_principal():
    """#786: a guest request with no session middleware stamps the primary
    operator principal instead of an ephemeral session key — one shared bag
    per installation until real auth exists."""
    from swarm.core.user_preferences import preference_identity
    from rest_framework.test import APIRequestFactory

    factory = APIRequestFactory()
    request = factory.get("/v1/preferences/")

    _user, principal, guest = preference_identity(request)
    assert guest is True
    assert principal == "user:admin"


@pytest.mark.django_db
def test_admin_principal_row_is_shared_between_guest_requests():
    """Two guest requests (no session round-trip) see the same bag because
    both resolve to the primary-operator principal."""
    writer = APIClient()
    first = writer.patch(
        "/v1/preferences/",
        {
            "rail_sections": {
                "sections": [{"id": "sec_a", "name": "Work"}],
                "membership": {"jeeves": "sec_a"},
            }
        },
        format="json",
    )
    assert first.status_code == 200
    reader = APIClient()
    seen = reader.get("/v1/preferences/").json()
    assert seen["guest"] is True
    assert seen["principal"] == "user:admin"
    assert seen["rail_sections"]["membership"] == {"jeeves": "sec_a"}

"""#1388 agent storefront profile — persist, validate, secret-free packs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import agent_profile as profile
from swarm.core import agent_settings as store

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_template_pack.json"
SECRET_NEEDLES = (
    "sk-",
    "api_key",
    "ghp_",
    "Bearer ",
    "password",
    "cli_session_id",
    "remote_session_id",
)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    store.reset_agent_settings_cache()


def test_defaults_are_rail_safe(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    got = store.get_profile("worker")
    assert got["display_name"] == ""
    assert got["description"] == ""
    assert got["title"] == ""
    assert got["role"] == ""
    assert got["avatar_shape"] == "circle"
    assert got["avatar_color"] == ""
    assert got["avatar_path"] is None


def test_create_update_read_profile(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.replace_profile(
        "bee",
        {
            "display_name": "Bee",
            "description": "Friendly helper",
            "title": "Guide",
            "role": "support",
            "avatar_shape": "rounded",
            "avatar_color": "#f59e0b",
            "avatar_path": "/avatars/bee/missing-still.png",
        },
    )
    assert created["display_name"] == "Bee"
    assert created["description"] == "Friendly helper"
    assert created["role"] == "support"
    assert created["avatar_shape"] == "rounded"
    assert created["avatar_color"] == "#f59e0b"
    assert created["avatar_path"] == "/avatars/bee/missing-still.png"

    store.reset_agent_settings_cache()
    read = store.get_profile("bee")
    assert read == created

    updated = store.update_profile("bee", {"display_name": "Honey Bee", "avatar_shape": "hexagon"})
    assert updated["display_name"] == "Honey Bee"
    assert updated["description"] == "Friendly helper"
    assert updated["avatar_shape"] == "hexagon"
    store.reset_agent_settings_cache()
    assert store.get_profile("bee")["display_name"] == "Honey Bee"
    assert store.get_settings("other")["profile"]["display_name"] == ""


def test_missing_custom_avatar_is_non_blocking(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    path = "/avatars/does-not-exist-yet.png"
    got = store.update_profile("ghost", {"avatar_path": path})
    assert got["avatar_path"] == path
    assert not (tmp_path / "does-not-exist-yet.png").exists()


def test_invalid_shape_rejected(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="avatar_shape"):
        store.update_profile("worker", {"avatar_shape": "triangle"})
    assert store.get_profile("worker")["avatar_shape"] == "circle"


def test_invalid_color_rejected(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="avatar_color"):
        store.update_profile("worker", {"avatar_color": "red"})
    with pytest.raises(ValueError, match="avatar_color"):
        store.update_profile("worker", {"avatar_color": "#gggggg"})
    assert store.get_profile("worker")["avatar_color"] == ""


def test_rgb_hex_expands():
    assert profile.normalize_avatar_color("#f80") == "#ff8800"


def test_role_alias_normalizes_and_unknown_rejected(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    got = store.update_profile("cos", {"role": "cos"})
    assert got["role"] == "chief_of_staff"
    hyphen = store.update_profile("cos", {"role": "chief-of-staff"})
    assert hyphen["role"] == "chief_of_staff"
    assert store.update_profile("cos", {"role": "worker"})["role"] == ""
    with pytest.raises(ValueError, match="role"):
        store.update_profile("cos", {"role": "wizard"})


def test_registered_custom_role_persists(tmp_path, monkeypatch):
    """Custom roles join ROLE_REGISTRY at runtime and are not in CANONICAL_ROLES.

    The storefront role must accept the registered slug itself. Aliases live on
    the Role object (hyphenated), not only in the import-time alias table.
    """
    from swarm.core.agent_roles import CANONICAL_ROLES
    from swarm.core.roles.custom import CustomRole
    from swarm.core.roles.registry import register_role, unregister_role

    _isolate(tmp_path, monkeypatch)
    slug = "storefront_liaison"
    register_role(CustomRole(id=slug, label="Liaison", aliases=("liaison-alias",)))
    try:
        assert slug not in CANONICAL_ROLES
        got = store.update_profile("bee", {"role": slug})
        assert got["role"] == slug
        aliased = store.update_profile("bee", {"role": "liaison-alias"})
        assert aliased["role"] == slug
        store.reset_agent_settings_cache()
        assert store.get_profile("bee")["role"] == slug
    finally:
        unregister_role(slug)


def test_custom_role_id_beats_builtin_alias(tmp_path, monkeypatch):
    """``helper`` is a support alias. A registered custom id of that name wins."""
    from swarm.core.roles.custom import CustomRole
    from swarm.core.roles.registry import register_role, unregister_role

    _isolate(tmp_path, monkeypatch)
    register_role(CustomRole(id="helper", label="Helper"))
    try:
        got = store.update_profile("bee", {"role": "helper"})
        assert got["role"] == "helper"
    finally:
        unregister_role("helper")


def test_saved_custom_role_survives_registry_loss(tmp_path, monkeypatch):
    """Unrelated saves must not blank a custom slug after the registry forgets it.

    Custom roles are process-local. GET and a display-name or settings patch
    still have to round-trip the slug that was valid when it was written.
    A different unknown slug is still rejected.
    """
    from swarm.core.roles.custom import CustomRole
    from swarm.core.roles.registry import register_role, unregister_role

    _isolate(tmp_path, monkeypatch)
    slug = "storefront_liaison"
    register_role(CustomRole(id=slug, label="Liaison", aliases=("liaison-alias",)))
    try:
        store.update_profile("bee", {"role": slug, "display_name": "Bee"})
    finally:
        unregister_role(slug)

    assert store.get_profile("bee")["role"] == slug
    renamed = store.update_profile("bee", {"display_name": "Honey Bee"})
    assert renamed["display_name"] == "Honey Bee"
    assert renamed["role"] == slug
    store.update_settings("bee", {"use_suggestions": True})
    assert store.get_profile("bee")["role"] == slug
    replaced = store.replace_profile(
        "bee",
        {**store.get_profile("bee"), "title": "Host"},
    )
    assert replaced["title"] == "Host"
    assert replaced["role"] == slug
    with pytest.raises(ValueError, match="role"):
        store.update_profile("bee", {"role": "wizard"})
    assert store.get_profile("bee")["role"] == slug
    assert store.update_profile("bee", {"role": "support"})["role"] == "support"


def test_avatar_path_rejects_traversal_and_urls():
    with pytest.raises(ValueError, match="avatar_path"):
        profile.normalize_avatar_path("../etc/passwd")
    with pytest.raises(ValueError, match="avatar_path"):
        profile.normalize_avatar_path("/etc/passwd")
    with pytest.raises(ValueError, match="avatar_path"):
        profile.normalize_avatar_path("https://evil.example/steal.png")
    with pytest.raises(ValueError, match="avatar_path"):
        profile.normalize_avatar_path("file:///tmp/secret.png")


def test_profile_rejects_secrets():
    with pytest.raises(ValueError, match="secrets"):
        profile.normalize_profile({"display_name": "Bee", "api_key": "sk-live"})


def test_pack_helpers_expose_profile_without_secrets():
    pack = profile.serialize_template_pack(
        "bee",
        {
            "display_name": "Bee",
            "description": "Short blurb",
            "title": "Guide",
            "role": "support",
            "avatar_shape": "circle",
            "avatar_color": "#111111",
            "avatar_path": "/avatars/bee/bee-profile-worker.svg",
        },
        extra={"api_key": "sk-live", "folder": "/home/op/.ssh", "cli_session_id": "sess-1"},
    )
    assert pack["kind"] == "agent_template"
    assert "profile" in pack
    assert pack["profile"]["display_name"] == "Bee"
    assert pack["profile"]["description"] == "Short blurb"
    assert "extra" not in pack
    blob = json.dumps(pack)
    for needle in SECRET_NEEDLES:
        assert needle not in blob


def test_fixture_is_secret_free():
    text = FIXTURE.read_text(encoding="utf-8")
    data = json.loads(text)
    assert data["kind"] == "agent_template"
    assert set(data["profile"]) == set(profile.PROFILE_FIELD_KEYS)
    for needle in SECRET_NEEDLES:
        assert needle not in text
    normalized = profile.normalize_profile(data["profile"])
    assert normalized["display_name"] == "Storefront Bee"
    assert profile.serialize_template_pack(data["agent_id"], data["profile"])["profile"] == normalized


def test_settings_patch_merges_flat_identity_fields(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    store.update_settings(
        "desk",
        {
            "profile": {
                "display_name": "Desk",
                "description": "Front desk",
                "avatar_shape": "square",
            }
        },
    )
    store.update_settings("desk", {"profile": {"title": "Host"}})
    got = store.get_settings("desk")["profile"]
    assert got["display_name"] == "Desk"
    assert got["title"] == "Host"
    assert got["avatar_shape"] == "square"

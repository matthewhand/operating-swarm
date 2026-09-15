"""Unit tests for the REQ-144 preferences registry helpers."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from swarm.core.user_preferences import (
    coerce_values,
    is_secret_key,
    merge_values,
    normalize_agent_dropdowns,
    normalize_favourites,
    normalize_hostname_override,
    preference_identity,
    public_payload,
)

User = get_user_model()


def test_normalize_favourites_dedupes_and_fills_names():
    pins = normalize_favourites(
        ["codey", {"id": "codey", "name": "Codey"}, {"id": "stewie"}, {"id": ""}, 3]
    )
    assert pins == [
        {"id": "codey", "name": "codey"},
        {"id": "stewie", "name": "stewie"},
    ]


def test_secret_keys_are_dropped_from_the_bag():
    assert is_secret_key("api_key")
    assert is_secret_key("openai_token")
    bag = coerce_values(
        {
            "favourites": [{"id": "support"}],
            "hidden_agents": ["gate", "gate", ""],
            "theme": "dark",
            "api_key": "sk-nope",
        }
    )
    assert bag["favourites"] == [{"id": "support", "name": "support"}]
    assert bag["hidden_agents"] == ["gate"]
    assert bag["theme"] == "dark"
    assert "api_key" not in bag


def test_merge_values_patches_known_keys_only():
    current = {"favourites": [{"id": "support", "name": "Support"}], "theme": "light"}
    merged = merge_values(current, {"hidden_agents": ["skeptic"], "theme": "dark"})
    assert merged["favourites"] == [{"id": "support", "name": "Support"}]
    assert merged["hidden_agents"] == ["skeptic"]
    assert merged["theme"] == "dark"


def test_extras_bag_keeps_role_agent_tip_dismissed():
    bag = coerce_values({"role_agent_tip_dismissed": True, "theme": "dark"})
    assert bag["role_agent_tip_dismissed"] is True
    payload = public_payload(
        principal="user:alice",
        guest=False,
        empty=False,
        values=bag,
    )
    assert payload["values"]["role_agent_tip_dismissed"] is True


def test_public_payload_marks_empty_and_lists_registry():
    payload = public_payload(principal="user:alice", guest=False, empty=True)
    assert payload["object"] == "user_preferences"
    assert payload["empty"] is True
    assert payload["favourites"] == []
    assert payload["hostname_override"] == ""
    assert [item["key"] for item in payload["registry"]] == [
        "favourites",
        "hidden_agents",
        "hostname_override",
        "context_auto_compress_pct",
        "context_strategy",
        "context_cull_trigger_pct",
        "context_cull_fraction_pct",
        "context_compress_api_only",
    ]
    assert payload["context_auto_compress_pct"] == 80
    assert payload["context_strategy"] == "compress"
    assert payload["context_cull_trigger_pct"] == 90
    assert payload["context_cull_fraction_pct"] == 50


def test_normalize_agent_dropdowns_keeps_safe_fields_only():
    cleaned = normalize_agent_dropdowns(
        {
            "cli_agent": {"cli": " grok ", "model": "grok-4", "api_key": "sk-nope"},
            "": {"cli": "agy"},
            "api_key": {"cli": "grok"},
            "codey": "grok",
        }
    )
    assert cleaned == {"cli_agent": {"cli": "grok", "model": "grok-4"}}


def test_normalize_hostname_override_strips_controls_and_caps_length():
    assert normalize_hostname_override("  lab-box\n") == "lab-box"
    assert normalize_hostname_override(None) == ""
    long_name = "x" * 300
    assert len(normalize_hostname_override(long_name)) == 255


def test_preference_identity_uses_authenticated_user():
    factory = RequestFactory()
    request = factory.get("/v1/preferences/")
    request.user = User(username="alice")
    user, principal, guest = preference_identity(request)
    assert user is request.user
    assert principal == "user:alice"
    assert guest is False

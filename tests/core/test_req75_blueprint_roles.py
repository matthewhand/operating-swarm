"""REQ-75: blueprint default role + workflow hint, apply-on-create.

Fixture metadata + live catalog filter. No secrets, no :8001.
"""

import pytest

from swarm.core.agent_roles import (
    ROLE_DEFAULT,
    ROLE_ENGINEER,
    ROLE_GATE,
    ROLE_SUPPORT,
    apply_blueprint_role,
    blueprint_role_fields,
    is_webui_blueprint,
    normalize_agent_role,
    normalize_workflow,
    role_badge_label,
)


FIXTURE_GATE = {
    "name": "fixture_gate",
    "title": "Fixture Gate",
    "role": "gate",
    "workflow": "as_tool",
}

FIXTURE_PLAIN = {
    "name": "fixture_plain",
    "title": "Fixture Plain",
    "description": "No role declared.",
}


def test_fixture_gate_blueprint_assigns_gate_role():
    fields = blueprint_role_fields(FIXTURE_GATE)
    assert fields["role"] == ROLE_GATE
    # #1080 renamed the gate role's badge to its canonical name, Belay
    # ('gate' remains a legacy alias).
    assert role_badge_label(fields["role"]) == "Belay"
    created = apply_blueprint_role(fields["role"])
    assert created == ROLE_GATE
    assert role_badge_label(created) == "Belay"


def test_fixture_plain_blueprint_assigns_no_role():
    fields = blueprint_role_fields(FIXTURE_PLAIN)
    assert fields["role"] == ROLE_DEFAULT
    assert role_badge_label(fields["role"]) == ""
    created = apply_blueprint_role(fields["role"])
    assert created == ROLE_DEFAULT
    assert role_badge_label(created) == ""


def test_none_role_is_default_no_badge():
    assert normalize_agent_role("none") == ROLE_DEFAULT
    assert role_badge_label("none") == ""
    assert blueprint_role_fields({"role": "none"})["role"] == ROLE_DEFAULT


def test_engineer_is_canonical():
    assert normalize_agent_role("engineer") == ROLE_ENGINEER
    assert normalize_agent_role("eng") == ROLE_ENGINEER
    assert role_badge_label("engineer") == "Engineer"
    fields = blueprint_role_fields(
        {
            "role": "engineer",
            "agents": [{"name": "Pat", "role": "engineer"}],
        }
    )
    assert fields["role"] == ROLE_ENGINEER
    assert fields["agents"][0]["role"] == ROLE_ENGINEER


def test_workflow_hint_handoff_and_as_tool():
    assert normalize_workflow("handoff") == "handoff"
    assert normalize_workflow("as-tool") == "as_tool"
    assert normalize_workflow("as_tool") == "as_tool"
    assert normalize_workflow(None) is None
    assert normalize_workflow("orchestra") is None
    assert blueprint_role_fields(FIXTURE_GATE)["workflow"] == "as_tool"
    assert blueprint_role_fields({"workflow": "handoff"})["workflow"] == "handoff"
    assert blueprint_role_fields(FIXTURE_PLAIN)["workflow"] is None


def test_editor_override_wins_re_pick_applies_unless_overridden():
    assert apply_blueprint_role("gate", current_role="support", role_overridden=True) == ROLE_SUPPORT
    assert apply_blueprint_role("gate", current_role="support", role_overridden=False) == ROLE_GATE
    # Re-pick a plain blueprint after an explicit override — keep the editor role.
    assert apply_blueprint_role("none", current_role="skeptic", role_overridden=True) == "skeptic"
    # Re-pick without override restores the new blueprint default (none → no role).
    assert apply_blueprint_role("none", current_role="skeptic", role_overridden=False) == ROLE_DEFAULT


def test_picker_does_not_classify_cli_api_as_webui():
    assert is_webui_blueprint("codey", {"role": "default"}) is False
    assert is_webui_blueprint("gate", FIXTURE_GATE) is False
    assert is_webui_blueprint("support", {"role": "support"}) is False


def test_django_chat_and_webui_kind_are_webui():
    assert is_webui_blueprint("django_chat", {}) is True
    assert is_webui_blueprint("other", {"kind": "webui"}) is True
    assert is_webui_blueprint(
        "legacy_page",
        {"urls_module": "blueprints.django_chat.urls", "url_prefix": "django_chat/"},
    ) is True


@pytest.mark.django_db
def test_live_catalog_picker_has_no_webui_kind(api_client):
    response = api_client.get("/v1/blueprints/")
    assert response.status_code == 200
    rows = response.json()["data"]
    assert rows, "expected bundled CLI/API recipes"
    for row in rows:
        assert row.get("webui") is False
        assert is_webui_blueprint(row.get("id"), row) is False
        assert row.get("id") != "django_chat"
        assert str(row.get("kind") or "").lower() not in {
            "webui",
            "django_chat",
            "webpage",
        }

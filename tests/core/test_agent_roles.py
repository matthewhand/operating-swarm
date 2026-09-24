"""REQ-28 / REQ-9 role enum — Chief of Staff aliases and rail contract."""

from swarm.core.agent_roles import (
    CANONICAL_ROLES,
    ROLE_CHIEF_OF_STAFF,
    ROLE_DEFAULT,
    ROLE_ENGINEER,
    ROLE_GATE,
    ROLE_BELAY,
    ROLE_SKEPTIC,
    ROLE_SUGGESTIONS,
    ROLE_SUPPORT,
    blueprint_role_fields,
    can_manage_agent_lifecycle,
    can_manage_topology,
    is_chief_of_staff,
    is_belay_role,
    normalize_agent_role,
    role_badge_label,
    role_css_class,
)


def test_chief_of_staff_aliases():
    for alias in ("chief_of_staff", "cos", "chief", "Chief", "CoS", "chief-of-staff"):
        assert normalize_agent_role(alias) == ROLE_CHIEF_OF_STAFF
        assert is_chief_of_staff(alias)


def test_lifecycle_roles_are_support_and_cos_only():
    assert can_manage_agent_lifecycle("support")
    assert can_manage_agent_lifecycle("helper")
    assert can_manage_agent_lifecycle("cos")
    assert can_manage_agent_lifecycle("chief_of_staff")
    assert not can_manage_agent_lifecycle("engineer")
    assert not can_manage_agent_lifecycle("gate")
    assert not can_manage_agent_lifecycle("default")
    assert not can_manage_agent_lifecycle("skeptic")


def test_topology_tools_are_cos_only():
    assert can_manage_topology("chief_of_staff")
    assert can_manage_topology("cos")
    assert can_manage_topology("chief")
    assert not can_manage_topology("support")
    assert not can_manage_topology("helper")
    assert not can_manage_topology("engineer")
    assert not can_manage_topology("default")


def test_role_enum_includes_cos_and_existing_seats():
    assert ROLE_CHIEF_OF_STAFF in CANONICAL_ROLES
    assert {
        ROLE_DEFAULT,
        ROLE_SUPPORT,
        ROLE_GATE,
        ROLE_SKEPTIC,
        ROLE_CHIEF_OF_STAFF,
        ROLE_ENGINEER,
        ROLE_SUGGESTIONS,
    } <= set(CANONICAL_ROLES)


def test_unknown_role_is_default_not_cos():
    assert normalize_agent_role("Writer") == ROLE_DEFAULT
    assert not is_chief_of_staff("Writer")


def test_cos_badge_contract_is_not_support_gate_or_skeptic():
    css = role_css_class("cos")
    assert css == "os-agent-role-chief_of_staff"
    assert css != role_css_class("support")
    assert css != role_css_class("gate")
    assert css != role_css_class("skeptic")
    assert role_badge_label("cos") == "CoS"
    assert role_badge_label("chief") == "CoS"


def test_blueprint_role_fields_surface_cos():
    fields = blueprint_role_fields(
        {
            "role": "cos",
            "agents": [
                {"name": "Pat", "role": "chief"},
                {"name": "Sam", "role": "default"},
            ],
        }
    )
    assert fields["role"] == ROLE_CHIEF_OF_STAFF
    assert fields["chief_of_staff_agent"] == "Pat"


def test_engineer_role_and_blueprint_fields():
    assert normalize_agent_role("engineer") == ROLE_ENGINEER
    assert role_badge_label("engineer") == "Engineer"
    assert role_css_class("engineer") == "os-agent-role-engineer"
    fields = blueprint_role_fields({"role": "engineer", "workflow": "as_tool"})
    assert fields["role"] == ROLE_ENGINEER
    assert fields["workflow"] == "as_tool"


def test_suggestions_role_and_blueprint_fields():
    assert normalize_agent_role("suggest") == ROLE_SUGGESTIONS
    assert normalize_agent_role("suggestion") == ROLE_SUGGESTIONS
    assert role_badge_label("suggestions") == "Suggest"
    assert role_css_class("suggestions") == "os-agent-role-suggestions"
    fields = blueprint_role_fields(
        {
            "role": "default",
            "agents": [
                {"name": "Tips", "role": "suggestions"},
                {"name": "Sam", "role": "default"},
            ],
        }
    )
    assert fields["suggestions_agent"] == "Tips"


def test_belay_role_aliases_and_badge():
    for alias in ("belay", "belayer", "gate", "tool_gate", "tool-gate", "toolgate"):
        assert normalize_agent_role(alias) == ROLE_GATE
        assert is_belay_role(alias)
    assert role_badge_label("belay") == "Belay"
    assert role_badge_label("belayer") == "Belay"
    assert role_badge_label("gate") == "Belay"
    assert ROLE_BELAY == ROLE_GATE

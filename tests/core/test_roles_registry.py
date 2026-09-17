"""REQ-852 Phase 1 — Role base, registry, and agent_roles shim parity.

The legacy parallel tables in ``agent_roles.py`` (aliases, badges, CSS
classes, mechanisms, allow-all) now derive from ``ROLE_REGISTRY``. These
tests embed the legacy literals as the behavior lock: the registry must
produce identical tables, and ``/v1/roles/`` descriptors must stay stable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from swarm.core.agent_roles import (  # noqa: F401  (shim parity is the point)
    CANONICAL_ROLES,
    ROLE_ADVISOR,
    ROLE_ALIASES,
    ROLE_ALLOW_ALL,
    ROLE_BADGE_LABELS,
    ROLE_CHIEF_OF_STAFF,
    ROLE_CSS_CLASS_PREFIX,
    ROLE_CSS_CLASSES,
    ROLE_DEFAULT,
    ROLE_ENGINEER,
    ROLE_GATE,
    ROLE_MECHANISM_DETAILS,
    ROLE_MECHANISMS,
    ROLE_SKEPTIC,
    ROLE_SUGGESTIONS,
    ROLE_SUPPORT,
    get_canonical_role_descriptors,
    normalize_agent_role,
)
from swarm.core.roles import ROLE_REGISTRY, all_roles, get_role
from swarm.core.roles.base import Role, RoleContext, RoleOutcome

LEGACY_ALIASES: dict[str, str] = {
    "default": ROLE_DEFAULT,
    "none": ROLE_DEFAULT,
    "worker": ROLE_DEFAULT,
    "agent": ROLE_DEFAULT,
    "coordinator": ROLE_DEFAULT,
    "support": ROLE_SUPPORT,
    "helper": ROLE_SUPPORT,
    "gate": ROLE_GATE,
    "tool_gate": ROLE_GATE,
    "tool-gate": ROLE_GATE,
    "toolgate": ROLE_GATE,
    "skeptic": ROLE_SKEPTIC,
    "reviewer": ROLE_SKEPTIC,
    "advisor": ROLE_ADVISOR,
    "adviser": ROLE_ADVISOR,
    "mentor": ROLE_ADVISOR,
    "chief_of_staff": ROLE_CHIEF_OF_STAFF,
    "chief-of-staff": ROLE_CHIEF_OF_STAFF,
    "chiefofstaff": ROLE_CHIEF_OF_STAFF,
    "cos": ROLE_CHIEF_OF_STAFF,
    "chief": ROLE_CHIEF_OF_STAFF,
    "engineer": ROLE_ENGINEER,
    "eng": ROLE_ENGINEER,
    "suggestions": ROLE_SUGGESTIONS,
    "suggestion": ROLE_SUGGESTIONS,
    "suggest": ROLE_SUGGESTIONS,
}

LEGACY_BADGES = {
    ROLE_DEFAULT: "",
    ROLE_SUPPORT: "Support",
    ROLE_GATE: "Gate",
    ROLE_SKEPTIC: "Skeptic",
    ROLE_ADVISOR: "Advisor",
    ROLE_CHIEF_OF_STAFF: "CoS",
    ROLE_ENGINEER: "Engineer",
    ROLE_SUGGESTIONS: "Suggest",
}

LEGACY_MECHANISMS = {
    ROLE_DEFAULT: "none",
    ROLE_SUPPORT: "implement",
    ROLE_GATE: "intercept",
    ROLE_SKEPTIC: "parse",
    ROLE_ADVISOR: "parse",
    ROLE_CHIEF_OF_STAFF: "intercept",
    ROLE_ENGINEER: "implement",
    ROLE_SUGGESTIONS: "parse",
}

LEGACY_MECHANISM_DETAILS = {
    ROLE_DEFAULT: "Worker agent executing standard conversational turns without role overrides.",
    ROLE_SUPPORT: "Socratic support and agent lifecycle manager (REQ-7, REQ-154).",
    ROLE_GATE: "Tool-call classifier intercepting execution requests before execution.",
    ROLE_SKEPTIC: "Post-run output validator performing bounded retries on failures.",
    ROLE_ADVISOR: "Reviews a completed turn and posts one concise follow-up advice note.",
    ROLE_CHIEF_OF_STAFF: "Orchestrator seat with cross-team communication and mailbox-wide scope (REQ-28).",
    ROLE_ENGINEER: "Implementer seat for software development, test authoring, and file editing.",
    ROLE_SUGGESTIONS: "Generates quick-select follow-up prompt chips after model turns (REQ-85).",
}

LEGACY_ALLOW_ALL = {
    ROLE_DEFAULT: False,
    ROLE_SUPPORT: False,
    ROLE_GATE: False,
    ROLE_SKEPTIC: False,
    ROLE_ADVISOR: False,
    ROLE_CHIEF_OF_STAFF: True,
    ROLE_ENGINEER: False,
    ROLE_SUGGESTIONS: False,
}


# ------------------------------------------------------------ registry shape


def test_registry_covers_all_canonical_roles():
    assert set(ROLE_REGISTRY) == set(CANONICAL_ROLES)
    assert len(ROLE_REGISTRY) == 8


def test_registry_order_matches_canonical_roles():
    assert tuple(role.id for role in all_roles()) == CANONICAL_ROLES


def test_get_role_round_trip_and_miss():
    assert get_role("skeptic") is not None
    assert get_role("skeptic").id == ROLE_SKEPTIC
    assert get_role("nope") is None


# ------------------------------------------------- legacy table parity (lock)


def test_aliases_derive_from_registry():
    assert ROLE_ALIASES == LEGACY_ALIASES


def test_badge_labels_derive_from_registry():
    assert ROLE_BADGE_LABELS == LEGACY_BADGES


def test_mechanisms_derive_from_registry():
    assert ROLE_MECHANISMS == LEGACY_MECHANISMS
    assert ROLE_MECHANISM_DETAILS == LEGACY_MECHANISM_DETAILS


def test_allow_all_derive_from_registry():
    assert ROLE_ALLOW_ALL == LEGACY_ALLOW_ALL


def test_css_classes_derive_from_registry():
    assert ROLE_CSS_CLASS_PREFIX == "os-agent-role-"
    assert {
        role: f"os-agent-role-{role}" for role in CANONICAL_ROLES
    } == ROLE_CSS_CLASSES


def test_normalize_still_routes_aliases():
    assert normalize_agent_role("CoS") == ROLE_CHIEF_OF_STAFF
    assert normalize_agent_role("tool-gate") == ROLE_GATE
    assert normalize_agent_role("whatever") == ROLE_DEFAULT
    assert normalize_agent_role(None) == ROLE_DEFAULT


# ------------------------------------------------- descriptor API stability


def test_descriptors_match_legacy_shape_and_order():
    legacy_keys = {
        "name",
        "label",
        "aliases",
        "allow_all",
        "mechanism",
        "mechanism_detail",
        "css_class",
    }
    descriptors = get_canonical_role_descriptors()
    assert [d["name"] for d in descriptors] == list(CANONICAL_ROLES)
    for d in descriptors:
        assert set(d) == legacy_keys
        assert d["label"] == LEGACY_BADGES[d["name"]]
        assert d["allow_all"] == LEGACY_ALLOW_ALL[d["name"]]
        assert d["mechanism"] == LEGACY_MECHANISMS[d["name"]]
        assert d["mechanism_detail"] == LEGACY_MECHANISM_DETAILS[d["name"]]
        assert d["css_class"] == f"os-agent-role-{d['name']}"
    cos = next(d for d in descriptors if d["name"] == ROLE_CHIEF_OF_STAFF)
    assert cos["aliases"] == ["chief_of_staff", "chief-of-staff", "chiefofstaff", "cos", "chief"]
    skeptic = next(d for d in descriptors if d["name"] == ROLE_SKEPTIC)
    assert skeptic["aliases"] == ["skeptic", "reviewer"]


# ----------------------------------------------------- hook defaults + seams


def test_role_base_defaults_are_noops():
    class Probe(Role):
        id = "probe"

    probe = Probe()
    ctx = RoleContext()
    assert probe.on_turn_start(ctx) == RoleOutcome()
    assert probe.on_turn_end(ctx, "result") == RoleOutcome()
    calls = [{"name": "t"}]
    assert probe.wrap_tool_calls(ctx, calls) is calls
    assert probe.as_tool(ctx) is None


def test_metadata_only_roles_never_override_hooks():
    for role_id in (ROLE_DEFAULT, ROLE_SUPPORT, ROLE_CHIEF_OF_STAFF, ROLE_ENGINEER):
        role = get_role(role_id)
        assert role.on_turn_start(RoleContext()) == RoleOutcome()
        assert role.on_turn_end(RoleContext(), "x") == RoleOutcome()
        assert role.as_tool(RoleContext()) is None


def test_gate_role_unwired_is_pass_through_and_wrapping_delegates():
    gate = get_role(ROLE_GATE)
    calls = ["tool_a", "tool_b"]
    # Default-open: no gate / classify_fn → unchanged (fail-open contract).
    assert gate.wrap_tool_calls(RoleContext(), calls) is calls

    # Wired with a classify_fn → delegates to tool_gate.wrap_tools_with_gate.
    def classify(_text: str, _params: dict) -> bool:
        return False  # always safe

    wrapped = gate.wrap_tool_calls(
        RoleContext(params={"classify_fn": classify}), calls
    )
    assert len(list(wrapped)) == 2


def test_skeptic_role_turn_end_emits_bounded_retry_directive():
    skeptic = get_role(ROLE_SKEPTIC)

    class FakeResult:
        accomplished = False
        findings = ["missing tests", "edge case uncovered"]

    outcome = skeptic.on_turn_end(RoleContext(), FakeResult())
    assert outcome.retry_directive == "edge case uncovered"
    assert skeptic.on_turn_end(RoleContext(), "plain output") == RoleOutcome()


def test_skeptic_role_run_bounded_delegates_to_run_with_skeptic():

    skeptic = get_role(ROLE_SKEPTIC)

    async def fake_run(_agent: Any, _message: str) -> str:
        return "done"

    result = asyncio.run(
        skeptic.run_bounded(agent="agent", prompt="p", run_fn=fake_run)
    )
    assert result.output == "done"
    assert result.attempts == 1


def test_advisor_role_resolution_seam(monkeypatch):
    import swarm.core.team_rosters as team_rosters

    monkeypatch.setattr(
        team_rosters,
        "advisor_blueprint_for_agent",
        lambda _team_id, _agent_id: "wise1",
    )
    assert get_role(ROLE_ADVISOR).resolve_advisor("t1", "ba") == "wise1"


def test_chief_of_staff_is_only_allow_everywhere():
    assert ROLE_ALLOW_ALL[ROLE_CHIEF_OF_STAFF] is True
    assert sum(1 for v in ROLE_ALLOW_ALL.values() if v) == 1


def test_suggestions_role_as_tool_requires_coordinator_and_specialist():
    suggestions = get_role(ROLE_SUGGESTIONS)
    # No coordinator → fail-soft None.
    assert suggestions.as_tool(RoleContext(params={"agents": {}})) is None
    # Wired → returns the resolved specialist seat.
    specialist = {"name": "chips", "role": "suggestions"}

    class Coordinator:
        pass

    outcome = suggestions.as_tool(
        RoleContext(coordinator=Coordinator(), params={"agents": {"chips": specialist}})
    )
    assert outcome == specialist


def test_register_role_rejects_idless_class_and_returns_class():
    from swarm.core.roles.registry import register_role

    class Idless(Role):
        pass

    with pytest.raises(ValueError):
        register_role(Idless())

    class Probe2(Role):
        id = "probe2"

    assert register_role(Probe2) is Probe2
    assert get_role("probe2") is not None
    ROLE_REGISTRY.pop("probe2", None)  # keep registry canonical for other tests

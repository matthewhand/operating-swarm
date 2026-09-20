"""#750 — Support must build the blueprint the discussion asks for.

Mandatory requirement: arbitrary natural-language team asks ("3 philosophers,
each reinterpreting the previous") produce a matching, usable blueprint —
never the canned First Team / starter-code dump. Proven three ways:

1. Detection: the phrasing is recognized as a create request.
2. Inference: the live agent's ``create_blueprint`` tool synthesizes and
   persists a blueprint from model-provided roster/edges JSON.
3. Deterministic fallback: the heuristic derive path builds the same shape
   hermetically (no LLM configured / SWARM_TEST_MODE).
"""

from __future__ import annotations

import pytest

from swarm.core.support_nl_blueprint import (
    SUPPORT_NL_SOURCE,
    CreatedNlBlueprint,
    NlBlueprintSpec,
    derive_spec_from_prompt,
    nl_create_or_socratic,
    render_spec_python,
    wants_nl_create,
)

PHILOSOPHERS_ASK = (
    "can you create me a blueprint that has 3 philosophers? "
    "and each one reinterprets the previous?"
)


# --- 1. Detection -----------------------------------------------------------


@pytest.mark.parametrize(
    "ask",
    [
        PHILOSOPHERS_ASK,
        "build me a team of 3 philosophers, each reinterpreting the previous",
        "design a council of 4 critics who debate a draft",
        "make me a workflow with 5 reviewers in a loop",
        "give me a squad of two poets",
    ],
)
def test_wants_nl_create_catches_creative_team_asks(ask: str) -> None:
    assert wants_nl_create(ask) is True


def test_wants_nl_create_still_rejects_non_create_chat() -> None:
    assert wants_nl_create("what is a blueprint?") is False
    assert wants_nl_create("hey") is False


# --- 2. Inference: the create_blueprint tool --------------------------------


def _philosopher_roster_json() -> dict:
    return {
        "title": "Three Philosophers",
        "description": "Each philosopher reinterprets the previous position.",
        "roster": [
            {"name": "Philosopher 1", "instructions": "Open the inquiry."},
            {"name": "Philosopher 2", "instructions": "Reinterpret Philosopher 1."},
            {"name": "Philosopher 3", "instructions": "Reinterpret Philosopher 2."},
        ],
        "edges": [["Philosopher 1", "Philosopher 2"], ["Philosopher 2", "Philosopher 3"]],
        "workflow": "handoff",
    }


def test_create_blueprint_tool_synthesizes_and_persists() -> None:
    tool = _create_blueprint_tool()
    reply = tool(_philosopher_roster_json())
    assert "Created **Three Philosophers**" in reply
    assert '"persisted": true' in reply
    # Persisted into the seat registry (disk under SWARM_TEST_MODE is
    # intentionally skipped) and immediately usable in chat (#723).
    from swarm.views import api_views

    custom = [row for row in api_views._custom_blueprints_registry if isinstance(row, dict)]
    assert any(row.get("name") == "Three Philosophers" for row in custom)
    assert any("/chat?blueprint=" in row.get("id", "") or row.get("rail") for row in custom)


def test_create_blueprint_tool_rejects_bad_edges() -> None:
    tool = _create_blueprint_tool()
    bad = _philosopher_roster_json()
    bad["edges"] = [["Philosopher 1", "Ghost"]]
    reply = tool(bad)
    assert "error" in reply.lower()


# --- 3. Deterministic fallback (hermetic) ------------------------------------


def test_derive_spec_parses_count_role_and_chain() -> None:
    spec = derive_spec_from_prompt(PHILOSOPHERS_ASK)
    assert spec is not None
    assert len(spec.roster) == 3
    names = [name for name, _ in spec.roster]
    assert names == ["Philosopher 1", "Philosopher 2", "Philosopher 3"]
    # Chain: each member hands off to the next.
    assert list(spec.edges) == [
        ("Philosopher 1", "Philosopher 2"),
        ("Philosopher 2", "Philosopher 3"),
    ]
    instructions = " ".join(text for _, text in spec.roster).lower()
    assert "reinterpret" in instructions or "previous" in instructions


def test_derive_spec_unknown_shape_falls_back_to_team() -> None:
    spec = derive_spec_from_prompt("build me a team of gardeners")
    assert spec is not None
    assert spec.roster  # still derives a usable roster from the role word


def test_created_code_compiles_and_wires_handoffs() -> None:
    spec = derive_spec_from_prompt(PHILOSOPHERS_ASK)
    code = render_spec_python(spec)
    ns: dict = {}
    exec(compile(code, "<support-nl>", "exec"), ns)  # noqa: S102 - test compiles generated code
    classes = [
        v
        for v in ns.values()
        if isinstance(v, type) and v.__name__ == spec.class_name
    ]
    assert classes, "generated module must define the spec class"
    bp = classes[0](blueprint_id=spec.blueprint_id)
    start = bp.create_starting_agent(mcp_servers=[])
    # Start node = the member with no incoming edge.
    assert start.name == spec.roster[0][0]
    handoff_names = {getattr(h, "name", "") for h in (start.handoffs or [])}
    assert handoff_names == {spec.roster[1][0]}


def test_full_turn_builds_philosophers_not_first_team() -> None:
    reply = nl_create_or_socratic(PHILOSOPHERS_ASK) or ""
    assert "first_team" not in reply
    assert "swarm-nl-blueprint" in reply
    assert "Philosopher" in reply


def test_support_deterministic_reply_honors_the_ask() -> None:
    from swarm.blueprints.support.blueprint_support import SupportBlueprint

    bp = SupportBlueprint(blueprint_id="support")
    reply = bp._deterministic_reply(PHILOSOPHERS_ASK, "api", [])
    assert "first_team" not in reply
    assert "swarm-nl-blueprint" in reply


# --- helpers -----------------------------------------------------------------


def _create_blueprint_tool():
    """The live agent's create_blueprint tool, extracted for direct testing."""
    from swarm.blueprints.support.blueprint_support import build_create_blueprint_tool

    return build_create_blueprint_tool()

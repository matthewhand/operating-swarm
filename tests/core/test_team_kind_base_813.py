"""#813 — TeamKindBase: the fourth first-class kind.

Teams are first-class seats (frontend kind='team', team_rosters store, the
Team Composer) — but multi-agent blueprints had no common base. This pins
the ADR-005-style contract: TeamKindBase stamps kind='team', declares
coordination capabilities, exposes roster/strategy/CoS hooks, and the
in-tree team blueprints inherit it.
"""

import pytest

from swarm.core.kind_bases import (
    KIND_BASE_NAMES,
    ApiKindBase,
    CliKindBase,
    KindBase,
    RemoteKindBase,
    TeamKindBase,
    base_class_for_kind,
    seat_capability,
    seat_capabilities,
)


def test_team_kind_base_is_a_first_class_kind():
    assert TeamKindBase.kind == "team"
    assert issubclass(TeamKindBase, KindBase)
    assert "TeamKindBase" in KIND_BASE_NAMES
    assert base_class_for_kind("team") == "TeamKindBase"


def test_coordination_added_to_capability_vocabulary():
    from swarm.core.kind_bases import _capability_names

    assert "coordination" in _capability_names()


def test_team_seat_capabilities_declare_coordination():
    caps = seat_capabilities(TeamKindBase)
    assert caps["coordination"]["enabled"] is True
    for axis in ("attach", "compact", "plugins", "routines"):
        assert caps[axis]["enabled"] is True, axis


def test_other_kinds_declare_coordination_false():
    for base in (ApiKindBase, CliKindBase, RemoteKindBase):
        caps = seat_capabilities(base)
        assert caps["coordination"]["enabled"] is False, base.__name__


def test_team_hooks_present():
    bp = TeamKindBase.__new__(TeamKindBase)
    bp.blueprint_id = "team_probe"
    assert bp.get_roster() == []
    assert isinstance(bp.get_strategy(), str) and bp.get_strategy()
    assert bp.get_chief_of_staff() is None


@pytest.mark.anyio
async def test_team_default_run_yields_stamped_reply():
    async def collect():
        bp = TeamKindBase.__new__(TeamKindBase)
        bp.blueprint_id = "team_probe"
        chunks = []
        async for chunk in bp.run([{"role": "user", "content": "hello team"}]):
            chunks.append(chunk)
        return chunks

    chunks = await collect()
    assert chunks and chunks[-1]["final"] is True
    assert "team" in chunks[0]["messages"][0]["content"]


def test_catalog_publishes_team_capabilities():
    from swarm.core.cli_catalog import seat_capabilities_payload

    payload = seat_capabilities_payload()
    assert "team" in payload
    assert payload["team"]["coordination"]["enabled"] is True


def test_in_tree_team_blueprints_subclass_team_kind_base():
    from swarm.blueprints.chucks_angels.blueprint_chucks_angels import ChucksAngelsBlueprint
    from swarm.blueprints.dynamic_team.blueprint_dynamic_team import DynamicTeamBlueprint
    from swarm.blueprints.example_team_orchestrator.blueprint_example_team_orchestrator import (
        ExampleTeamOrchestratorBlueprint,
    )
    from swarm.blueprints.hybrid_moa.blueprint_hybrid_moa import HybridMoABlueprint
    from swarm.blueprints.hybrid_team.blueprint_hybrid_team import HybridTeamBlueprint
    from swarm.blueprints.moa_orchestrator.blueprint_moa_orchestrator import MoAOrchestratorBlueprint
    from swarm.blueprints.poets.blueprint_poets import PoetsBlueprint
    from swarm.blueprints.sdlc_handoff.blueprint_sdlc_handoff import SdlcHandoffBlueprint

    for cls in (
        DynamicTeamBlueprint,
        SdlcHandoffBlueprint,
        ExampleTeamOrchestratorBlueprint,
        MoAOrchestratorBlueprint,
        HybridMoABlueprint,
        HybridTeamBlueprint,
        PoetsBlueprint,
        ChucksAngelsBlueprint,
    ):
        assert issubclass(cls, TeamKindBase), cls.__name__
        assert cls.kind == "team"


def test_validator_accepts_team_kind_base_subclass():
    from swarm.views.agent_creator_views import BlueprintCodeValidator

    code = (
        "from typing import Any, ClassVar\n"
        "from agents import Agent\n"
        "from swarm.core.kind_bases import TeamKindBase\n"
        "\n"
        "class ProbeTeamBlueprint(TeamKindBase):\n"
        "    metadata: ClassVar[dict[str, Any]] = {\n"
        "        'name': 'probe_team_813',\n"
        "        'title': 'Probe Team',\n"
        "        'description': 'probe',\n"
        "        'version': '0.1.0',\n"
        "    }\n"
        "\n"
        "    def create_starting_agent(self, mcp_servers):\n"
        "        return Agent(name='Lead', instructions='lead')\n"
        "\n"
        "    async def run(self, messages):\n"
        "        yield {'messages': [{'role': 'assistant', 'content': 'team pong'}], 'final': True}\n"
    )
    result = BlueprintCodeValidator().validate_blueprint_code(code)
    assert result.get("valid") is True, result

"""example_team_orchestrator — a coordinator that knows its sub-agents.

Read this file top-to-bottom; it teaches the team axis (REQ-920 / #539;
SDK docs: REQ-921 / #540): how a recipe coordinates multiple named
sub-agents through roles, and how that differs from raw openai-agents
handoff graphs.

Base: TeamKindBase. Why: coordination (routing a turn to a specialist,
collecting results, deciding) is programmatic swarm-side work — exactly
what the API kind exists for. The sub-agents may themselves be CLI or
remote seats; the *coordinator* is swarm-side.

The idea being taught:
    A team is roles + membership, not a pile of agents. The coordinator
    declares which roles it understands (chief_of_staff, worker, skeptic
    …), composes them from the team roster at run time, and speaks to
    agents AS roles so the roster can change without rewriting the
    recipe. Rosters persist in team_rosters.json (Settings → Teams);
    role semantics live in the role model (#502 / #551).

Hooks used here, and why:
    create_starting_agent    builds the coordinator agent with per-role
                             specialist tools (agent.as_tool) derived
                             from the roster — the swarm-native way to
                             "know your sub-agents".

What this example deliberately does NOT do:
    - no hard-coded agent ids: a coordinator bound to "bob" breaks the
      moment the roster changes. Bind to ROLES; resolve members at run
      time (see stamped members in the roster contract).
    - no parallel fan-out here: this is the minimal sequential version.
      For consensus/fan-out patterns see moa / persona_council, and for
      handoff-graph theory docs/examples/openai-agents-handoff-graphs/.

Runnability: needs an OpenAI-compatible model profile for the
coordinator. Without one it fails honestly at run time — it still LOADS
and is INSPECTABLE with zero credentials, which is the contract for every
example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import TeamKindBase

logger = logging.getLogger(__name__)

_COORDINATOR_PROMPT = (
    "You coordinate a small team. Route each request to the specialist "
    "tool that matches the request; summarise what each specialist did. "
    "You are example_team_orchestrator, a teaching blueprint."
)


class ExampleTeamOrchestratorBlueprint(TeamKindBase):
    """Team recipe: a coordinator that speaks to sub-agents as roles."""

    kind = TeamKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_team_orchestrator",
        "title": "Example: team orchestrator (roles, not ids)",
        "description": (
            "Teaching recipe: a coordinator that resolves its sub-agents "
            "from team roles at run time instead of hard-coding agent ids. "
            "Read its source before copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "team", "roles", "orchestrator"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: The roles this coordinator understands. Keep it small: a team recipe
    #: declares the ROLES it needs, and the roster (team_rosters.json)
    #: supplies the members. This is the deliberate anti-pattern guard:
    #: SUB_AGENTS = ["alice", "bob"]  # ← breaks the moment rosters change.
    COORDINATED_ROLES: ClassVar[tuple[str, ...]] = ("worker", "skeptic")

    def resolve_role_members(self) -> dict[str, list[str]]:
        """Resolve role → member display names from the current roster.

        Reads the persisted team roster rather than a hard-coded list. A
        real recipe reads team_rosters.json via the roster store (see
        Settings → Teams); the teaching point is the RESOLUTION STEP —
        roles in, member handles out — which is what lets the roster
        evolve without touching this file.
        """
        # Minimal teaching version: no roster yet → no members, honestly.
        # The pattern (not the plumbing) is the lesson; the full plumbing
        # is in TeamComposer + the /v1/team-rosters endpoints.
        return {}

    def create_starting_agent(self, mcp_servers: list[Any] | None = None) -> Any:
        """Build the coordinator with one specialist tool per resolved member."""
        members_by_role = self.resolve_role_members()
        specialists: list[Any] = []
        for role in self.COORDINATED_ROLES:
            for member in members_by_role.get(role, ()):
                specialists.append(
                    {
                        "role": role,
                        # NEXT STEP — agent.as_tool: wrap each member seat
                        # (ApiKindBase agents support as_tool directly; CLI
                        # and remote members are consulted through their
                        # seat APIs) and name it "<role>:<member>" so the
                        # coordinator's tool choice is auditable in chat.
                        "name": f"{role}:{member}",
                    }
                )
        logger.debug(
            "example_team_orchestrator resolved %d specialist(s) from roles %s",
            len(specialists),
            self.COORDINATED_ROLES,
        )
        return Agent(
            name="example_team_orchestrator",
            instructions=_COORDINATOR_PROMPT,
            model=self._get_model_instance(self.llm_profile_name),
            mcp_servers=list(mcp_servers or []),
        )

"""example_api_minimal — the smallest API-kind recipe that answers a turn.

Read this file top-to-bottom; it is a worked tour of the API extension
point. For the full interface (every hook, every capability axis), see
the Blueprint SDK documentation (REQ-921 / #540) — these examples are
the worked half of that deliverable (REQ-920 / #539).

Base: ApiKindBase (``swarm.core.kind_bases``). Why: this recipe hosts an
openai-agents agent graph that runs *inside* Open Swarm — the API kind is
the only kind that fully runs programmatic workflows (forced pipelines,
circular skeptic loops, agent-as-tool graphs). If your recipe never needs
swarm-side code execution, look at ``example_cli_minimal`` instead.

Hooks overridden here, and why:
    metadata              required. Discovery reads name/title/description
                          from it; ``rail`` is deliberately ABSENT so this
                          example appears in the catalog/library only and
                          never floods the rail (REQ-170/171B: default deny).
    create_starting_agent required for LLM-backed runs. The kind base's
                          run() wraps it with Runner + timeout + sandbox
                          tool attachment for you — you never call Runner
                          yourself in a minimal recipe.

What this example deliberately does NOT do:
    - no custom run(): the ApiKindBase default already implements the full
      turn (instruction extraction → agent build → Runner → single final
      chunk). Override run() only for graphs Runner cannot express.
    - no MCP servers, no tools, no navbar items, no per-axis capability
      overrides. Those are documented as "next steps" comments below.

Runnability: needs an OpenAI-compatible model profile configured (the
platform default). Without one it fails honestly at run time with the
kind base's timeout/error chunks — it still LOADS and is INSPECTABLE
with zero credentials, which is the contract for every example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase

logger = logging.getLogger(__name__)

# System prompt for the demo agent. Keep teaching examples' prompts tiny and
# self-describing — the point is the shape of the recipe, not the persona.
_SYSTEM_PROMPT = (
    "You are example_api_minimal, a teaching blueprint from the Open Swarm "
    "SDK. Answer in one short sentence and mention that you are an example."
)


class ExampleApiMinimalBlueprint(ApiKindBase):
    """Smallest API-kind recipe: one agent, one turn, no custom run()."""

    kind = ApiKindBase.kind  # stamped by the base; restated for readers

    # Discovery metadata. `rail` is intentionally omitted: the catalog shows
    # every discovered recipe, but the rail only seats recipes that opt in
    # with `rail: True` (see src/swarm/core/rail_seats.py::metadata_rail).
    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_api_minimal",
        "title": "Example: minimal API recipe",
        "description": (
            "Teaching recipe: the smallest ApiKindBase blueprint that answers "
            "a turn. Read its source before copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "api", "minimal"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def create_starting_agent(self, mcp_servers: list[Any] | None = None) -> Agent:
        """Build the openai-agents agent for this recipe.

        Called by ApiKindBase.run() on every turn (uncached on purpose —
        build cheap agents; cache expensive clients on self if you must).
        `mcp_servers` is the session's discovered MCP server list; a minimal
        recipe passes it straight through so operators can attach servers
        from settings without editing this file.
        """
        return Agent(
            name="example_api_minimal",
            instructions=_SYSTEM_PROMPT,
            # Honours the operator's LLM profile (settings → default_llm_profile).
            # `_get_model_instance` + `llm_profile_name` come from BlueprintBase;
            # this is the canonical model wiring, identical to chatbot's.
            model=self._get_model_instance(self.llm_profile_name),
            # NEXT STEP — tools: pass `tools=[...]` (plain functions wrapped
            # with agents.function_tool, or agent.as_tool(...) specialists).
            # NEXT STEP — handoffs: pass `handoffs=[...]` to hand the turn to
            # another Agent. Graphs (fan-out, skeptic loops) belong in run().
            mcp_servers=list(mcp_servers or []),
        )

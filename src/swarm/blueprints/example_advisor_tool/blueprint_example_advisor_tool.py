"""example_advisor_tool — an agent other agents consult *as a tool*.

Read this file top-to-bottom; it teaches the agent-as-tool axis
(REQ-920 / #539; SDK docs: REQ-921 / #540): how to expose an agent's
capability as a callable tool so ANY other seat can consult it — the
"advisor" pattern (the role-model refactor #502 calls this the advisor /
research role).

Base: ApiKindBase. Why: `as_tool()` composition is openai-agents
machinery, which only API-kind seats run. A CLI or remote seat cannot
host this recipe — but CLI/remote/API agents alike can CONSUME an
advisor through their own seat surface.

The idea being taught:
    An advisor is a normal specialist agent with a narrow, well-named
    capability, published via `agent.as_tool(...)`. The calling agent
    sees ONE tool (e.g. "consult_advisor") with a description that says
    WHEN to call it. The advisor investigates (web, RAG, local store —
    whatever tools you give it) and returns a written answer. The
    caller stays in control of the conversation; the advisor never
    talks to the user directly.

What this example deliberately does NOT do:
    - no handoff: a handoff gives the turn AWAY; an advisor is consulted
      and returns. Choosing handoff vs as_tool is the whole design
      decision — see docs/examples/openai-agents-handoff-graphs/.
    - no research backend wired: the investigation tool list is a
      documented extension point, kept empty here so the example stays
      credential-free.

Runnability: needs an OpenAI-compatible model profile. Without one it
fails honestly at run time — it still LOADS and is INSPECTABLE with zero
credentials, which is the contract for every example recipe.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from agents import Agent

from swarm.core.kind_bases import ApiKindBase

logger = logging.getLogger(__name__)

_ADVISOR_PROMPT = (
    "You are a research advisor. You receive one question, investigate "
    "with the tools you have, and return a concise written answer with "
    "your sources. You never address the end user directly."
)


class ExampleAdvisorToolBlueprint(ApiKindBase):
    """Advisor recipe: a specialist published with agent.as_tool."""

    kind = ApiKindBase.kind  # stamped by the base; restated for readers

    metadata: ClassVar[dict[str, Any]] = {
        "name": "example_advisor_tool",
        "title": "Example: advisor agent-as-tool",
        "description": (
            "Teaching recipe: an advisor (research) agent other agents "
            "consult via as_tool(). The caller keeps the turn; the advisor "
            "returns an answer. Read its source before copying it."
        ),
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["example", "teaching", "advisor", "as_tool", "research"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    #: The tool name callers will see. Naming matters: callers choose tools
    #: by description, so the name + description must say WHEN to consult.
    ADVISOR_TOOL_NAME: ClassVar[str] = "consult_advisor"

    #: NEXT STEP — research backends: give the advisor real investigation
    #: tools here (web search, RAG over your store, a file index). Keep
    #: each backend behind its own tool function; the advisor's prompt
    #: should not need to change when you add one.
    ADVISOR_TOOLS: ClassVar[tuple[Any, ...]] = ()

    def build_advisor_agent(self) -> Agent:
        """The specialist itself. Narrow prompt, narrow tools, no smalltalk."""
        return Agent(
            name="example_advisor",
            instructions=_ADVISOR_PROMPT,
            model=self._get_model_instance(self.llm_profile_name),
            tools=list(self.ADVISOR_TOOLS),
        )

    def build_advisor_tool(self, calling_agent_name: str = "caller") -> Any:
        """Publish the advisor as ONE tool for a calling agent.

        The teaching point is the as_tool contract: `tool_description`
        is the ONLY thing the calling agent reads when deciding to
        consult — write it as advice to the caller, not as docs for a
        human.
        """
        advisor = self.build_advisor_agent()
        return advisor.as_tool(
            tool_name=self.ADVISOR_TOOL_NAME,
            tool_description=(
                "Consult the research advisor when a claim needs "
                "verification or background before answering. Pass one "
                "self-contained question; a written answer comes back."
            ),
        )

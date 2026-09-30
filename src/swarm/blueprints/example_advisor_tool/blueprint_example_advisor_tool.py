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

#: The same advisor when it is addressed *directly* (this seat's own turn).
#: Without it the persona is told it "never addresses the end user", which
#: invites a briefing-style reply instead of an answer.
_ADVISOR_TURN_INSTRUCTIONS = (
    "You are a research advisor being asked a question directly. Investigate "
    "with the tools you have, then answer that question in a few short "
    "sentences. State your sources. If you have no research tools, say what "
    "you know and mark anything uncertain as uncertain — do not restate the "
    "question, and do not describe yourself or your role."
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
        "author": "Operating Swarm Team",
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

    def _advisor_model(self) -> Any:
        """The seat's model instance, or ``None`` when the profile is unusable.

        ``_get_model_instance`` raises when the resolved profile has no
        credentials (an unset ``${LITELLM_API_KEY}``, a missing provider, …).
        ``create_starting_agent`` runs *outside* ``ApiKindBase.run``'s error
        handler, so letting that escape aborts the turn with no bubble at all.
        Returning ``None`` leaves the agent on the SDK default instead, and the
        turn then fails honestly through the normal path.
        """
        try:
            return self._get_model_instance(self.llm_profile_name)
        except Exception as exc:  # noqa: BLE001 — reported by the turn, not here
            logger.warning(
                "example_advisor_tool: LLM profile %r unusable (%s); "
                "leaving the agent on the SDK default",
                self.llm_profile_name,
                exc,
            )
            return None

    def build_advisor_agent(self) -> Agent:
        """The specialist itself. Narrow prompt, narrow tools, no smalltalk."""
        return Agent(
            name="example_advisor",
            instructions=_ADVISOR_PROMPT,
            model=self._advisor_model(),
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

    def create_starting_agent(self, mcp_servers: list[Any] | None = None):
        """The seat's own turn agent: the advisor, answering directly.

        Without this the seat inherits ``ApiKindBase.run``, which found no
        starting agent and fell through to its final
        ``"Agent example_advisor_tool ready."`` banner. The sweep read that
        banner as a reply that was not one — the classic symptom of a recipe
        that teaches ``as_tool`` composition but forgets the entry point.

        An advisor is normally *consulted*, not addressed, so this is also the
        honest minimal wiring: the advisor answers the turn itself, and
        :meth:`build_advisor_tool` stays available for callers that want the
        ``as_tool`` contract demonstrated from a coordinator of their own.
        """
        advisor = self.build_advisor_agent()
        if mcp_servers:
            advisor.mcp_servers = list(mcp_servers)
        # Answer the user's question directly instead of narrating a brief.
        advisor.instructions = _ADVISOR_TURN_INSTRUCTIONS
        return advisor

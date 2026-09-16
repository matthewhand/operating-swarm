"""Support — onboarding guide (role=support).

A single discoverable blueprint. The coordinator uses openai-agents
``as_tool`` specialists (product guide + blueprint coder). It does **not**
spawn extra Grok / OMB / Rakazo CLI seats.
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as fusion
from swarm.blueprints.common.support_blueprint import (
    CLICK_BUBBLE_TO_EDIT,
    resolve_session_kind,
    support_turn_context,
    support_turn_reply,
)
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.support_context import (
    create_paths_markdown,
    live_context,
    model_context_block,
    quickstart_section,
)
from swarm.core.support_nl_blueprint import (
    create_nl_blueprint,
    nl_create_or_socratic,
    wants_code_reveal,
)

logger = logging.getLogger(__name__)

SUPPORT_INSTRUCTIONS = """
You are Support, Open Swarm's first-run journey onboarder (role=support).
Fixture: ONBOARD_JOURNEY_CLI_API_REMOTE
Fixture: SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON

Goals:
- Guide the open-swarm journey in natural language + kickstart chips
  (Create a team, Create a BA → Engineer → Tester workflow, Add a remote,
  Wire a CLI) — not a form maze.
- Happy path: underspecified “create a team” → one Socratic ```question
  (purpose/shape). Read get_quickstart(section="team") and list_create_paths
  (ADR-005 kind bases) before drafting. Specified asks (BA → Engineer →
  Tester, skeptic loop) may draft immediately. Call create_blueprint_from_nl
  only after you know the shape — it returns a **draft** card, not a rail
  seat. They do **not** write Python. Do **not** dump a ```python fence
  unless they ask to view / edit code.
- The card CTAs are **Add as agent** (rail) and **Save as blueprint**
  (library). Do not tell them to Open in chat.
- Under the hood a team is a Python ApiKindBase class (ADR-005). Say that
  briefly. Code stays hidden; the UI offers View / edit code.
- Help them create a local team: personas, optional Chief of Staff (CoS).
- Power-user path only: if they ask to write or see the Python, consult
  blueprint_coder and show a fenced ```python block (ApiKindBase /
  CliKindBase / RemoteKindBase — not raw BlueprintBase for most cases).
- Help them add a CLI agent and list models the host CLI reports.
- Help them connect remotes (Hermes, OpenMousBot, Herdr, nested swarm)
  to setups they already have. Env var names only — never plaintext secrets.
- Explain the one-pane bridge: task here across CLI ↔ API ↔ remotes.
- Stay honest about constraints: API threads are editable here; CLI and
  remote sessions live outside Open Swarm (no click-to-edit).
- When inference is not configured, point at QUICKSTART §4 and the Settings
  overlay /profiles/ — never invent credentials, ports, or a live host.

Tools:
- create_blueprint_from_nl: draft a team/workflow from NL (no user Python;
  persist is Add as agent / Save as blueprint on the card).
- get_live_context: current agents + inference status.
- get_quickstart: existing quickstart excerpts (inference / team / blueprint / run).
- list_create_paths: in-product paths to create agents, blueprints, and teams.
- create_agent / archive_agent / restore_agent / list_archived_agents:
  grow or trim the roster (REQ-154). Safe defaults; env var names only;
  no secrets. Archive is a soft-delete (~30 day restore, then purge).
- consult_product_guide: specialist (as_tool) for product Q&A.
- consult_blueprint_coder: specialist (as_tool) for drafting blueprint Python
  only when they ask to view / edit / write code.

Do not shell out to grok, omb, or rakazo. Stay on this Support seat.
"""

PRODUCT_GUIDE_INSTRUCTIONS = """
You are the Support product guide. Answer from Open Swarm's existing
quickstart and in-product overlays (/settings/, /profiles/, /teams/launch/,
/blueprint-library/, /agent-creator/). Prefer quoting QUICKSTART.md over
inventing steps. Onboard the journey: create a team, add a remote
(Hermes / OpenMousBot / Herdr), wire a CLI and list models, then bridge
CLI ↔ API ↔ remotes in one pane. Never invent secrets or a live host.
"""

BLUEPRINT_CODER_INSTRUCTIONS = """
You are the Support blueprint coder. Help the user write a kind-base
subclass: ApiKindBase (handoff / as-tool graphs), CliKindBase (native CLI
session), or RemoteKindBase (Hermes / OpenMousBot / Herdr). BlueprintBase
is the low-level parent — do not invent a fourth harness from the raw base.
Always return a complete, copy-pasteable ```python fenced block.
Use openai-agents Agent + function_tool / as_tool (handoff-as-tool), not
extra CLI seats. Keep the example small and honest. ADR-005 / REQ-159.
"""

STARTER_BLUEPRINT_PYTHON = '''```python
from typing import Any, ClassVar

from agents import Agent, function_tool

from swarm.core.kind_bases import ApiKindBase


class FirstTeamBlueprint(ApiKindBase):
    """Minimal coordinator + specialist via Agent.as_tool (no extra CLI seats)."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "first_team",
        "title": "First Team",
        "description": "A starter coordinator that delegates to one specialist.",
        "version": "0.1.0",
        "tags": ["team", "starter"],
    }

    def create_starting_agent(self, mcp_servers):
        specialist = Agent(
            name="Specialist",
            instructions="Do the concrete work the coordinator delegates.",
        )
        coordinator = Agent(
            name="Coordinator",
            instructions="Plan the work, then call consult_specialist.",
            tools=[],
        )
        if hasattr(specialist, "as_tool"):
            coordinator.tools.append(
                specialist.as_tool(
                    tool_name="consult_specialist",
                    tool_description="Delegate implementation to the specialist.",
                )
            )
        return coordinator
```'''


def _function_tool(fn):
    """Decorate when openai-agents is available; keep a callable otherwise."""
    try:
        from agents import function_tool as _ft

        return _ft(fn)
    except Exception:
        fn.name = getattr(fn, "__name__", "tool")
        return fn


@_function_tool
def get_live_context() -> str:
    """Current agents list and whether inference is configured. No secrets."""
    import json

    return json.dumps(live_context(), indent=2, default=str)


@_function_tool
def get_quickstart(section: str = "inference") -> str:
    """Return an excerpt from docs/QUICKSTART.md (inference, team, blueprint, run)."""
    excerpt = quickstart_section(section)
    if excerpt:
        return excerpt
    return (
        f"No QUICKSTART.md excerpt for '{section}'. "
        "Valid sections: inference, team, blueprint, run. "
        "See docs/QUICKSTART.md in the repo."
    )


@_function_tool
def list_create_paths() -> str:
    """In-product paths to create agents, blueprints, and teams."""
    return create_paths_markdown()


@_function_tool
def create_blueprint_from_nl(request: str) -> str:
    """Draft a team/workflow from natural language. User does not write Python.

    Does not persist. The chat card offers Add as agent / Save as blueprint.
    """
    created = create_nl_blueprint(request, persist=False)
    return created.user_reply(include_code_fence=False)


class SupportBlueprint(BlueprintBase):
    """Onboarding Support agent. Discoverable; metadata.role = support."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "support",
        "title": "Support",
        "description": "Onboarding. First team.",
        "version": "1.0.0",
        "author": "Open Swarm Team",
        "tags": ["support", "onboarding", "quickstart"],
        "role": "support",
        "rail": True,
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def system_prompt(self, messages: list[dict[str, Any]] | None = None) -> str:
        """Skill-injected system/prompt for this turn (includes the fixture)."""
        params = getattr(self, "_params", {}) or {}
        session_kind = resolve_session_kind(params, messages)
        live = model_context_block(live_context())
        return support_turn_context(session_kind, live)

    def create_starting_agent(self, mcp_servers=None):  # noqa: ARG002
        """Coordinator + as_tool specialists (no Grok/OMB/Rakazo seats)."""
        try:
            from agents import Agent
        except ImportError as exc:  # pragma: no cover - env without SDK
            raise RuntimeError("openai-agents is required for Support") from exc

        product_guide = Agent(
            name="ProductGuide",
            instructions=PRODUCT_GUIDE_INSTRUCTIONS.strip(),
        )
        blueprint_coder = Agent(
            name="BlueprintCoder",
            instructions=BLUEPRINT_CODER_INSTRUCTIONS.strip(),
        )
        tools: list[Any] = [
            get_live_context,
            get_quickstart,
            list_create_paths,
            create_blueprint_from_nl,
        ]
        coordinator = Agent(
            name="Support",
            instructions=SUPPORT_INSTRUCTIONS.strip(),
            tools=list(tools),
        )
        try:
            coordinator.tools = list(coordinator.tools or [])
            if hasattr(product_guide, "as_tool"):
                coordinator.tools.append(
                    product_guide.as_tool(
                        tool_name="consult_product_guide",
                        tool_description=(
                            "Ask the product-guide specialist about Open Swarm, "
                            "quickstarts, and in-product paths."
                        ),
                    )
                )
            if hasattr(blueprint_coder, "as_tool"):
                coordinator.tools.append(
                    blueprint_coder.as_tool(
                        tool_name="consult_blueprint_coder",
                        tool_description=(
                            "Ask the blueprint-coder specialist to draft Python "
                            "for an ApiKindBase / CliKindBase / RemoteKindBase team."
                        ),
                    )
                )
        except Exception as exc:  # pragma: no cover
            logger.debug("Support as_tool wiring skipped: %s", exc)
        return coordinator

    def _deterministic_reply(
        self,
        user_text: str,
        session_kind: str = "api",
        messages: list[dict[str, Any]] | None = None,
    ) -> str:
        if session_kind in ("cli", "remote"):
            return support_turn_reply(None, session_kind)
        if not user_text:
            return create_paths_markdown()
        designed = nl_create_or_socratic(
            user_text,
            messages,
            include_code_fence=wants_code_reveal(user_text),
        )
        if designed:
            return designed
        lowered = user_text.lower()
        parts = [user_text]
        if "create a team" in lowered or "first team" in lowered:
            parts.extend(
                [
                    "",
                    "A local team is personas on one roster. Optional Chief of Staff "
                    "(CoS) talks across teams. Chat stays the main view — New team is "
                    "an overlay, not a Settings maze. Happy path: ask Support; you do "
                    "not write Python.",
                ]
            )
        if "add a remote" in lowered or "connect a remote" in lowered:
            parts.extend(
                [
                    "",
                    "Remotes (Hermes, OpenMousBot, Herdr) attach an existing setup. "
                    "Settings → Remotes is + Add remote. Env var names only — no "
                    "plaintext secrets. The live remote session stays outside Open Swarm.",
                ]
            )
        if "wire a cli" in lowered or "add a cli" in lowered:
            parts.extend(
                [
                    "",
                    "A CLI agent wraps a host CLI you already have. Swarm can list "
                    "models that CLI reports. The live CLI session stays outside "
                    "Open Swarm — no click-to-edit.",
                ]
            )
        if wants_code_reveal(user_text) or any(
            word in lowered for word in ("blueprint", "code", "python", "write")
        ):
            parts.extend(["", STARTER_BLUEPRINT_PYTHON])
        parts.extend(["", create_paths_markdown()])
        return "\n".join(parts)

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        params = getattr(self, "_params", {}) or {}
        session_kind = resolve_session_kind(params, messages)
        user_text = fusion.render_prompt(messages).strip()
        # Chat-load / empty turn and test mode never hit a live model.
        if os.environ.get("SWARM_TEST_MODE") or not user_text:
            yield fusion.message_chunk(
                self._deterministic_reply(user_text, session_kind, messages),
                final=True,
            )
            return

        injected = [
            {"role": "system", "content": self.system_prompt(messages)},
            *list(messages or []),
        ]
        try:
            from agents import Runner

            agent = self.create_starting_agent(kwargs.get("mcp_servers") or [])
            result = await Runner.run(agent, fusion.render_prompt(injected))
            response = getattr(result, "final_output", None) or str(result)
            text = str(response)
            if session_kind in ("cli", "remote") and CLICK_BUBBLE_TO_EDIT in text.lower():
                text = support_turn_reply(messages, session_kind)
            yield fusion.message_chunk(text, final=True)
        except Exception as exc:
            logger.warning("Support LLM path failed; falling back to welcome: %s", exc)
            fallback = self._deterministic_reply(user_text, session_kind, messages)
            yield fusion.message_chunk(fallback, final=True)

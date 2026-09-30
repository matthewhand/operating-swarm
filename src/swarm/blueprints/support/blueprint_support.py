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
from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.blueprints.common.support_blueprint import (
    CLICK_BUBBLE_TO_EDIT,
    resolve_session_kind,
    support_turn_context,
    support_turn_reply,
)
from swarm.core.blueprint_base import BlueprintBase, apply_agent_model_defaults
from swarm.core.support_context import (
    create_paths_markdown,
    live_context,
    model_context_block,
    quickstart_section,
)
from swarm.core.support_interactive_create import (
    interactive_create_or_socratic,
    reply_for_routine_request,
    reply_for_seating_request,
)
from swarm.core.support_nl_blueprint import (
    create_nl_blueprint,
    synthesize_from_roster_payload,
    wants_code_reveal,
)

logger = logging.getLogger(__name__)

SUPPORT_INSTRUCTIONS = """
You are Support, Operating Swarm's first-run journey onboarder (role=support).
Fixture: ONBOARD_JOURNEY_CLI_API_REMOTE
Fixture: SUPPORT_NL_BLUEPRINT_NO_USER_PYTHON
Fixture: SUPPORT_INTERACTIVE_CREATE_1373

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
- Routines: underspecified “create a routine” → one Socratic ```question.
  Specified asks draft a **Add routine** card. A GitHub merge routine needs
  an owner/repo before the card. A github.com URL counts as owner/repo.
  An explicit merge wins over “daily” or “weekly” inside the instruction;
  a passing “github” mention still loses to a daily or weekly schedule.
  Hourly still wins over an explicit merge. An owner/repo after “for”
  is the repository, not the agent. `git@github.com:owner/repo` and
  `api.github.com/repos/owner/repo` are the repository too, not agent
  `git`. A gist URL is not a repository.
  Persist uses the existing routines API
  (`POST /v1/agents/<id>/routines/`). Do not invent a second store.
- Team/group seating: “seat Ada on office”, “put Ada on the office team”,
  or “put Ada in the office team” drafts a **Seat on team** / **Create
  group** card. Do not treat “create a group chat”, “put X in Y”
  without a team, group, or roster, or a non-roster noun after
  team/group/roster (“team folder”, “group chat”, “team standup”) as
  seating. “please”, “today”, “now”, “tomorrow”, and “and” still seat.
  A polite word is not the roster name, and “with Pat please” keeps Pat.
  Persist uses the
  existing team-roster API (`POST/PUT /v1/team-rosters/`).
- Under the hood a team is a Python ApiKindBase class (ADR-005). Say that
  briefly. Code stays hidden; the UI offers View code.
- Help them create a local team: personas, optional Chief of Staff (CoS).
- Power-user path only: if they ask to write or see the Python, consult
  blueprint_coder and show a fenced ```python block (ApiKindBase /
  CliKindBase / RemoteKindBase — not raw BlueprintBase for most cases).
- Help them add a CLI agent and list models the host CLI reports.
- Help them connect remotes (Hermes, OpenMousBot, Herdr, nested swarm)
  to setups they already have. Env var names only — never plaintext secrets.
- Explain the one-pane bridge: task here across CLI ↔ API ↔ remotes.
- Stay honest about constraints: API threads are editable here; CLI and
  remote sessions live outside Operating Swarm (no click-to-edit).
- When inference is not configured, point at QUICKSTART §4 and the Settings
  overlay /profiles/ — never invent credentials, ports, or a live host.

Tools:
- create_blueprint_from_nl: draft a team/workflow from NL (no user Python;
  persist is Add as agent / Save as blueprint on the card).
- create_routine_from_nl: draft a scheduled routine from NL (persist is
  Add routine on the card).
- seat_agents_on_team: draft team/group seating from NL (persist is Seat
  on team / Create group on the card).
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
You are the Support product guide. Answer from Operating Swarm's existing
quickstart and in-product overlays (/chat?settings=llm-profiles, /profiles/, /teams/launch/,
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


def build_create_blueprint_tool():
    """#750: the create_blueprint tool handler, unwrapped for direct testing.

    The coordinator registers ``_create_blueprint_from_json`` (below) as the
    LLM-facing tool; tests call this raw handler with a parsed payload dict.
    """
    return synthesize_from_roster_payload


@_function_tool
def _create_blueprint_from_json(spec_json: str) -> str:
    """Create a team blueprint from the discussion's design.

    Pass a JSON object: {"title": str, "description": str,
    "roster": [{"name": str, "instructions": str}],
    "edges": [["<member name>", "<member name>"]]}.
    Edges must reference roster names; a sequential chain reads
    [[A, B], [B, C]]. This validates the design, generates the ApiKindBase
    class, persists the seat so it is immediately usable in chat, and
    returns the confirmation card with its /chat link. You never write
    Python — design the roster and graph from what the user asked for.
    """
    import json

    try:
        payload = json.loads(spec_json)
    except Exception:
        return "Error: spec_json must be valid JSON."
    if not isinstance(payload, dict):
        return "Error: spec_json must be a JSON object with title/roster/edges."
    return synthesize_from_roster_payload(payload)


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


@_function_tool
def create_routine_from_nl(request: str) -> str:
    """Draft a routine from natural language. Persist is Add routine on the card.

    Uses the existing per-agent routines store. Does not invent a second scheduler.
    """
    return reply_for_routine_request(request)


@_function_tool
def seat_agents_on_team(request: str) -> str:
    """Draft team/group seating from natural language.

    Persist is Seat on team / Create group on the card. Writes team_rosters
    via the existing /v1/team-rosters/ API — not a new Python class.
    """
    return reply_for_seating_request(request)


@_function_tool
def list_config_targets() -> str:
    """Survey every configurable domain: providers, settings, MCP servers,
    teams, blueprints. Read-only; secret values redacted to env-var names.
    Call this before update_config to discover target ids.
    """
    from swarm.core.support_config import list_config_targets as _list

    return _list()


@_function_tool
def update_config_tool(domain: str, target_id: str, patch_json: str) -> str:
    """Apply a configuration write in one of the listed domains.

    Args:
        domain: "provider" | "settings" | "mcp_servers" | "teams" | "blueprints".
        target_id: Profile name, setting key, server id, team or blueprint id.
        patch_json: JSON object of fields to merge, e.g.
            {"base_url": "https://api.example.com/v1", "model": "gpt-5-mini"}.
            For settings, {"value": <any>}.

    Writes that touch the ACTIVE provider powering this session are
    intercepted: they return a denial explaining the approval requirement
    instead of executing. Never claim a write succeeded when the result
    reports denied or an error.
    """
    import json as _json

    try:
        patch = _json.loads(patch_json)
    except Exception:
        return "Error: patch_json must be valid JSON."
    if not isinstance(patch, dict):
        return "Error: patch_json must be a JSON object."
    from swarm.core.support_config import (
        active_provider_descriptor,
    )
    from swarm.core.support_config import (
        update_config as _update,
    )

    result = _update(
        domain=domain,
        target_id=target_id,
        patch=patch,
        active=active_provider_descriptor(),
    )
    return _json.dumps(result, indent=2, default=str)


class SupportBlueprint(BlueprintBase):
    """Onboarding Support agent. Discoverable; metadata.role = support."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "support",
        "title": "Support",
        "description": "Onboarding. First team.",
        "version": "1.0.0",
        "author": "Operating Swarm Team",
        "tags": ["support", "onboarding", "quickstart"],
        "role": "support",
        "rail": True,
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def system_prompt(self, messages: list[dict[str, Any]] | None = None) -> str:
        """Skill-injected system/prompt for this turn (includes the fixture).

        #854: appends the self-preservation directives and the active
        inference identifier so Support always knows which provider this
        session runs on — and what modifying it would do.
        """
        params = getattr(self, "_params", {}) or {}
        session_kind = resolve_session_kind(params, messages)
        live = model_context_block(live_context())
        base = support_turn_context(session_kind, live)
        try:
            from swarm.core.support_config import (
                SELF_PRESERVATION_DIRECTIVES,
                active_inference_identifier,
            )

            return (
                f"{base}\n\n{SELF_PRESERVATION_DIRECTIVES}"
                f"\n\n{active_inference_identifier(self)}"
            )
        except Exception:  # pragma: no cover - guardrail block is additive
            logger.debug("support_config block unavailable", exc_info=True)
            return base

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
            create_routine_from_nl,
            seat_agents_on_team,
            list_config_targets,
            update_config_tool,
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
                            "Ask the product-guide specialist about Operating Swarm, "
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
            # #750: the LLM designs teams from the discussion itself — this
            # tool executes the design (validate → generate → persist).
            try:
                coordinator.tools.append(_create_blueprint_from_json)
            except Exception as exc:  # pragma: no cover
                logger.debug("create_blueprint tool wiring skipped: %s", exc)
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
        designed = interactive_create_or_socratic(
            user_text,
            messages,
            include_code_fence=wants_code_reveal(user_text),
        )
        if designed:
            return designed
        lowered = user_text.lower()
        # Never open with the user's own words. This reply is the no-model
        # fallback, and a bubble that starts by restating the prompt reads as
        # an echo; the agent sweep scored exactly that as a 1.9s "answer".
        parts = ["Here are the in-product paths I can help with:"]
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
                    "plaintext secrets. The live remote session stays outside Operating Swarm.",
                ]
            )
        if "wire a cli" in lowered or "add a cli" in lowered:
            parts.extend(
                [
                    "",
                    "A CLI agent wraps a host CLI you already have. Swarm can list "
                    "models that CLI reports. The live CLI session stays outside "
                    "Operating Swarm — no click-to-edit.",
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
            # #737: every Agent built here is bare, so the SDK would fall back to
            # its hardcoded default model. Against a LiteLLM / non-OpenAI profile
            # that is a 400 (`Invalid model name passed in model=gpt-4.1`) — the
            # turn dies before it starts. Pin the framework's resolved chat model
            # first, exactly as ApiKindBase.run does, so Support answers on the
            # profile the seat actually resolved.
            apply_agent_model_defaults(agent)
            result = await Runner.run(agent, fusion.render_prompt(injected))
            response = getattr(result, "final_output", None) or str(result)
            text = str(response)
            if session_kind in ("cli", "remote") and CLICK_BUBBLE_TO_EDIT in text.lower():
                text = support_turn_reply(messages, session_kind)
            yield fusion.message_chunk(text, final=True)
        except Exception as exc:
            # The old fallback was `_deterministic_reply`, which opens with the
            # user's own words and then dumps the create-paths chrome. The sweep
            # read that as a 1.9s answer that was really a prompt echo. A failed
            # turn must say it failed.
            logger.warning("Support LLM path failed: %s", exc)
            yield unavailable.cannot_answer_chunk(
                self.blueprint_id or "support",
                why=(
                    f"the onboarding model turn raised "
                    f"{type(exc).__name__}: {str(exc)[:200]}"
                ),
                remedy=(
                    "check the seat's LLM profile (Settings → LLM profiles) has a "
                    "model and base URL the provider accepts, then send the "
                    "message again"
                ),
                backends=["support"],
            )

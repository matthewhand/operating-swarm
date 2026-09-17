"""Concrete Role adapters (REQ-852 Phase 1) — behavior-preserving.

Each subclass wraps an existing module (``tool_gate``, ``skeptic``,
``suggestions``, ``team_rosters``); delegation imports happen inside methods
so this module stays a leaf (``agent_roles`` imports it at module level to
populate the registry and derive the legacy tables).

Phase 1 keeps the runtime engine untouched: hooks expose the seams Phase 2
will migrate consumer call sites onto. Existing modules and their tests are
the behavior lock.

Adding a role = one class here + ``register_role``; badges, CSS classes,
aliases, mechanisms, and the ``/v1/roles/`` descriptor all derive from the
registry (no FE table edits).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, ClassVar

from swarm.core.roles.base import Role, RoleContext, RoleOutcome
from swarm.core.roles.registry import register_role

__all__ = [
    "DefaultRole",
    "SupportRole",
    "GateRole",
    "SkepticRole",
    "AdvisorRole",
    "ChiefOfStaffRole",
    "EngineerRole",
    "SuggestionsRole",
]


@register_role
class DefaultRole(Role):
    """Ordinary worker (no badge). Metadata only — hooks are no-ops."""

    id: ClassVar[str] = "default"
    aliases: ClassVar[tuple[str, ...]] = ("default", "none", "worker", "agent", "coordinator")
    label: ClassVar[str] = ""
    badge: ClassVar[str | None] = None
    mechanism: ClassVar[str] = "none"
    mechanism_detail: ClassVar[str] = (
        "Worker agent executing standard conversational turns without role overrides."
    )


@register_role
class SupportRole(Role):
    """Support seat (REQ-7). Lifecycle-capable metadata; hooks are no-ops."""

    id: ClassVar[str] = "support"
    aliases: ClassVar[tuple[str, ...]] = ("support", "helper")
    label: ClassVar[str] = "Support"
    badge: ClassVar[str | None] = "Support"
    mechanism: ClassVar[str] = "implement"
    mechanism_detail: ClassVar[str] = (
        "Socratic support and agent lifecycle manager (REQ-7, REQ-154)."
    )


@register_role
class GateRole(Role):
    """Tool-call classifier intercepting execution requests before execution.

    Delegates to ``tool_gate.wrap_tools_with_gate`` (fail-open when unwired)
    and ``tool_gate.attach_gate_as_tool``. The veto path lives inside the
    wrappers at call time, matching today's behavior.
    """

    id: ClassVar[str] = "gate"
    aliases: ClassVar[tuple[str, ...]] = ("gate", "tool_gate", "tool-gate", "toolgate")
    label: ClassVar[str] = "Gate"
    badge: ClassVar[str | None] = "Gate"
    mechanism: ClassVar[str] = "intercept"
    mechanism_detail: ClassVar[str] = (
        "Tool-call classifier intercepting execution requests before execution."
    )

    def wrap_tool_calls(
        self, ctx: RoleContext, calls: Sequence[Any]
    ) -> Sequence[Any] | RoleOutcome:
        from swarm.core.tool_gate import wrap_tools_with_gate

        gate = ctx.params.get("gate")
        classify_fn = ctx.params.get("classify_fn")
        if gate is None and classify_fn is None:
            return calls  # default-open: unwired → unchanged
        return wrap_tools_with_gate(
            list(calls),
            gate=gate,
            classify_fn=classify_fn,
            invoke_fn=ctx.params.get("invoke_fn"),
            elicit_fn=ctx.params.get("elicit_fn"),
            trace=ctx.trace or None,
        )

    def attach_as_tool(self, coordinator: Any, gate: Any) -> Any:  # noqa: ARG002 (phase-2 seam)
        """Phase-2 seam for ``attach_gate_as_tool`` (behavior-preserving)."""
        from swarm.core.tool_gate import attach_gate_as_tool

        return attach_gate_as_tool(coordinator, gate)


@register_role
class SkepticRole(Role):
    """Post-run reviewer issuing bounded retry directives.

    ``run_bounded`` delegates to ``skeptic.run_with_skeptic`` (bounded
    retries, default 2). ``on_turn_end`` maps a ``SkepticRunResult`` to a
    ``RoleOutcome.retry_directive`` — the seam Phase 2 wires into the
    consumer turn loop.
    """

    id: ClassVar[str] = "skeptic"
    aliases: ClassVar[tuple[str, ...]] = ("skeptic", "reviewer")
    label: ClassVar[str] = "Skeptic"
    badge: ClassVar[str | None] = "Skeptic"
    mechanism: ClassVar[str] = "parse"
    mechanism_detail: ClassVar[str] = (
        "Post-run output validator performing bounded retries on failures."
    )

    async def run_bounded(self, **kwargs: Any) -> Any:
        from swarm.core.skeptic import run_with_skeptic

        return await run_with_skeptic(**kwargs)

    def on_turn_end(self, ctx: RoleContext, result: Any) -> RoleOutcome:  # noqa: ARG002 (seam: ctx unused in phase 1)
        findings = getattr(result, "findings", None)
        accomplished = getattr(result, "accomplished", None)
        if accomplished is False and findings:
            return RoleOutcome(retry_directive=str(findings[-1]))
        return RoleOutcome()


@register_role
class AdvisorRole(Role):
    """One concise follow-up advice note after a completed turn.

    Phase 1 carries the resolution seam (``resolve_advisor`` →
    ``team_rosters.advisor_blueprint_for_agent``); the consumer still owns
    emission until the Phase-2 migration onto this hook. ``as_tool``/research
    backends (web / RAG / local store) land in Phase 4 (ambition d).
    """

    id: ClassVar[str] = "advisor"
    aliases: ClassVar[tuple[str, ...]] = ("advisor", "adviser", "mentor")
    label: ClassVar[str] = "Advisor"
    badge: ClassVar[str | None] = "Advisor"
    mechanism: ClassVar[str] = "parse"
    mechanism_detail: ClassVar[str] = (
        "Reviews a completed turn and posts one concise follow-up advice note."
    )

    def resolve_advisor(self, team_id: Any, agent_id: Any) -> str | None:
        from swarm.core.team_rosters import advisor_blueprint_for_agent

        return advisor_blueprint_for_agent(team_id, agent_id)


@register_role
class ChiefOfStaffRole(Role):
    """Orchestrator seat with cross-team scope (REQ-28).

    The only ``allowed_everywhere`` role. Lifecycle permission helpers stay
    in ``agent_roles`` this phase (they cover Support too).
    """

    id: ClassVar[str] = "chief_of_staff"
    aliases: ClassVar[tuple[str, ...]] = (
        "chief_of_staff",
        "chief-of-staff",
        "chiefofstaff",
        "cos",
        "chief",
    )
    label: ClassVar[str] = "CoS"
    badge: ClassVar[str | None] = "CoS"
    allowed_everywhere: ClassVar[bool] = True
    mechanism: ClassVar[str] = "intercept"
    mechanism_detail: ClassVar[str] = (
        "Orchestrator seat with cross-team communication and mailbox-wide scope (REQ-28)."
    )


@register_role
class EngineerRole(Role):
    """Implementer seat (software dev / Chatty). Metadata only."""

    id: ClassVar[str] = "engineer"
    aliases: ClassVar[tuple[str, ...]] = ("engineer", "eng")
    label: ClassVar[str] = "Engineer"
    badge: ClassVar[str | None] = "Engineer"
    mechanism: ClassVar[str] = "implement"
    mechanism_detail: ClassVar[str] = (
        "Implementer seat for software development, test authoring, and file editing."
    )


@register_role
class SuggestionsRole(Role):
    """Quick-select follow-up prompt chips after a turn (REQ-85).

    ``as_tool`` resolves the wired suggestions specialist and delegates to
    ``suggestions.attach_suggestions_as_tool`` (fail-soft: no coordinator /
    no specialist → no tool).
    """

    id: ClassVar[str] = "suggestions"
    aliases: ClassVar[tuple[str, ...]] = ("suggestions", "suggestion", "suggest")
    label: ClassVar[str] = "Suggest"
    badge: ClassVar[str | None] = "Suggest"
    mechanism: ClassVar[str] = "parse"
    mechanism_detail: ClassVar[str] = (
        "Generates quick-select follow-up prompt chips after model turns (REQ-85)."
    )

    def specialist_for(self, ctx: RoleContext) -> Any | None:
        from swarm.core.agent_roles import ROLE_SUGGESTIONS, find_role_agent

        agents = ctx.params.get("agents") or getattr(ctx.coordinator, "_agents", None)
        if not agents:
            return None
        return find_role_agent(agents, ROLE_SUGGESTIONS)

    def as_tool(self, ctx: RoleContext) -> Any | None:
        from swarm.core.suggestions import attach_suggestions_as_tool

        specialist = self.specialist_for(ctx)
        if ctx.coordinator is None or specialist is None:
            return None
        attach_suggestions_as_tool(ctx.coordinator, specialist)
        return specialist

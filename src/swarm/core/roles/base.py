"""Role base class (REQ-852 / #206) — roles as behavior, not parallel tables.

A *role* is behavior attached to a seat that shapes the inputs/outputs of the
agent (or the user's message) flowing through it. Behavior previously lived
scattered across modules with per-role invocation shapes; here it gets one
contract with three injection points:

* ``on_turn_start(ctx)`` — before the agent runs (e.g. capability manifests)
* ``wrap_tool_calls(ctx, calls)`` — intercept before tool execution (gate)
* ``on_turn_end(ctx, result)`` — after the agent runs (skeptic, suggestions,
  advisor)

Plus ``as_tool(ctx)`` for roles the calling agent invokes explicitly
(advisor/research backends, ambition d).

Defaults are no-ops: worker roles (``default``, ``support``, ``engineer``)
carry metadata only and cost nothing. Concrete subclasses in this package
wrap the existing modules (``tool_gate``, ``skeptic``, ``suggestions``,
``team_rosters``) — behavior-preserving; current tests are the lock.
"""

from __future__ import annotations

from abc import ABC
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar

__all__ = [
    "ROLE_CSS_CLASS_PREFIX",
    "RoleContext",
    "RoleOutcome",
    "Role",
    "WorkerRole",
    "VerifierRole",
    "AdvisoryRole",
    "SupervisorRole",
    "Verdict",
]

# Sidepane badge CSS contract (REQ-67). ``agent_roles`` re-exports this as
# ``ROLE_CSS_CLASS_PREFIX`` so existing imports keep working.
ROLE_CSS_CLASS_PREFIX = "os-agent-role-"


@dataclass
class RoleContext:
    """Everything a role hook may need for one turn.

    ``source`` marks whose message enters the pipeline this turn —
    ``"user"`` or ``"agent"`` — so a role can also process user-sent input,
    not only agent output (e.g. advisor annotating the user's message).
    """

    coordinator: Any = None  # blueprint instance (roster access)
    agent: Any = None  # seat carrying the role
    config: dict[str, Any] = field(default_factory=dict)
    messages: list[dict[str, Any]] = field(default_factory=list)
    params: dict[str, Any] = field(default_factory=dict)
    source: str = "agent"  # "user" | "agent"
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class RoleOutcome:
    """What a role wants to happen at its injection point.

    All fields are additive and optional:

    * ``status_note`` — non-persistent status chrome (advisor #181 pattern)
    * ``messages`` — persistent appended messages
    * ``tool`` — a tool spec exposed to the calling agent (ambition d)
    * ``retry_directive`` — ask the calling agent to revise (ambition c,
      bounded by the skeptic loop's retry budget)
    * ``veto`` — block a pending tool call (gate path)
    """

    status_note: str | None = None
    messages: list[dict[str, Any]] | None = None
    tool: Any | None = None
    retry_directive: str | None = None
    veto: bool = False


class Role(ABC):  # noqa: B024 (intentional interface base: hooks default to no-ops)
    """Base class for all agent roles.

    Class-level attributes are the single source of truth for badges, CSS
    classes, aliases, and the descriptor served by ``/v1/roles/``.
    Subclasses set ``id`` at minimum; the registry derives the rest.

    The behavioral taxonomy (#814) layers four sub-bases between ``Role``
    and the concrete adapters: ``WorkerRole`` (ordinary turns),
    ``VerifierRole`` (bounded yes/no review), ``AdvisoryRole`` (pure
    status/chrome), and ``SupervisorRole`` (lifecycle + topology authority
    over other seats).
    """

    id: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    label: ClassVar[str] = ""
    css_class: ClassVar[str] = ""
    allowed_everywhere: ClassVar[bool] = False
    badge: ClassVar[str | None] = None
    mechanism: ClassVar[str] = "none"
    mechanism_detail: ClassVar[str] = ""
    role_category: ClassVar[str] = "worker"

    def describe(self) -> dict[str, Any]:
        """Descriptor for ``/v1/roles/`` — the single source for settings."""
        return {
            "name": self.id,
            "label": self.badge or self.label,
            "aliases": list(self.aliases),
            "allow_all": self.allowed_everywhere,
            "mechanism": self.mechanism,
            "mechanism_detail": self.mechanism_detail,
            "css_class": self.css_class or f"{ROLE_CSS_CLASS_PREFIX}{self.id}",
            "category": self.role_category,
        }

    # ------------------------------------------------------------- Mode B

    def execute_as_role(
        self,
        ctx: RoleContext,  # noqa: ARG002 (seam: subclasses may read params)
        payload: dict[str, Any] | Any,
    ) -> list[dict[str, str]]:
        """Mode B invocation engine (ADR-010 / #814).

        When other agents invoke a role agent via ``as_tool`` or handoff,
        the model context is *strictly* ``[execution_prompt, caller_context,
        latest_message]`` — never the callee's private Mode A configure
        thread. ``payload`` may be a dict (validated via
        ``agent_roles.is_mode_b_payload``) or a pre-parsed ``ModeBPayload``.
        Raises ``ValueError`` on invalid payloads so callers fail loudly
        instead of silently widening the window.
        """
        from swarm.core.agent_roles import ModeBPayload, is_mode_b_payload, parse_mode_b_payload

        if isinstance(payload, ModeBPayload):
            parsed = payload
        elif isinstance(payload, dict) and is_mode_b_payload(payload):
            parsed = parse_mode_b_payload(payload)
        else:
            raise ValueError(
                "execute_as_role requires a valid Mode B payload "
                "(invocation, caller_id, role, latest_message, caller_context)"
            )
        execution_prompt = (ctx.params.get("execution_prompt") if ctx is not None else None) or (
            f"You are executing a '{self.id or 'role'}' task on behalf of caller"
            f" '{parsed.caller_id}'. Work only from the caller context and the"
            " latest message below; your private chat history is not available."
        )
        return parsed.build_model_messages(system_prompt=execution_prompt)

    # ------------------------------------------------------------- hooks

    def on_turn_start(self, ctx: RoleContext) -> RoleOutcome:  # noqa: ARG002 (default: unused)
        """Before the agent runs. Default: no-op."""
        return RoleOutcome()

    def on_turn_end(self, ctx: RoleContext, result: Any) -> RoleOutcome:  # noqa: ARG002 (default: unused)
        """After the agent runs. Default: no-op."""
        return RoleOutcome()

    def wrap_tool_calls(
        self, ctx: RoleContext, calls: Sequence[Any]  # noqa: ARG002 (default: unused)
    ) -> Sequence[Any] | RoleOutcome:
        """Intercept pending tool calls before execution (gate path).

        Return the (possibly wrapped/filtered) calls, or a ``RoleOutcome``
        with ``veto=True`` to block. Default: pass through unchanged.
        """
        return calls

    def as_tool(self, ctx: RoleContext) -> Any | None:  # noqa: ARG002 (default: unused)
        """Tool spec the calling agent may invoke (ambition d). Default: none."""
        return None


class WorkerRole(Role):
    """Ordinary turn execution — default, support, engineer.

    Metadata plus no-op hooks; never intercepts, never appends chrome.
    """

    role_category: ClassVar[str] = "worker"


class VerifierRole(Role):
    """Bounded yes/no review over completed work — gate, skeptic (#814).

    Subclasses share the standard :class:`Verdict` schema and the unified
    ``execute_verification`` seam; verdicts **fail closed** — an undetermined
    or unwired verification must not approve.
    """

    role_category: ClassVar[str] = "verifier"

    def execute_verification(
        self,
        ctx: RoleContext,  # noqa: ARG002 (seam: subclasses may read params)
        result: Any = None,
        payload: dict[str, Any] | None = None,
    ) -> "Verdict":
        """Produce a :class:`Verdict` from a turn result or tool-call batch.

        Default implementation fails closed: no recognized evidence means
        ``approved=False`` with ``failed=True``. Subclasses map their
        concrete result shapes onto the shared schema.
        """
        return Verdict(approved=False, failed=True, reason="verification unavailable (fail closed)")


class AdvisoryRole(Role):
    """Pure status/chrome output — advisor, suggestions (#814).

    Never mutates the persistent transcript with agent-visible content;
    produces status notes, chips, or tool specs only.
    """

    role_category: ClassVar[str] = "advisory"


class SupervisorRole(Role):
    """Lifecycle + topology authority over other seats — admin, CoS (#814).

    The only sub-base permitted ``allowed_everywhere``: supervisors span
    sections and teams by definition.
    """

    role_category: ClassVar[str] = "supervisor"


@dataclass
class Verdict:
    """Standard verifier outcome schema shared by gate and skeptic (#814).

    ``approved`` — the verified work may proceed.
    ``failed``   — verification ran and rejected (drives bounded retries).
    ``reason``   — human-readable summary for directives and traces.
    Fail-closed invariant: ``not approved and not failed`` is reserved for
    "verification could not run" and still counts as *not approved*.
    """

    approved: bool
    failed: bool = False
    reason: str | None = None

    @property
    def may_proceed(self) -> bool:
        """Fail-closed gate: only an explicit approval lets work proceed."""
        return self.approved and not self.failed

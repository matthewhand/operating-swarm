"""Role base class (REQ-852) — roles as behavior, not parallel tables.

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

    * ``status_note`` — non-persistent status chrome (advisor follow-up pattern)
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
    """

    id: ClassVar[str] = ""
    aliases: ClassVar[tuple[str, ...]] = ()
    label: ClassVar[str] = ""
    css_class: ClassVar[str] = ""
    allowed_everywhere: ClassVar[bool] = False
    badge: ClassVar[str | None] = None
    mechanism: ClassVar[str] = "none"
    mechanism_detail: ClassVar[str] = ""

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
        }

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

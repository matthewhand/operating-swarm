"""#1081 Phase 3 — Belay ToolGate bridge for the Pi harness.

The ADR gate: a Pi seat's tool execution runs through Swarm's Belay
approval barrier before any mutating tool executes. This module exposes
that barrier as an async callable suitable for serialising over the RPC
control channel (``pi_rpc_driver``) into the ``pi-operating-swarm``
extension's ``onToolCall`` hook (Phase 2, ``extensions/pi-operating-swarm``).

Reuse-first: the decision itself is :func:`swarm.core.safety.approve_pending_tool_call_async`
— the exact REQ-55 surface the API chat path uses (classify → always-allow →
elicit → deny, fail-closed). This module only adapts it to Pi's async
tool-call shape; no new policy lives here.

Denial semantics: Pi's ``onToolCall`` denies by raising, so the returned
async callable **raises** :class:`BelayDenial` on any non-approved verdict
(denied, unwired-elicit, or fail-closed classification). Approved calls
return normally.
"""

from __future__ import annotations

from typing import Any

from swarm.core.safety import approve_pending_tool_call_async

__all__ = ["BelayDenial", "belay_tool_gate"]


class BelayDenial(RuntimeError):
    """A Pi tool call was denied by the Belay barrier (or failed closed).

    Serialised with ``to_payload`` so the RPC control channel can forward a
    structured denial to the extension (which turns it into a tool error)
    without string-matching on the message.
    """

    def __init__(self, tool_name: str, verdict_raw: str, prompted: bool) -> None:
        self.tool_name = tool_name
        self.verdict_raw = verdict_raw
        self.prompted = prompted
        super().__init__(
            f"Belay denied tool '{tool_name}' (verdict: {verdict_raw}, prompted: {prompted})"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "type": "belay_denial",
            "tool": self.tool_name,
            "verdict": self.verdict_raw,
            "prompted": self.prompted,
        }


def belay_tool_gate(
    *,
    agent_id: str,
    safety: Any = None,
    classify_fn: Any = None,
    elicit_fn: Any = None,
    always_allow: Any = None,
    safety_assigned: bool | None = None,
) -> Any:
    """Build the async gate handed to the Pi extension's ``onToolCall``.

    Closure over the seat's REQ-55 inputs; the returned callable has the
    stable shape the extension serialises/awaits:
    ``async def gate(payload: dict) -> dict`` where *payload* carries
    ``tool`` and ``arguments``. Approved → returns ``{"approved": True,
    "verdict": raw}``. Denied → raises :class:`BelayDenial`.
    """

    async def gate(payload: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(payload.get("tool") or "")
        arguments = payload.get("arguments")
        verdict = await approve_pending_tool_call_async(
            channel="api",  # Pi seats use the Swarm approval UI (REQ-55: api-only elicitation)
            safety=safety,
            tool_name=tool_name,
            arguments=arguments if isinstance(arguments, dict) else {},
            agent_id=agent_id,
            classify_fn=classify_fn,
            elicit_fn=elicit_fn,
            always_allow=always_allow,
            safety_assigned=safety_assigned,
        )
        if not verdict.approved:
            raise BelayDenial(tool_name, str(verdict.raw), bool(verdict.prompted))
        return {"approved": True, "verdict": str(verdict.raw)}

    return gate

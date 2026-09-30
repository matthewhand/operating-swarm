"""Gate — role=gate marker (approval-classifier placeholder).

Classifies a tool call as dangerous or not by calling
``submit_gate_verdict`. Until a gate is wired, every tool call is approved. The
full ask-user-on-dangerous loop is a later PR — this blueprint only registers the
role so the AGENTS sidepane can style it, and so Support can point at it.

Because the classifier is not implemented, the seat must not read as a working
approval gate. It used to reply with its own instruction banner ("Gate — call
submit_gate_verdict… Until wired, all approved"), which the agent sweep scored as
a 1.9s answer: a bubble shaped like a turn that approves nothing. It now
returns the shared honest refusal and marks itself broken via ``seat_health``.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.core.blueprint_base import BlueprintBase

STUB_REASON = (
    "the approval classifier is not implemented — this seat registers the "
    "`role=gate` marker only, so no tool call is actually judged or blocked"
)
STUB_REMEDY = (
    "gate a real seat with `security_reviewer` (`role=gate`) or approve calls at "
    "the tool-request prompt; the ask-user-on-dangerous loop is a later PR"
)


class GateBlueprint(BlueprintBase):
    """Discoverable `role=gate` marker. No approval engine, and it says so."""

    metadata: ClassVar[dict[str, Any]] = {
        **unavailable.placeholder_metadata(),
        "name": "gate",
        "title": "Gate",
        "description": (
            "Placeholder for the dangerous-tool-call gate (yes=dangerous / "
            "no=safe). No classifier yet, so this seat does not answer and "
            "approves nothing. Use security_reviewer (role=gate) for a real gate."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["gate", "approval", "placeholder"],
        "role": "gate",
        "rail": True,
        "required_mcp_servers": [],
        "env_vars": [],
    }

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        yield unavailable.cannot_answer_chunk(
            "gate",
            why=STUB_REASON,
            remedy=STUB_REMEDY,
            backends=["gate"],
        )

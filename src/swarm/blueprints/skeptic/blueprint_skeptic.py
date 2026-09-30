"""Skeptic — role=skeptic marker (retry-check placeholder).

Receives the original prompt, checks whether the work was accomplished via
``submit_skeptic_verdict``, and if not would send findings back to the original
agent to retry. The full retry loop is a later PR — this blueprint only registers
the role.

That makes it a **placeholder**, not a working reviewer, so it says so. It used
to reply with its own instruction banner ("Skeptic — call
submit_skeptic_verdict…"), which the agent sweep read as a 1.9s answer: a
bubble that looks like a turn and is not one. It now returns the shared honest
refusal and marks itself broken via ``seat_health``, so the operator sees the
seat as unusable instead of as a fast, terse reviewer.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.core.blueprint_base import BlueprintBase

STUB_REASON = (
    "the skeptic retry loop is not implemented — this seat registers the "
    "`role=skeptic` marker only and has no engine to run a verdict"
)
STUB_REMEDY = (
    "use `code_reviewer` (a real review turn) or `sdlc_handoff` with "
    "`variant=skeptic_loop`; the skeptic retry engine is tracked as a later PR"
)


class SkepticBlueprint(BlueprintBase):
    """Discoverable `role=skeptic` marker. No retry engine, and it says so."""

    metadata: ClassVar[dict[str, Any]] = {
        **unavailable.placeholder_metadata(),
        "name": "skeptic",
        "title": "Skeptic",
        "description": (
            "Placeholder for the retry-check skeptic (pass/fail verdict, findings "
            "back to the original agent). No verdict engine yet — this seat does "
            "not answer. Use code_reviewer or sdlc_handoff (skeptic_loop) instead."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["skeptic", "retry", "placeholder"],
        "role": "skeptic",
        "rail": True,
        "required_mcp_servers": [],
        "env_vars": [],
    }

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        yield unavailable.cannot_answer_chunk(
            "skeptic",
            why=STUB_REASON,
            remedy=STUB_REMEDY,
            backends=["skeptic"],
        )

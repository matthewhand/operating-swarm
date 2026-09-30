"""The stub seats must also be honest outside chat.

``cannot_answer_chunk`` speaks the shared refusal in a chat bubble. The same
three seats are also reachable as CLI blueprints, where the chunk stream is
consumed directly by ``swarm-cli``. A stub seat must not print its old
instruction banner there either — that string is what the #1357 sweep read as a
1.9s answer, and it is equally misleading with no UI around it.
"""

from __future__ import annotations

import pytest

from swarm.blueprints.common.unavailable_seat import NO_MODEL_TURN_LEAD
from swarm.blueprints.gate.blueprint_gate import GateBlueprint
from swarm.blueprints.rue_code.blueprint_rue_code import RueCodeBlueprint
from swarm.blueprints.skeptic.blueprint_skeptic import SkepticBlueprint


async def _all_text(bp, messages):
    """Every string the turn emits, not just the final bubble."""
    out: list[str] = []
    async for chunk in bp.run(messages):
        if isinstance(chunk, dict):
            msgs = chunk.get("messages")
            if msgs:
                out.append(str(msgs[-1].get("content") or ""))
            elif chunk.get("content") is not None:
                out.append(str(chunk["content"]))
        else:
            out.append(str(chunk))
    return out


@pytest.mark.parametrize(
    "blueprint_id,cls",
    [
        ("gate", GateBlueprint),
        ("skeptic", SkepticBlueprint),
        ("rue_code", RueCodeBlueprint),
    ],
)
async def test_stub_seat_emits_only_the_refusal(blueprint_id, cls):
    parts = await _all_text(
        cls(blueprint_id=blueprint_id),
        [{"role": "user", "content": "review this diff for me"}],
    )
    assert parts, f"{blueprint_id} emitted nothing"
    spoken = [p for p in parts if p.strip()]
    assert spoken[0].startswith(NO_MODEL_TURN_LEAD)
    # No spinner frames, no progress strings, no second bubble pretending to
    # be the result.
    assert all(p.startswith(NO_MODEL_TURN_LEAD) for p in spoken), spoken
    joined = "\n".join(spoken)
    for banned in ("call submit_", "Generating.", "Code Results", "all approved"):
        assert banned not in joined

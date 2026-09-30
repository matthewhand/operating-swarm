"""Gate / Skeptic are role markers only — no execution loop.

Both seats are **declared placeholders**: they register a `role=` so the AGENTS
sidepane can style them, and nothing else. They used to answer with their own
instruction banner ("Skeptic — call submit_skeptic_verdict…", "Gate — … Until
wired, all approved"), which the #1357 agent sweep scored as a fast, terse reply
— a bubble shaped like a model turn that approves nothing and reviews nothing.

The requirement ("no execution loop", "never claim to do work you cannot") is
unchanged. What changed is that they now satisfy it explicitly: ``status:
incomplete`` in discovery metadata, and one shared honest refusal per turn.
"""

from swarm.blueprints.common.unavailable_seat import NO_MODEL_TURN_LEAD
from swarm.blueprints.gate.blueprint_gate import GateBlueprint
from swarm.blueprints.skeptic.blueprint_skeptic import SkepticBlueprint


async def _final(bp, messages=None):
    text = None
    async for chunk in bp.run(messages or []):
        msgs = chunk.get("messages") if isinstance(chunk, dict) else None
        if msgs:
            text = msgs[0]["content"]
    return text


def test_roles():
    assert GateBlueprint.metadata["role"] == "gate"
    assert SkepticBlueprint.metadata["role"] == "skeptic"
    assert GateBlueprint.metadata["rail"] is True
    assert SkepticBlueprint.metadata["rail"] is True


def test_both_declare_themselves_incomplete():
    for cls in (GateBlueprint, SkepticBlueprint):
        assert cls.metadata["status"] == "incomplete"
        assert "placeholder" in cls.metadata["description"].lower()


async def test_gate_refuses_instead_of_claiming_approval():
    text = await _final(GateBlueprint(blueprint_id="gate"))
    assert text.startswith(NO_MODEL_TURN_LEAD)
    # The old banner asserted a capability it does not have.
    assert "all approved" not in text.lower()
    assert "gate" in text
    # Still useful: it names the seat's purpose and the way out.
    assert "role=gate" in text
    assert "What to do:" in text


async def test_skeptic_refuses_instead_of_announcing_a_verdict_tool():
    text = await _final(SkepticBlueprint(blueprint_id="skeptic"))
    assert text.startswith(NO_MODEL_TURN_LEAD)
    assert "skeptic" in text
    assert "role=skeptic" in text
    assert "What to do:" in text


async def test_neither_returns_its_own_instruction_text():
    """The exact failure mode: the bubble is the seat's system prompt."""
    for cls, blueprint_id in ((GateBlueprint, "gate"), (SkepticBlueprint, "skeptic")):
        text = await _final(cls(blueprint_id=blueprint_id))
        assert "call submit_" not in text
        assert text.count("\n") > 0, "a refusal explains itself; a banner is one line"

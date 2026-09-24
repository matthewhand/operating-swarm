"""#1081 Phase 3 — Belay ToolGate bridge contracts.

The gate reuses Swarm's REQ-55 :func:`approve_pending_tool_call` verbatim;
these tests pin the *bridge* behaviour: approval passthrough, denial
raises, structured denial payload, and the fail-closed path.
"""

from __future__ import annotations

import pytest

from swarm.core.pi_belay_gate import BelayDenial, belay_tool_gate
from swarm.core.safety import AlwaysAllowStore


class _Verdict:
    def __init__(self, approved: bool, raw: str = "OK", prompted: bool = False) -> None:
        self.approved = approved
        self.raw = raw
        self.prompted = prompted


@pytest.fixture
def patch_approve(monkeypatch):
    """Patch the REQ-55 call the bridge delegates to; returns a recorder."""

    def _install(verdict: _Verdict):
        calls: list[dict] = []

        async def fake_approve(**kwargs):
            calls.append(kwargs)
            return verdict

        monkeypatch.setattr(
            "swarm.core.pi_belay_gate.approve_pending_tool_call_async", fake_approve
        )
        return calls

    return _install


@pytest.mark.anyio
async def test_approved_tool_call_passes_through(patch_approve):
    calls = patch_approve(_Verdict(approved=True, raw="NO"))
    gate = belay_tool_gate(agent_id="seat-1", safety_assigned=True)
    out = await gate({"tool": "read_file", "arguments": {"path": "x"}})
    assert out == {"approved": True, "verdict": "NO"}
    assert calls[0]["tool_name"] == "read_file"
    assert calls[0]["agent_id"] == "seat-1"
    assert calls[0]["channel"] == "api"


@pytest.mark.anyio
async def test_denied_tool_call_raises_belay_denial(patch_approve):
    patch_approve(_Verdict(approved=False, raw="ELICIT_DENY", prompted=True))
    gate = belay_tool_gate(agent_id="seat-1", safety_assigned=True)
    with pytest.raises(BelayDenial) as excinfo:
        await gate({"tool": "bash", "arguments": {"cmd": "rm -rf /"}})
    assert excinfo.value.tool_name == "bash"
    assert excinfo.value.prompted is True


@pytest.mark.anyio
async def test_denial_serialises_to_structured_payload(patch_approve):
    patch_approve(_Verdict(approved=False, raw="ELICIT_DENY", prompted=False))
    gate = belay_tool_gate(agent_id="seat-1", safety_assigned=True)
    with pytest.raises(BelayDenial) as excinfo:
        await gate({"tool": "bash", "arguments": {}})
    payload = excinfo.value.to_payload()
    assert payload == {
        "type": "belay_denial",
        "tool": "bash",
        "verdict": "ELICIT_DENY",
        "prompted": False,
    }


@pytest.mark.anyio
async def test_unwired_gate_approves_everything(patch_approve):
    # REQ-55 default-open: no safety assigned → approved without prompting.
    calls = patch_approve(_Verdict(approved=True, raw="UNWIRED"))
    gate = belay_tool_gate(agent_id="seat-1", safety_assigned=False)
    out = await gate({"tool": "bash", "arguments": {}})
    assert out["approved"] is True
    assert calls[0]["safety_assigned"] is False


@pytest.mark.anyio
async def test_arguments_normalised_when_missing(patch_approve):
    calls = patch_approve(_Verdict(approved=True, raw="NO"))
    gate = belay_tool_gate(agent_id="seat-1", safety_assigned=True)
    await gate({"tool": "read_file"})
    assert calls[0]["arguments"] == {}

"""#1170 — the chat gate's verdict is honored, visibly, with a cap.

`_gate_provider_rate_limit` now:
1. emits the wait status when the wait *starts* (the old `on_wait` only fired
   from inside `acquire`'s retry loop — a long first wait was invisible),
2. caps the total wait (default 60s, `SWARM_CHAT_GATE_WAIT_CAP_S`): beyond it,
   `ProviderGateTimeout` is raised so `respond_with_blueprint` can fail the
   turn honestly instead of holding the agent lock forever,
3. returns the gate's `WaitDecision` (or None when no rules) so the caller can
   proceed exactly when the gate allowed it.
"""

from __future__ import annotations

import asyncio

import pytest

from swarm.chat import helpers
from swarm.core import provider_rate_limit as prl
from swarm.core.provider_rate_limit import WaitDecision


class _FakeConsumer:
    def __init__(self):
        self.sent = []
        self.messages = []
        self.ui_events = []

    async def send(self, text_data):
        self.sent.append(text_data)


def _decision(remaining: float, key: str = "remote:letta-demo") -> WaitDecision:
    return WaitDecision(
        provider_key=key, rule="requests_per_minute",
        remaining_seconds=remaining, limit=1, wait_until=0.0,
    )


def _install_gate(monkeypatch, *, remaining: float, hold: float, returns):
    """Fake swarm.consumers.gate_provider_send: emits once, holds, returns."""

    async def fake_gate(**kwargs):
        on_wait = kwargs.get("on_wait")
        if on_wait is not None and remaining is not None:
            await on_wait(_decision(remaining))
        if hold:
            await asyncio.sleep(hold)
        return returns

    monkeypatch.setattr(prl, "gate_provider_send", fake_gate)


def test_wait_start_is_emitted_and_decision_flows(monkeypatch):
    consumer = _FakeConsumer()
    _install_gate(monkeypatch, remaining=30.0, hold=0.05, returns=_decision(30.0))
    monkeypatch.setenv("SWARM_CHAT_GATE_WAIT_CAP_S", "60")

    async def scenario():
        return await helpers._gate_provider_rate_limit(
            consumer, params={"remote": "letta-demo"}, blueprint_id="remote_harness",
        )

    decision = asyncio.run(scenario())
    assert isinstance(decision, WaitDecision)
    assert consumer.sent, "wait status must be emitted when the wait starts"
    assert consumer.ui_events, "wait status must be recorded into the transcript side-channel"


def test_wait_is_capped_and_raises_for_the_responder(monkeypatch):
    consumer = _FakeConsumer()
    _install_gate(monkeypatch, remaining=600.0, hold=3.0, returns=_decision(600.0))
    monkeypatch.setenv("SWARM_CHAT_GATE_WAIT_CAP_S", "1")

    async def scenario():
        return await helpers._gate_provider_rate_limit(
            consumer, params={"remote": "letta-demo"}, blueprint_id="remote_harness",
        )

    with pytest.raises(helpers.ProviderGateTimeout) as excinfo:
        asyncio.run(scenario())
    assert "letta-demo" in str(excinfo.value) or "throttl" in str(excinfo.value).lower()
    assert consumer.sent, "the cap must still leave visible copy on the wire"


def test_immediate_capacity_is_silent(monkeypatch):
    consumer = _FakeConsumer()
    _install_gate(monkeypatch, remaining=None, hold=0.0, returns=None)
    monkeypatch.setenv("SWARM_CHAT_GATE_WAIT_CAP_S", "60")

    async def scenario():
        return await helpers._gate_provider_rate_limit(
            consumer, params={"remote": "letta-demo"}, blueprint_id="remote_harness",
        )

    assert asyncio.run(scenario()) is None
    assert not consumer.sent  # no wait → no wait copy


def test_gate_crash_still_proceeds(monkeypatch):
    consumer = _FakeConsumer()

    async def boom(**kwargs):
        raise RuntimeError("gate exploded")

    monkeypatch.setattr(prl, "gate_provider_send", boom)

    async def scenario():
        return await helpers._gate_provider_rate_limit(
            consumer, params={"remote": "letta-demo"}, blueprint_id="remote_harness",
        )

    assert asyncio.run(scenario()) is None

"""#818 — the auxiliary-task registry: register/finish/cancel/decay."""

from __future__ import annotations

import pytest

from swarm.core.auxiliary_tasks import AuxiliaryTaskRegistry


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


class FakeHandle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


@pytest.fixture()
def clock():
    return FakeClock()


def test_register_and_running_payload(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    tid = reg.register("Summarizing context", model="gpt-4o-mini")
    rows = reg.snapshot()
    assert len(rows) == 1
    assert rows[0]["task_id"] == tid
    assert rows[0]["state"] == "running"
    assert rows[0]["label"] == "Summarizing context"
    assert rows[0]["model"] == "gpt-4o-mini"


def test_finish_records_duration_and_decays(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    tid = reg.register("Advisor note")
    clock.now += 1.4
    payload = reg.finish(tid)
    assert payload["state"] == "done"
    assert payload["duration_s"] == 1.4
    # Lingers through the decay window...
    clock.now += AuxiliaryTaskRegistry.DECAY_SECONDS - 0.1
    assert len(reg.snapshot()) == 1
    # ...then sweeps.
    clock.now += 0.2
    assert reg.snapshot() == []


def test_cancel_aborts_the_cancellable_handle(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    handle = FakeHandle()
    tid = reg.register("Runaway loop", cancellable=handle)
    assert reg.cancel(tid) is True
    assert handle.cancelled is True
    states = {row["task_id"]: row["state"] for row in reg.snapshot()}
    assert states[tid] == "cancelled"


def test_cancel_without_handle_is_honest(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    tid = reg.register("Inline await")
    assert reg.cancel(tid) is False
    assert reg.snapshot()[0]["state"] == "running"


def test_cancel_unknown_id_is_false(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    assert reg.cancel("nope") is False


def test_snapshot_orders_active_first_by_recency(clock):
    reg = AuxiliaryTaskRegistry(clock=clock)
    first = reg.register("first")
    clock.now += 5
    second = reg.register("second")
    rows = reg.snapshot()
    assert [r["task_id"] for r in rows] == [second, first]
    reg.finish(first)
    clock.now += 1
    # Finished rows sink below running ones.
    rows = reg.snapshot()
    assert rows[0]["task_id"] == second
    assert rows[-1]["task_id"] == first

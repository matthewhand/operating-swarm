"""#1374 Phase A — one team send runs N≥3 legs concurrently.

The team-roster path is a first-class fan-out (blueprint, CLI, and remote
members). This harness proves:

* three legs overlap in time (no single worker lock serialises them);
* each leg has a stable id and the status stream
  queued → running → done/error/cancelled;
* ``FanOutCancel.cancel(leg_id)`` stops that leg and leaves the others to finish.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from swarm.core import team_roster_executor as ex

pytestmark = pytest.mark.asyncio


def _roster(members):
    return {"id": "t1", "name": "Fan Out", "members": members}


def _member(member_id, source, name=None):
    kind = source.split(":", 1)[0]
    return {
        "id": member_id,
        "name": name or member_id,
        "kind": kind,
        "role": "default",
        "source": source,
    }


def _patch_roster(monkeypatch, roster):
    monkeypatch.setattr(ex, "resolve_roster", lambda rid: roster if rid == "t1" else None)


async def test_three_legs_overlap_and_stream_done(monkeypatch):
    """N=3 sleeps overlap; a serial loop would take ~3x one leg."""
    in_flight = 0
    max_in_flight = 0
    entered: dict[str, float] = {}

    async def slow(blueprint_id, prompt, *, brief=None, **_kwargs):
        nonlocal in_flight, max_in_flight
        del prompt, brief
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        entered[blueprint_id] = time.monotonic()
        try:
            await asyncio.sleep(0.35)
            return f"ok:{blueprint_id}"
        finally:
            in_flight -= 1

    monkeypatch.setattr(ex, "_run_blueprint_member", slow)
    roster = _roster(
        [
            _member("alpha", "blueprint:alpha", name="Alpha"),
            _member("bravo", "blueprint:bravo", name="Bravo"),
            _member("charlie", "blueprint:charlie", name="Charlie"),
        ]
    )
    _patch_roster(monkeypatch, roster)
    log: list[ex.FanOutEvent] = []

    started = time.monotonic()
    run = await ex.execute_roster("t1", "all", "fan out", config={}, status_log=log)
    elapsed = time.monotonic() - started

    assert [r.member_id for r in run.results] == ["alpha", "bravo", "charlie"]
    assert [r.status for r in run.results] == ["done", "done", "done"]
    assert all(r.ok for r in run.results)
    assert max_in_flight >= 3, f"legs were serialised (max in flight {max_in_flight})"
    assert elapsed < 0.9, f"expected overlap under 0.9s, took {elapsed:.2f}s"
    assert max(entered.values()) - min(entered.values()) < 0.2

    for leg_id in ("alpha", "bravo", "charlie"):
        seq = [event.status for event in log if event.leg_id == leg_id]
        assert seq == ["queued", "running", "done"], seq
        assert all(event.leg_id == leg_id for event in log if event.leg_id == leg_id)


async def test_cancel_stops_one_leg_and_siblings_finish(monkeypatch):
    entered = asyncio.Event()

    async def maybe_hang(blueprint_id, prompt, *, brief=None, **_kwargs):
        del prompt, brief
        if blueprint_id == "bravo":
            entered.set()
            await asyncio.sleep(30)
            return "bravo-should-not-finish"
        await asyncio.sleep(0.05)
        return f"ok:{blueprint_id}"

    monkeypatch.setattr(ex, "_run_blueprint_member", maybe_hang)
    roster = _roster(
        [
            _member("alpha", "blueprint:alpha"),
            _member("bravo", "blueprint:bravo"),
            _member("charlie", "blueprint:charlie"),
        ]
    )
    _patch_roster(monkeypatch, roster)
    handle = ex.FanOutCancel()
    log: list[ex.FanOutEvent] = []

    job = asyncio.create_task(
        ex.execute_roster(
            "t1",
            "all",
            "go",
            config={},
            cancel=handle,
            status_log=log,
            per_member_timeout=10,
        )
    )
    await asyncio.wait_for(entered.wait(), timeout=2)
    assert handle.cancel("bravo") is True
    assert handle.cancel("no-such-leg") is False

    run = await asyncio.wait_for(job, timeout=2)
    by_id = {row.member_id: row for row in run.results}
    assert by_id["alpha"].status == "done" and by_id["alpha"].ok
    assert by_id["charlie"].status == "done" and by_id["charlie"].ok
    assert by_id["bravo"].status == "cancelled"
    assert by_id["bravo"].ok is False
    assert "bravo-should-not-finish" not in (by_id["bravo"].text or "")

    assert [e.status for e in log if e.leg_id == "bravo"] == [
        "queued",
        "running",
        "cancelled",
    ]
    assert [e.status for e in log if e.leg_id == "alpha"] == [
        "queued",
        "running",
        "done",
    ]
    assert "[failed: cancelled]" not in run.combined
    assert "ok:alpha" in run.combined
    assert "ok:charlie" in run.combined


async def test_failed_leg_is_error_and_does_not_block_siblings(monkeypatch):
    async def boom_or_ok(blueprint_id, prompt, *, brief=None, **_kwargs):
        del prompt, brief
        await asyncio.sleep(0.05)
        if blueprint_id == "bravo":
            raise RuntimeError("boom")
        return f"ok:{blueprint_id}"

    monkeypatch.setattr(ex, "_run_blueprint_member", boom_or_ok)
    roster = _roster(
        [
            _member("alpha", "blueprint:alpha"),
            _member("bravo", "blueprint:bravo"),
            _member("charlie", "blueprint:charlie"),
        ]
    )
    _patch_roster(monkeypatch, roster)
    log: list[ex.FanOutEvent] = []

    run = await ex.execute_roster("t1", "all", "go", config={}, status_log=log)
    by_id = {row.member_id: row for row in run.results}
    assert by_id["bravo"].status == "error"
    assert "boom" in (by_id["bravo"].error or "")
    assert by_id["alpha"].status == "done"
    assert by_id["charlie"].status == "done"
    assert [e.status for e in log if e.leg_id == "bravo"] == [
        "queued",
        "running",
        "error",
    ]


async def test_cancel_all_during_queue_does_not_start_later_legs(monkeypatch):
    """Stop while the first queued frame is in flight must not start the rest.

    Legs are tracked before any await. A cancel that arrives on another
    task at that first await therefore marks every leg, including ones
    whose queued frame has not been sent yet.
    """
    entered: list[str] = []

    async def slow(blueprint_id, prompt, *, brief=None, **_kwargs):
        del prompt, brief
        entered.append(blueprint_id)
        await asyncio.sleep(30)
        return f"ok:{blueprint_id}"

    monkeypatch.setattr(ex, "_run_blueprint_member", slow)
    roster = _roster(
        [
            _member("alpha", "blueprint:alpha"),
            _member("bravo", "blueprint:bravo"),
            _member("charlie", "blueprint:charlie"),
        ]
    )
    _patch_roster(monkeypatch, roster)
    handle = ex.FanOutCancel()
    first_queued = asyncio.Event()

    async def on_status(event):
        if event.status == "queued":
            first_queued.set()

    job = asyncio.create_task(
        ex.execute_roster(
            "t1",
            "all",
            "go",
            config={},
            cancel=handle,
            on_status=on_status,
            per_member_timeout=10,
        )
    )
    await asyncio.wait_for(first_queued.wait(), timeout=2)
    assert handle.cancel_all() >= 1
    run = await asyncio.wait_for(job, timeout=2)

    assert entered == []
    assert [row.status for row in run.results] == ["cancelled", "cancelled", "cancelled"]
    assert run.combined == ""

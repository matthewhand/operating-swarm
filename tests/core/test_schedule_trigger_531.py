"""#531 — repeating schedule triggers alongside the on-merge PR trigger.

The backend machinery (``interval``/``cron``/``one_shot`` kinds,
``compute_next_run``, the in-process ``schedule_engine`` tick, and the
RoutineEditor's interval/cron fields) already exists on main. These tests pin
the issue's acceptance criteria end-to-end so the capability cannot regress:

1. creating a repeating schedule persists ``next_run``;
2. updating the trigger recomputes (honours) ``next_run``;
3. the due tick fires the flow (history + fresh ``next_run``);
4. disabling stops firing.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from swarm.core.routines import (
    create_routine,
    get_routine,
    tick_due_routines,
    update_routine,
)
from swarm.core.schedule_triggers import utcnow


@pytest.fixture()
def routine_store(tmp_path, monkeypatch):
    """Point the routines store at a temp file and reset the module cache."""
    store = tmp_path / "agent_routines.json"
    store.write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(store))
    monkeypatch.setattr(
        "swarm.core.routines._cache", None, raising=False
    )
    yield store
    import swarm.core.routines as routines_mod

    routines_mod._cache = None


def _as_utc(value: str | None) -> datetime:
    assert value
    return datetime.fromisoformat(value)


def test_creating_repeating_interval_persists_next_run(routine_store):
    """The fixture wires the temp store even though the body never names it."""
    del routine_store
    now = utcnow()
    created = create_routine(
        "api_agent",
        {
            "name": "Every 5 minutes",
            "instruction": "Check the queue",
            "active": True,
            "trigger": {"kind": "interval", "seconds": 300},
        },
    )
    assert created["active"] is True
    next_run = _as_utc(created["next_run"])
    assert now < next_run <= now + timedelta(minutes=6)


def test_creating_repeating_cron_persists_next_run(routine_store):
    del routine_store
    now = utcnow()
    created = create_routine(
        "api_agent",
        {
            "name": "Nightly",
            "instruction": "Sweep logs",
            "active": True,
            "trigger": {"kind": "cron", "expression": "0 3 * * *"},
        },
    )
    assert now < _as_utc(created["next_run"]) <= now + timedelta(days=1)


def test_updating_trigger_honours_next_run(routine_store):
    del routine_store
    """The REQ-896 regression: a trigger edit must recompute next_run, not
    leave the old cadence's value behind (issue #531's explicit pointer)."""
    created = create_routine(
        "api_agent",
        {
            "name": "Cadence change",
            "instruction": "Work",
            "active": True,
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )
    before = _as_utc(created["next_run"])

    updated = update_routine("api_agent", created["id"], {"active": True})
    assert _as_utc(updated["next_run"]) == before

    changed = update_routine(
        "api_agent",
        created["id"],
        {"trigger": {"kind": "interval", "seconds": 60}},
    )
    after = _as_utc(changed["next_run"])
    assert after < before, "tightened cadence must pull next_run earlier"


def test_due_tick_fires_the_flow(routine_store):
    del routine_store
    now = utcnow()
    created = create_routine(
        "api_agent",
        {
            "name": "Due now",
            "instruction": "Do the thing",
            "active": True,
            "trigger": {"kind": "interval", "seconds": 300},
        },
    )
    # Force next_run into the past: the schedule is due.
    due = update_routine(
        "api_agent",
        created["id"],
        {"next_run": (now - timedelta(seconds=5)).isoformat()},
    )
    assert _as_utc(due["next_run"]) < now

    fired = tick_due_routines(now)
    assert any(row["routine"]["id"] == created["id"] for row in fired)

    refired = get_routine("api_agent", created["id"])
    assert len(refired["history"]) == 1
    assert refired["history"][0]["source"] == "schedule"
    # The repeat: next_run advanced past the tick moment.
    assert _as_utc(refired["next_run"]) >= now


def test_disabling_stops_firing(routine_store):
    del routine_store
    now = utcnow()
    created = create_routine(
        "api_agent",
        {
            "name": "Paused soon",
            "instruction": "Do not run",
            "active": True,
            "trigger": {"kind": "interval", "seconds": 300},
        },
    )
    update_routine(
        "api_agent",
        created["id"],
        {"next_run": (now - timedelta(seconds=5)).isoformat()},
    )
    update_routine("api_agent", created["id"], {"active": False})

    fired = tick_due_routines(now)
    assert not any(row["routine"]["id"] == created["id"] for row in fired)

    row = get_routine("api_agent", created["id"])
    assert row["history"] == []

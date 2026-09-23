"""#222 in-process schedule engine ticks routines and test schedules together."""

from datetime import datetime, timedelta, timezone

from swarm.core import routines as routines_store
from swarm.core import schedule_engine
from swarm.core import test_schedules as schedules_store


def test_tick_runs_due_routine_and_schedule(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    path = tmp_path / "test_schedules.json"
    path.write_text('{"schema": 1, "schedules": []}\n', encoding="utf-8")
    monkeypatch.setenv("SWARM_TEST_SCHEDULES_PATH", str(path))
    routines_store.reset_routines_cache()
    schedules_store.reset_test_schedules_cache()
    schedules_store.set_failure_notifier(lambda *_a, **_k: None)

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    routine = routines_store.create_routine(
        "codey",
        {
            "name": "Hourly recap",
            "instruction": "Recap the hour.",
            "trigger": {"kind": "interval", "seconds": 60},
        },
    )
    routines_store.update_routine( "codey", routine["id"], {"next_run": (now - timedelta(seconds=1)).isoformat()})
    # update_routine clears next_run when trigger changes; patch next_run via persist
    row = routines_store.get_routine("codey", routine["id"])
    row["next_run"] = (now - timedelta(seconds=1)).isoformat()
    routines_store._persist_agent("codey", [row])

    schedule = schedules_store.create_schedule(
        {
            "name": "Health",
            "trigger": {"kind": "interval", "seconds": 60},
            "check": {"kind": "harness_health", "name": "remote_health"},
        }
    )
    sched_row = schedules_store.get_schedule(schedule["id"])
    sched_row["next_run"] = (now - timedelta(seconds=1)).isoformat()
    schedules_store._persist([sched_row])

    result = schedule_engine.tick(now)
    assert result["routines"] == 1
    assert result["schedules"] == 1
    assert routines_store.get_routine("codey", routine["id"])["history"][0]["source"] == "schedule"
    assert schedules_store.get_schedule(schedule["id"])["history"][0]["source"] == "schedule"


def test_start_loop_skipped_in_test_mode(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    assert schedule_engine.start_loop() is False

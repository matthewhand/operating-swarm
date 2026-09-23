"""#222 test schedule store — seeds, CRUD, run-now, tick, failure notify."""

from datetime import UTC, datetime, timedelta

from swarm.core import test_schedules as store


def _isolate(tmp_path, monkeypatch):
    path = tmp_path / "test_schedules.json"
    path.write_text('{"schema": 1, "schedules": []}\n', encoding="utf-8")
    monkeypatch.setenv("SWARM_TEST_SCHEDULES_PATH", str(path))
    store.reset_test_schedules_cache()
    store.set_check_runner(None)
    store.set_failure_notifier(lambda *_args, **_kwargs: None)


def test_empty_file_can_be_seeded_on_missing_path(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_TEST_SCHEDULES_PATH", str(tmp_path / "missing.json"))
    store.reset_test_schedules_cache()
    rows = store.list_schedules()
    names = {row["name"] for row in rows}
    assert "Remote harness health" in names
    assert "Blueprint smoke tests" in names
    assert "Fleet remote prove" in names
    assert all(row["active"] is False for row in rows)


def test_create_interval_run_now_and_history(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_schedule(
        {
            "name": "Hourly health",
            "trigger": {"kind": "interval", "seconds": 3600},
            "target": {"kind": "fleet", "fleet": "all"},
            "check": {"kind": "harness_health", "name": "remote_health"},
        }
    )
    assert created["trigger"]["kind"] == "interval"
    assert created["when_to_run"] == "Every 1 hour…"
    ran = store.run_now(created["id"])
    assert ran["history"][0]["status"] == "success"
    assert ran["history"][0]["source"] == "run_now"
    assert ran["history"][0]["duration_ms"] >= 0
    assert "artifact" in ran["history"][0]
    assert store.fired_checks()[0]["check"] == "remote_health"


def test_tick_fires_due_interval_and_skips_inactive(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    due = store.create_schedule(
        {
            "name": "Due",
            "trigger": {"kind": "interval", "seconds": 60},
            "check": {"kind": "script", "name": "fleet_prove"},
        }
    )
    paused = store.create_schedule(
        {
            "name": "Paused",
            "active": False,
            "trigger": {"kind": "interval", "seconds": 60},
            "check": {"kind": "script", "name": "fleet_prove"},
        }
    )
    store.update_schedule(due["id"], {"next_run": (now - timedelta(seconds=1)).isoformat()})
    fired = store.tick_due_schedules(now)
    ids = {row["id"] for row in fired}
    assert due["id"] in ids
    assert paused["id"] not in ids
    assert store.get_schedule(due["id"])["history"][0]["source"] == "schedule"


def test_update_schedule_persists_next_run(tmp_path, monkeypatch):
    """update_schedule accepts next_run — it must actually persist it (#486 sweep).

    Regression: next_run was whitelisted in the patch keys but never applied, so
    callers could not seed or correct a schedule's next fire time and
    tick_due_schedules silently never fired the schedule.
    """
    _isolate(tmp_path, monkeypatch)
    created = store.create_schedule(
        {
            "name": "Seeded",
            "trigger": {"kind": "interval", "seconds": 60},
            "check": {"kind": "script", "name": "fleet_prove"},
        }
    )
    seeded = (datetime(2026, 9, 16, 12, 0, tzinfo=UTC) - timedelta(seconds=1)).isoformat()
    updated = store.update_schedule(created["id"], {"next_run": seeded})
    assert updated["next_run"] == seeded
    assert store.get_schedule(created["id"])["next_run"] == seeded


def test_failure_notifies_and_open_failures(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    notes = []
    store.set_failure_notifier(lambda schedule, row: notes.append((schedule["id"], row["status"])))

    def _fail(_schedule):
        return {"status": "error", "summary": "harness down", "token_cost": 0}

    store.set_check_runner(_fail)
    created = store.create_schedule({"name": "Boom", "check": {"kind": "script", "name": "fleet_prove"}})
    ran = store.run_now(created["id"])
    assert ran["history"][0]["status"] == "error"
    assert notes
    failures = store.open_failures()
    assert failures[0]["id"] == created["id"]


def test_rejects_github_trigger_and_secrets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_schedule({"trigger": {"kind": "github_pr_merged", "owner_repo": "o/r"}})
    except ValueError as exc:
        assert "kind" in str(exc).lower() or "Unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    try:
        store.create_schedule({"name": "leak ghp_notasecret"})
    except ValueError as exc:
        assert "secret" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_one_shot_deactivates_after_schedule_fire(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    now = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)
    created = store.create_schedule(
        {
            "name": "Once",
            "trigger": {"kind": "one_shot", "run_at": "2026-09-16T11:00:00Z"},
            "check": {"kind": "blueprint_smoke", "name": "blueprint_smoke"},
        }
    )
    fired = store.tick_due_schedules(now)
    assert fired
    again = store.get_schedule(created["id"])
    assert again["active"] is False

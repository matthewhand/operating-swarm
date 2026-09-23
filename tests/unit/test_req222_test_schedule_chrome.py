"""#222 — Test schedule pane + time-based routine triggers sit beside REQ-80 chrome."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STUB = REPO / "webui" / "frontend" / "src" / "components" / "ComputerControlStub.tsx"
PANE = REPO / "webui" / "frontend" / "src" / "components" / "TestSchedulePane.tsx"
ROUTINES_PANE = REPO / "webui" / "frontend" / "src" / "components" / "ComputerRoutinesPane.tsx"
TRIGGERS = REPO / "src" / "swarm" / "core" / "schedule_triggers.py"
SCHEDULES = REPO / "src" / "swarm" / "core" / "test_schedules.py"
ENGINE = REPO / "src" / "swarm" / "core" / "schedule_engine.py"
API = REPO / "src" / "swarm" / "views" / "test_schedules_api.py"
URLS = REPO / "src" / "swarm" / "urls.py"
APPS = REPO / "src" / "swarm" / "apps.py"


def test_computer_pane_has_routines_and_test_schedule_tabs():
    stub = STUB.read_text(encoding="utf-8")
    assert "TestSchedulePane" in stub
    assert "ComputerRoutinesPane" in stub
    assert "Test schedule" in stub
    assert "failure_count" in stub or "failed test schedules" in stub
    assert "Operating Swarm" not in stub  # do not rebrand this pane


def test_test_schedule_editor_has_run_now_history_and_fleet_target():
    pane = PANE.read_text(encoding="utf-8")
    for needle in ("Run now", "Active", "History", "Fleet subset", "Harness health", "Add test schedule"):
        assert needle in pane
    assert ":8001" not in pane


def test_routines_pane_exposes_time_and_mailbox_triggers():
    pane = ROUTINES_PANE.read_text(encoding="utf-8")
    for needle in ("Interval", "Cron", "One-shot", "Mailbox message", "Run now"):
        assert needle in pane


def test_store_seeds_fleet_proofs_and_engine_is_single_process():
    schedules = SCHEDULES.read_text(encoding="utf-8")
    assert "Remote harness health" in schedules
    assert "Fleet remote prove" in schedules
    assert "test_schedules.json" in schedules
    engine = ENGINE.read_text(encoding="utf-8")
    assert "single-process" in engine
    assert "No distributed" in engine or "no distributed" in engine
    apps = APPS.read_text(encoding="utf-8")
    assert "_maybe_start_schedule_engine" in apps


def test_api_paths_exist():
    urls = URLS.read_text(encoding="utf-8")
    assert "v1/test-schedules/" in urls
    assert "v1/test-schedules/status/" in urls
    assert "run-now" in urls
    api = API.read_text(encoding="utf-8")
    assert "run-now" in api
    assert ":8001" not in api
    assert "localhost" not in api
    triggers = TRIGGERS.read_text(encoding="utf-8")
    assert "interval" in triggers
    assert "mailbox_message" in triggers
    assert "must not contain secrets" in triggers

"""Operator control plane (#1360): budgets, checkout, gates, org packs."""

from __future__ import annotations

import inspect
import json
import threading
from datetime import UTC, datetime, timedelta

import pytest

from swarm.core import operator_plane as plane
from swarm.core import routines
from swarm.core.kind_bases import KindBase
from swarm.core.operator_plane import (
    ApprovalError,
    BudgetHardStop,
    OperatorPlaneError,
    OrgPackError,
    TaskBusy,
    TaskNotHeld,
)
from swarm.core.remote_harness import REMOTE_IMPL_IDS


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_OPERATOR_PLANE_PATH", str(tmp_path / "plane.json"))
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "routines.json"))
    routines.reset_routines_cache()
    routines.set_instruction_runner(None)
    from swarm.core import team_rosters as rosters

    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setattr(rosters, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(rosters, "ensure_swarm_directories_exist", lambda: None)
    rosters.reset_team_rosters()


def test_operator_plane_is_not_a_seat_kind():
    assert "paperclip" not in REMOTE_IMPL_IDS
    assert "operator_plane" not in REMOTE_IMPL_IDS
    for obj in vars(plane).values():
        if inspect.isclass(obj) and obj.__module__ == plane.__name__:
            assert not issubclass(obj, KindBase)


def test_hard_stop_refuses_the_charge_that_would_exceed(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    policy = plane.set_budget_policy(
        scope="seat", scope_id="codey", token_limit=5, hard_stop=True
    )
    assert policy["stopped"] is False
    charged = plane.charge_budget(scope="seat", scope_id="codey", tokens=4)
    assert charged["tokens_used"] == 4
    with pytest.raises(BudgetHardStop) as raised:
        plane.charge_budget(scope="seat", scope_id="codey", tokens=2)
    assert raised.value.attempted == 2
    assert raised.value.used == 4
    again = plane.list_budgets()[0]
    assert again["tokens_used"] == 4
    assert again["stopped"] is True
    with pytest.raises(BudgetHardStop):
        plane.charge_budget(scope="seat", scope_id="codey", tokens=1)
    reset = plane.reset_budget(scope="seat", scope_id="codey")
    assert reset["tokens_used"] == 0
    assert reset["stopped"] is False


def test_soft_budget_records_overage(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    plane.set_budget_policy(
        scope="team", scope_id="research", token_limit=5, hard_stop=False
    )
    charged = plane.charge_budget(scope="team", scope_id="research", tokens=9)
    assert charged["tokens_used"] == 9
    assert charged["stopped"] is False


def test_zero_limit_starts_stopped(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    policy = plane.set_budget_policy(scope="seat", scope_id="codey", token_limit=0)
    assert policy["stopped"] is True
    with pytest.raises(BudgetHardStop):
        plane.charge_budget(scope="seat", scope_id="codey", tokens=0)


def test_checkout_is_atomic_and_lease_can_be_stolen(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker():
        barrier.wait()
        try:
            plane.checkout_task("task-1", f"worker-{threading.get_ident()}", lease_s=60)
            results.append("ok")
        except TaskBusy:
            results.append("busy")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == ["busy", "ok"]

    moment = datetime(2026, 9, 27, tzinfo=UTC)
    plane.release_task("task-1", plane.list_checkouts()[0]["worker_id"])
    first = plane.checkout_task("task-2", "worker-a", lease_s=0, now=moment)
    assert first["expired"] is True
    second = plane.checkout_task(
        "task-2", "worker-b", lease_s=30, now=moment + timedelta(seconds=1)
    )
    assert second["worker_id"] == "worker-b"
    with pytest.raises(TaskNotHeld):
        plane.release_task("task-2", "worker-a")
    plane.release_task("task-2", "worker-b")


def test_gate_rollback_restores_an_approved_snapshot(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    proposed = plane.propose_gate(
        "budget:codey", {"limit": 1, "api_key": "sk-secretvalue"}, actor="ada"
    )
    assert proposed["revisions"][0]["snapshot"]["api_key"] == "[scrubbed]"
    assert "sk-secretvalue" not in json.dumps(proposed)
    pending = proposed["pending_revision"]
    decided = plane.decide_gate("budget:codey", pending, approved=True, actor="ada")
    assert decided["snapshot"] == {"limit": 1, "api_key": "[scrubbed]"}
    newer = plane.propose_gate("budget:codey", {"limit": 9}, actor="ada")
    plane.decide_gate(
        "budget:codey", newer["pending_revision"], approved=True, actor="ada"
    )
    restored = plane.rollback_gate(
        "budget:codey", pending, actor="ada", reason="too high"
    )
    assert restored["snapshot"] == {"limit": 1, "api_key": "[scrubbed]"}
    assert restored["revisions"][-1]["action"] == "rollback"
    assert restored["revisions"][-1]["restores"] == pending
    with pytest.raises(ApprovalError):
        plane.rollback_gate("budget:codey", pending, actor="ada")


def test_pending_proposal_supersedes_the_previous_one(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    first = plane.propose_gate("roster:research", {"name": "A"}, actor="ada")
    second = plane.propose_gate("roster:research", {"name": "B"}, actor="ada")
    statuses = {row["revision"]: row["status"] for row in second["revisions"]}
    assert statuses[first["pending_revision"]] == "superseded"
    with pytest.raises(ApprovalError):
        plane.decide_gate(
            "roster:research", first["pending_revision"], approved=True, actor="ada"
        )
    decided = plane.decide_gate(
        "roster:research", second["pending_revision"], approved=False, actor="ada"
    )
    assert decided["current_revision"] == 0
    with pytest.raises(ApprovalError):
        plane.rollback_gate("roster:research", second["pending_revision"], actor="ada")


def test_org_pack_scrubs_secrets_and_renames_collisions(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    from swarm.core.team_rosters import get_roster, upsert_roster

    upsert_roster(
        {
            "id": "child",
            "name": "Existing child",
            "members": [{"id": "kept", "kind": "api", "role": "default"}],
        }
    )
    pack = plane.export_org(
        name="Acme",
        teams=[
            {
                "id": "child",
                "name": "Child",
                "members": [
                    {
                        "id": "jeeves",
                        "kind": "api",
                        "role": "default",
                        "api_key": "sk-live-secret-value",
                        "description": "https://hooks.example/a?token=abcdef&ok=1",
                    }
                ],
                "chief_of_staff_id": "jeeves",
                "chief_of_staff_instructions": "Bearer supersecretvalue1",
            },
            {
                "id": "parent",
                "name": "Parent",
                "members": [
                    {
                        "id": "child",
                        "kind": "team",
                        "team_id": "child",
                        "role": "default",
                    }
                ],
            },
        ],
        routines=[
            {
                "id": "routine-1",
                "agent_id": "jeeves",
                "name": "Ship notes",
                "instruction": "Use ghp_abcdefghijklmnop carefully.",
                "trigger": {"kind": "interval", "seconds": 3600},
            }
        ],
        budgets=[
            {
                "scope": "seat",
                "scope_id": "jeeves",
                "token_limit": 20,
                "cost_micros_limit": None,
                "hard_stop": True,
            }
        ],
    )
    encoded = json.dumps(pack)
    assert "sk-live-secret-value" not in encoded
    assert "ghp_abcdefghijklmnop" not in encoded
    assert "token=abcdef" not in encoded
    assert "Bearer supersecretvalue1" not in encoded
    assert pack["kind"] == "os-org-pack"
    assert any(path.endswith("api_key") for path in pack["scrubbed"])
    child = next(team for team in pack["teams"] if team["id"] == "child")
    assert "api_key" not in child["members"][0]
    assert child["members"][0]["description"].endswith("ok=1")
    assert "token" not in child["members"][0]["description"]

    installed = plane.install_org_pack(pack, on_collision="rename")
    assert {"from": "child", "to": "child-2"} in installed["renames"]
    assert get_roster("child")["name"] == "Existing child"
    assert get_roster("child-2")["name"] == "Child"
    parent = get_roster("parent")
    nested = parent["members"][0]
    assert nested["team_id"] == "child-2"
    assert plane.list_budgets()[0]["scope_id"] == "jeeves"
    assert plane.list_budgets()[0]["tokens_used"] == 0
    again = plane.install_org_pack(pack, on_collision="skip")
    assert again["routines_created"] == 0
    assert again["routines_skipped"]
    assert "child" in again["skipped_teams"]
    with pytest.raises(OrgPackError):
        plane.install_org_pack(pack, on_collision="error")


def test_corrupt_store_is_not_overwritten(tmp_path, monkeypatch):
    path = tmp_path / "plane.json"
    path.write_text("not-json", encoding="utf-8")
    monkeypatch.setenv("SWARM_OPERATOR_PLANE_PATH", str(path))
    with pytest.raises(OperatorPlaneError):
        plane.list_budgets()
    assert path.read_text(encoding="utf-8") == "not-json"


def test_fire_routine_blocks_overlap_and_hard_stop(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = routines.create_routine(
        "codey",
        {
            "name": "Notes",
            "instruction": "Write the note.",
            "trigger": {"kind": "interval", "seconds": 60},
        },
    )
    calls = {"n": 0}
    started = threading.Event()
    release = threading.Event()

    def runner(_agent, _instruction, _source):
        calls["n"] += 1
        started.set()
        assert release.wait(3)

    routines.set_instruction_runner(runner)
    holder: dict = {}

    def hold():
        holder["routine"] = routines.fire_routine(
            "codey", created["id"], source="test_run"
        )

    thread = threading.Thread(target=hold)
    thread.start()
    assert started.wait(3)
    blocked = routines.fire_routine("codey", created["id"], source="test_run")
    release.set()
    thread.join(3)
    assert calls["n"] == 1
    assert holder["routine"]["history"][0]["status"] == "success"
    assert blocked["history"][0]["status"] == "error"
    assert "already checked out" in blocked["history"][0]["error"]

    plane.set_budget_policy(
        scope="seat", scope_id="codey", token_limit=2, hard_stop=True
    )
    routines.set_instruction_runner(
        lambda *_args: calls.__setitem__("n", calls["n"] + 1)
    )
    ran = routines.fire_routine("codey", created["id"], source="run_now", token_cost=2)
    assert ran["history"][0]["status"] == "success"
    assert calls["n"] == 2
    stopped = routines.fire_routine(
        "codey", created["id"], source="run_now", token_cost=1
    )
    assert calls["n"] == 2
    assert "hard-stop" in stopped["history"][0]["error"]
    assert plane.list_checkouts() == []

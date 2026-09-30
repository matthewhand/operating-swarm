"""Hermetic tests for scripts/verify_trueforge_upgrade.py (#1307).

No network: every check's transport call is injected. Cases cover a healthy
instance, an offline instance, a changed turn-state shape, and a
removed/renamed field — each must produce the right PASS/FAIL without raising.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

from swarm.core.remotes import HealthResult, OperateResult

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_trueforge_upgrade.py"


def _load_harness():
    spec = importlib.util.spec_from_file_location("verify_trueforge_upgrade", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(spec.name, None)
    return module


harness = _load_harness()
CONFIG = {"remotes": {}}


def _health(state="UP", ok=True, detail="tcp 1ms · http 200 on /healthz"):
    return HealthResult(
        remote="trueforge",
        ok=ok,
        state=state,
        detail=detail,
        http_status=200 if ok else None,
        version={"version": "9.9.9"} if ok else None,
    )


def _sessions():
    return [
        {
            "id": "sess-1",
            "agent": "orchestrator",
            "title": "thread one",
            "created_at": "2026-01-01",
            "updated_at": "2026-01-02",
        }
    ]


def _list_result(sessions=None, data=None):
    payload = data if data is not None else {
        "data": [{"id": "agent-1", "name": "orchestrator"}],
        "rows_are": "agents",
        "resume_key": "session_id",
        "sessions": _sessions() if sessions is None else sessions,
    }
    return OperateResult(
        remote="trueforge",
        op="list",
        ok=True,
        detail="TrueForge listed 1 agent(s)",
        http_status=200,
        data=payload,
    )


def _send_result(session_id="sess-1", turn=None, text="OK"):
    return OperateResult(
        remote="trueforge",
        op="send",
        ok=True,
        detail=text,
        http_status=200,
        data={
            "session_id": session_id,
            "turn_id": "turn-1",
            "turn": turn if turn is not None else {"state": {"status": "done"}},
            "text": text,
            "events": [{"type": "model.message", "content": text}],
        },
    )


def _op_ok(_rid, op, **kwargs):
    if op == "list":
        return _list_result()
    assert kwargs.get("session_id") == "sess-1"
    return _send_result()


def _probe_ok(
    *,
    sessions_rows=1,
    agents_rows=1,
    sessions_status=200,
    agents_status=200,
    sessions_row_keys=None,
):
    return {
        "instance": "trueforge",
        "errors": [],
        "agents_status": agents_status,
        "agents_rows": agents_rows,
        "agents_keys": ["data"],
        "agents_row_keys": ["id", "name"],
        "sessions_status": sessions_status,
        "sessions_rows": sessions_rows,
        "sessions_keys": ["data"],
        "sessions_row_keys": sessions_row_keys or ["id", "agent", "title", "created_at"],
    }


def _fake_module():
    return SimpleNamespace(chat_thread=lambda _request: None)


def _by_check(results):
    return {row.check: row for row in results}


def test_healthy_instance_all_checks_pass():
    results = harness.verify_instance(
        "trueforge",
        config=CONFIG,
        health_fn=lambda _rid, **_kwargs: _health(),
        operate_fn=_op_ok,
        probe_fn=lambda _rid, **_kwargs: _probe_ok(),
        hydrate_importer=_fake_module,
        hydrate_live_probe=lambda: [{"role": "user", "content": "hi"}],
    )
    by = _by_check(results)
    assert by["trueforge: health"].status == harness.PASS
    assert by["trueforge: list"].status == harness.PASS
    assert by["trueforge: send resume"].status == harness.PASS
    assert by["sample: required_actions"].status == harness.PASS
    assert by["sample: turn_state"].status == harness.PASS
    assert by["django: chat_persist_views import"].status == harness.PASS
    assert all(row.status == harness.PASS for row in results)


def test_offline_instance_degrades_to_fail_and_skip_without_raising():
    calls: list[tuple] = []

    def uninterruptible(*args, **_kwargs):
        calls.append(args)
        raise AssertionError("live call must not run while the gateway is DOWN")

    results = harness.verify_instance(
        "trueforge",
        config=CONFIG,
        health_fn=lambda _rid, **_kwargs: _health(
            state="DOWN", ok=False, detail="tcp 127.0.0.1:8791 refused/timed out"
        ),
        operate_fn=uninterruptible,
        probe_fn=uninterruptible,
        hydrate_importer=_fake_module,
    )
    by = _by_check(results)
    assert by["trueforge: health"].status == harness.FAIL
    assert "offline" in by["trueforge: health"].detail
    assert by["trueforge: list"].status == harness.SKIP
    assert by["trueforge: send resume"].status == harness.SKIP
    assert calls == []
    assert by["sample: required_actions"].status == harness.PASS
    assert by["sample: turn_state"].status == harness.PASS
    assert by["django: chat_persist_views import"].status == harness.PASS


def test_changed_turn_state_shape_fails_without_raising():
    res = harness.check_turn_state(live_turn={"state": {"phase": "done"}})
    assert res.status == harness.FAIL
    assert "unrecognized" in res.detail


def test_send_with_changed_live_turn_state_keeps_send_pass_and_state_fail():
    results = harness.verify_instance(
        "trueforge",
        config=CONFIG,
        health_fn=lambda _rid, **_kwargs: _health(),
        operate_fn=lambda _rid, op, **_kwargs: (
            _list_result() if op == "list" else _send_result(turn={"state": {"phase": "done"}})
        ),
        probe_fn=lambda _rid, **_kwargs: _probe_ok(),
        hydrate_importer=_fake_module,
    )
    by = _by_check(results)
    assert by["trueforge: send resume"].status == harness.PASS
    assert by["sample: turn_state"].status == harness.FAIL
    assert "live turn state unrecognized" in by["sample: turn_state"].detail


def test_renamed_list_fields_fail_honestly():
    renamed = OperateResult(
        remote="trueforge",
        op="list",
        ok=True,
        detail="listed",
        data={"agents": [{"uid": "agent-1"}], "sessions": [{"uid": "sess-1"}]},
    )
    lres, sessions = harness.check_list(
        "trueforge",
        operate_fn=lambda _rid, _op, **_kwargs: renamed,
        probe_fn=lambda _rid, **_kwargs: _probe_ok(),
    )
    assert lres.status == harness.FAIL
    assert "removed/renamed" in lres.detail
    assert sessions == []


def test_server_rows_that_parse_to_zero_fail_honestly():
    lres, sessions = harness.check_list(
        "trueforge",
        operate_fn=lambda _rid, _op, **_kwargs: _list_result(sessions=[]),
        probe_fn=lambda _rid, **_kwargs: _probe_ok(
            sessions_rows=3, sessions_row_keys=["uid", "name"]
        ),
    )
    assert lres.status == harness.FAIL
    assert "parsed 0" in lres.detail
    assert sessions == []


def test_renamed_required_actions_fails_detector():
    res = harness.check_pending_question(
        turn_data={
            "state": {
                "status": "done",
                "pending_actions": harness.SAMPLE_PAUSED_TURN["state"]["required_actions"],
            }
        },
        events=harness.SAMPLE_ASK_EVENTS,
    )
    assert res.status == harness.FAIL
    assert "required_actions" in res.detail


def test_missing_hydrate_view_fails_honestly():
    res = harness.check_hydrate(importer=lambda: SimpleNamespace())
    assert res.status == harness.FAIL
    assert "chat_thread" in res.detail


def test_send_that_mints_a_new_session_fails():
    minted = _send_result(session_id="sess-new")
    minted.data["session_created_for"] = "orchestrator"
    obs = harness.check_send(
        "trueforge", "sess-1", operate_fn=lambda *_args, **_kwargs: minted
    )
    assert obs.result.status == harness.FAIL
    assert "minted a NEW session" in obs.result.detail


def test_send_budget_raises_subfloor_env(monkeypatch):
    """A 90s SWARM_TRUEFORGE_TIMEOUT is reported as the 180s floor (#1307)."""
    monkeypatch.setenv("SWARM_TRUEFORGE_TIMEOUT", "90")
    resolved, label = harness.describe_send_budget(None, None)
    assert resolved == 180.0
    assert "floor" in label
    assert "90" in label
    assert "46-59s" in label


def test_send_budget_keeps_explicit_and_higher_env(monkeypatch):
    monkeypatch.setenv("SWARM_TRUEFORGE_TIMEOUT", "240")
    resolved, label = harness.describe_send_budget(None, None)
    assert resolved == 240.0
    assert "SWARM_TRUEFORGE_TIMEOUT" in label
    explicit, explicit_label = harness.describe_send_budget(20, None)
    assert explicit == 20.0
    assert "--send-timeout" in explicit_label


def test_send_headroom_note_flags_the_measured_90s_budget():
    """46–59s of a 90s budget is tight; the same turn against 180s is not."""
    note = harness.send_headroom_note(59.0, 90.0)
    assert "headroom tight" in note
    assert "59.0s of 90s" in note
    assert harness.send_headroom_note(46.0, 90.0)
    assert harness.send_headroom_note(50.0, 180.0) == ""
    assert "headroom tight" in harness.send_headroom_note(90.0, 180.0)


def test_check_exceptions_become_fail_not_raise():
    def boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    assert harness.check_health("trueforge", health_fn=boom).status == harness.FAIL
    lres, sessions = harness.check_list("trueforge", operate_fn=boom, probe_fn=boom)
    assert lres.status == harness.FAIL
    assert sessions == []
    obs = harness.check_send("trueforge", "sess-1", operate_fn=boom)
    assert obs.result.status == harness.FAIL
    assert obs.live_turn is None
    assert harness.check_hydrate(importer=boom).status == harness.FAIL

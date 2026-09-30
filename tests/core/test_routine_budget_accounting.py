"""Routine runs must debit the seat budget they are charged against.

Gap: every ``fire_routine`` call site omitted ``token_cost``, so the
seat-budget debit always charged 0. An operator who set a seat token
budget believed routine spend was capped against it; it never was.

Contracts:
- **Measured-first**: a live turn's usage (prompt + completion, measured
  from the messages actually sent and the reply actually produced) is what
  gets debited, and the run's history row records it.
- **Never double-charged**: the pre-run prompt charge and the post-run
  measured charge settle the *same* run, so the seat ends up debited the
  measured total exactly once.
- **Clamped**: negative / missing / non-numeric usage never debits a
  negative amount and never corrupts a balance.
- **Over-budget is a pre-run refusal**: a seat that cannot cover the run is
  refused before the instruction executes, and the refusal is a loud
  history row, not a silent no-op.
- **A refused post-run debit is reported, not swallowed**: the run stands,
  the row keeps the true usage, and the caller gets the refusal.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

from swarm.core import operator_plane as plane
from swarm.core import routines as store

pytestmark = pytest.mark.django_db

INSTRUCTION = "Investigate the flake and report back."


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_OPERATOR_PLANE_PATH", str(tmp_path / "plane.json"))
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _interval_routine(agent="codey", instruction=INSTRUCTION):
    return store.create_routine(
        agent,
        {
            "name": "Watch",
            "instruction": instruction,
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )


def _github_event_routine(agent="codey", instruction=INSTRUCTION):
    return store.create_routine(
        agent,
        {
            "name": "Triage",
            "instruction": instruction,
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "owner/repo",
            },
        },
    )


def _issue_opened_payload(*, number=42, author="octocat"):
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": "Fix the flux capacitor",
            "body": "It does not flux.",
            "user": {"login": author},
            "labels": [],
            "html_url": f"https://github.com/owner/repo/issues/{number}",
        },
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": author},
    }


def _seat(agent="codey", **kwargs):
    return plane.set_budget_policy(scope="seat", scope_id=agent, **kwargs)


def _used(agent="codey") -> int:
    rows = [row for row in plane.list_budgets() if row["scope_id"] == agent]
    return int(rows[0]["tokens_used"]) if rows else 0


def _newest_row(routine: dict) -> dict:
    return routine["history"][0]


def _patch_blueprint(monkeypatch, seen: dict):
    """Install a one-turn fake blueprint behind the module-level test seam."""

    class _Blueprint:
        async def run(self, messages, **kwargs):
            del kwargs
            seen["prompt"] = messages[-1]["content"]
            seen["runs"] = int(seen.get("runs", 0)) + 1
            yield "branch "
            yield "created"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del params
        seen["agent_id"] = agent_id
        return _Blueprint()

    monkeypatch.setattr(
        "swarm.core.routine_jobs.get_blueprint_instance",
        _fake_get_blueprint_instance,
    )


# --- regression: a run must move the balance ------------------------------------


def test_run_now_debits_the_seat_budget(tmp_path, monkeypatch):
    """Regression: before the fix this ran and left ``tokens_used == 0``."""
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=100_000, hard_stop=True)

    updated = store.run_now("codey", created["id"])

    assert _used("codey") > 0
    assert _newest_row(updated)["token_cost"] == _used("codey")
    assert _newest_row(updated)["status"] == "success"


def test_scheduled_run_debits_the_seat_budget(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    store.update_routine(
        "codey", created["id"], {"next_run": "2020-01-01T00:00:00+00:00"}
    )
    _seat("codey", token_limit=100_000, hard_stop=True)

    fired = store.tick_due_routines()

    assert len(fired) == 1
    assert _used("codey") > 0
    assert _newest_row(fired[0]["routine"])["token_cost"] == _used("codey")
    assert _newest_row(fired[0]["routine"])["status"] == "success"


def test_the_debit_is_the_instruction_prompt_estimate(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=100_000, hard_stop=True)
    expected = store.estimate_instruction_tokens(INSTRUCTION)

    updated = store.run_now("codey", created["id"])

    assert expected > 0
    assert _newest_row(updated)["token_cost"] == expected
    assert store.TOKEN_COST_NOTE


# --- clamping -------------------------------------------------------------------


@pytest.mark.parametrize("bogus", [None, -5, -1, "nope", float("nan"), float("inf")])
def test_run_now_never_debits_a_negative_amount(tmp_path, monkeypatch, bogus):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=100_000, hard_stop=True)
    # A runner that reports nonsense usage must not corrupt the balance.
    monkeypatch.setattr(
        "swarm.core.routines.estimate_instruction_tokens",
        lambda *_a, **_k: bogus,
    )

    updated = store.run_now("codey", created["id"])

    assert _used("codey") == 0
    assert _newest_row(updated)["status"] == "success"
    assert _newest_row(updated).get("token_cost", 0) == 0


def test_declared_negative_token_cost_is_clamped(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=100_000, hard_stop=True)

    updated = store.fire_routine("codey", created["id"], source="run_now", token_cost=-500)

    assert _used("codey") == 0
    assert _newest_row(updated).get("token_cost", 0) == 0


def test_clamp_tokens_is_an_integer_floor_at_zero():
    assert store.clamp_tokens(None) == 0
    assert store.clamp_tokens(-1) == 0
    assert store.clamp_tokens(float("nan")) == 0
    assert store.clamp_tokens(float("inf")) == 0
    assert store.clamp_tokens("nope") == 0
    assert store.clamp_tokens([]) == 0
    assert store.clamp_tokens(1.9) == 1
    assert store.clamp_tokens("12") == 12
    assert store.clamp_tokens(7) == 7


# --- over-budget semantics: refuse before the run -------------------------------


def test_over_budget_seat_refuses_before_running_the_instruction(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    ran: list[str] = []
    store.set_instruction_runner(lambda *_a: ran.append("ran"))
    _seat("codey", token_limit=5, hard_stop=True)
    # The pre-run prompt charge alone exhausts the seat.
    created = _interval_routine(instruction="Investigate the flake. " * 200)

    refused = store.run_now("codey", created["id"])

    assert ran == [], "an out-of-budget seat must not execute the instruction"
    row = _newest_row(refused)
    assert row["status"] == "error"
    assert "hard-stop" in row["error"]
    assert row.get("token_cost", 0) == 0
    assert plane.list_checkouts() == []


def test_already_exhausted_seat_refuses_before_running(tmp_path, monkeypatch):
    """A budget sized to exactly one run runs once, then refuses."""
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    ran: list[str] = []
    store.set_instruction_runner(lambda *_a: ran.append("ran"))
    one_run = store.estimate_instruction_tokens(INSTRUCTION)
    assert one_run > 0
    _seat("codey", token_limit=one_run, hard_stop=True)

    first = store.run_now("codey", created["id"])
    assert _newest_row(first)["status"] == "success"
    assert _used("codey") == one_run

    second = store.run_now("codey", created["id"])

    assert len(ran) == 1
    assert _newest_row(second)["status"] == "error"
    assert "hard-stop" in _newest_row(second)["error"]
    assert _used("codey") == one_run, "a refused run must not debit the seat"


def test_soft_budget_records_the_overrun_instead_of_refusing(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=1, hard_stop=False)

    first = store.run_now("codey", created["id"])
    second = store.run_now("codey", created["id"])

    assert _newest_row(first)["status"] == "success"
    assert _newest_row(second)["status"] == "success"
    assert _used("codey") > 1


def test_no_budget_configured_means_unlimited(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()

    updated = store.run_now("codey", created["id"])

    assert _used("codey") == 0
    assert _newest_row(updated)["status"] == "success"
    assert _newest_row(updated)["token_cost"] > 0


# --- measured usage from a live turn --------------------------------------------


def test_measured_turn_usage_is_debited_on_the_run_row(tmp_path, monkeypatch):
    """The webhook path: a real turn's usage replaces the prompt estimate."""
    _isolate(tmp_path, monkeypatch)
    seen: dict[str, object] = {}
    _patch_blueprint(monkeypatch, seen)
    monkeypatch.setenv("SWARM_ROUTINES_LIVE", "1")
    created = _github_event_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    conversation_id = store.github_event_conversation_id(
        store.parse_github_webhook_event(_issue_opened_payload(), "issues")
    )

    fired = store.deliver_github_event(_issue_opened_payload(), event_header="issues")
    store.wait_for_live_jobs()

    assert len(fired) == 1
    assert seen["runs"] == 1
    row = _newest_row(fired[0]["routine"])
    assert row["conversation_id"] == conversation_id
    measured = store.routine_token_usage_for_conversation("codey", conversation_id)
    assert measured is not None
    assert measured["basis"] == store.TOKEN_BASIS_MEASURED
    assert measured["tokens"] > 0
    assert measured["refused"] is False
    # The run's row carries the measured total, and the seat was debited
    # that total once (the pre-run prompt charge is subsumed, not doubled).
    assert store.get_routine("codey", created["id"])["history"][0]["token_cost"] == measured["tokens"]
    assert _used("codey") == measured["tokens"]
    statuses = store.live_job_status("codey")
    assert "measured" in statuses[-1]["detail"]


def test_measured_usage_larger_than_the_estimate_debits_only_the_difference(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _github_event_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    fired = store.deliver_github_event(_issue_opened_payload(), event_header="issues")
    conversation_id = _newest_row(fired[0]["routine"])["conversation_id"]
    pre_run_used = _used("codey")
    assert pre_run_used > 0

    store.record_routine_token_usage(
        "codey", conversation_id, tokens=pre_run_used + 500, basis=store.TOKEN_BASIS_MEASURED
    )

    assert _used("codey") == pre_run_used + 500
    assert _newest_row(store.get_routine("codey", created["id"]))["token_cost"] == pre_run_used + 500


def test_single_turn_cap_is_preserved(tmp_path, monkeypatch):
    """Automated spend is still bounded to one turn per run (#862)."""
    _isolate(tmp_path, monkeypatch)
    seen: dict[str, object] = {}
    _patch_blueprint(monkeypatch, seen)

    asyncio.run(
        store.run_routine_agent_job(
            "codey",
            "Investigate and fix it now.",
            conversation_id="conv-one-turn",
            max_turns=9,
        )
    )

    assert seen["prompt"] == "Investigate and fix it now."
    assert seen["runs"] == 1


# --- settle_routine_tokens -------------------------------------------------------


def test_settle_records_the_overrun_on_a_soft_budget(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=2, hard_stop=False)
    store.run_now("codey", created["id"])

    settle = store.settle_routine_tokens(
        "codey", created["id"], tokens=10_000, basis=store.TOKEN_BASIS_MEASURED
    )

    assert settle["tokens"] == 10_000
    assert settle["refused"] is False
    assert _used("codey") == 10_000
    assert _newest_row(store.get_routine("codey", created["id"]))["token_cost"] == 10_000


def test_settle_refuses_a_post_run_charge_that_would_bust_a_hard_stop(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=50, hard_stop=True)
    store.run_now("codey", created["id"])

    settle = store.settle_routine_tokens(
        "codey", created["id"], tokens=10_000, basis=store.TOKEN_BASIS_MEASURED
    )

    assert settle["refused"] is True
    assert "hard-stop" in settle["reason"]
    assert _used("codey") < 10_000
    budgets = [row for row in plane.list_budgets() if row["scope_id"] == "codey"]
    assert budgets[0]["stopped"] is True
    # The run's true usage is still on the row: a refusal is not a silent 0.
    assert _newest_row(store.get_routine("codey", created["id"]))["token_cost"] == 10_000


def test_settle_is_idempotent(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    store.run_now("codey", created["id"])

    first = store.settle_routine_tokens(
        "codey", created["id"], tokens=500, basis=store.TOKEN_BASIS_MEASURED
    )
    after_first = _used("codey")
    second = store.settle_routine_tokens(
        "codey", created["id"], tokens=500, basis=store.TOKEN_BASIS_MEASURED
    )

    assert first["charged"] > 0
    assert first["charged_total"] == _used("codey")
    assert second["charged"] == 0
    assert second["charged_total"] == _used("codey")
    assert _used("codey") == after_first


def test_settle_with_no_budget_is_a_no_op_that_still_records(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    store.run_now("codey", created["id"])

    settle = store.settle_routine_tokens(
        "codey", created["id"], tokens=321, basis=store.TOKEN_BASIS_MEASURED
    )

    assert settle["tokens"] == 321
    assert settle["charged"] == 0
    assert settle["refused"] is False
    assert _used("codey") == 0
    assert _newest_row(store.get_routine("codey", created["id"]))["token_cost"] == 321


def test_settle_unknown_routine_raises(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    with pytest.raises(KeyError):
        store.settle_routine_tokens("codey", "nope", tokens=5, basis=store.TOKEN_BASIS_MEASURED)


def test_settle_clamps_negative_usage(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    store.run_now("codey", created["id"])
    before = _used("codey")

    settle = store.settle_routine_tokens(
        "codey", created["id"], tokens=-99, basis=store.TOKEN_BASIS_MEASURED
    )

    assert settle["tokens"] == 0
    assert settle["charged"] == 0
    assert _used("codey") == before


def test_pending_measured_usage_lands_on_the_row_it_raced(tmp_path, monkeypatch):
    """The live thread can finish before fire_routine writes the history row."""
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)

    stash = store.record_routine_token_usage(
        "codey", "conv-race", tokens=4242, basis=store.TOKEN_BASIS_MEASURED
    )
    assert stash["pending"] is True
    assert store.routine_token_usage_for_conversation("codey", "conv-race") is None

    updated = store.fire_routine(
        "codey",
        created["id"],
        source="github_webhook",
        conversation_id="conv-race",
    )

    row = _newest_row(updated)
    assert row["token_cost"] == 4242
    assert _used("codey") == 4242
    drained = store.routine_token_usage_for_conversation("codey", "conv-race")
    assert drained is not None
    assert drained["tokens"] == 4242
    assert drained["basis"] == store.TOKEN_BASIS_MEASURED


def test_unattributable_usage_is_never_charged_to_another_run(tmp_path, monkeypatch):
    """A measurement with no conversation and no routine is not guessed at."""
    _isolate(tmp_path, monkeypatch)
    created = _interval_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    store.run_now("codey", created["id"])
    before_used = _used("codey")
    before_row = _newest_row(store.get_routine("codey", created["id"]))["token_cost"]

    result = store.record_routine_token_usage("codey", "", tokens=500_000)

    assert result["pending"] is False
    assert result["charged"] == 0
    assert _used("codey") == before_used
    assert _newest_row(store.get_routine("codey", created["id"]))["token_cost"] == before_row
    assert store.routine_token_usage_for_conversation("codey", "") is None


def test_concurrent_fire_and_settle_keep_both_writes(tmp_path, monkeypatch):
    """A job thread settling a run must not clobber a concurrent fire."""
    _isolate(tmp_path, monkeypatch)
    created = _github_event_routine()
    _seat("codey", token_limit=1_000_000, hard_stop=True)
    store.fire_routine(
        "codey", created["id"], source="github_webhook", conversation_id="conv-x"
    )
    failures: list[Exception] = []

    def settle():
        try:
            store.settle_routine_tokens(
                "codey", created["id"], tokens=4321, basis=store.TOKEN_BASIS_MEASURED
            )
        except Exception as exc:  # pragma: no cover - failure detail
            failures.append(exc)

    def fire():
        try:
            store.fire_routine("codey", created["id"], source="run_now")
        except Exception as exc:  # pragma: no cover - failure detail
            failures.append(exc)

    threads = [threading.Thread(target=settle), threading.Thread(target=fire)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)

    assert failures == []
    rows = store.get_routine("codey", created["id"])["history"]
    assert len(rows) == 2, "one write was lost"
    assert any(row.get("token_cost") == 4321 for row in rows)


def test_estimate_and_measure_never_raise(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert store.estimate_instruction_tokens("") == 0
    assert store.estimate_instruction_tokens(INSTRUCTION) > 0
    assert store.measure_turn_tokens([{"role": "user", "content": "hi"}], "there") > 0
    assert store.measure_turn_tokens(None, None) == 0

    def _boom(*_a, **_k):
        raise RuntimeError("tokenizer exploded")

    monkeypatch.setattr("swarm.utils.context_utils.get_token_count", _boom)
    assert store.estimate_instruction_tokens("x") == 0
    assert store.measure_turn_tokens([{"role": "user", "content": "x"}], "y") == 0

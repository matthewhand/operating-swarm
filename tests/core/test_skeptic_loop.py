"""Skeptic rework loop engine + roster wiring tests.

The engine (``skeptic_loop.run_skeptic_rework_loop``) is transport-agnostic:
these tests use plain closures, mirroring how the chat consumer adapts it.
"""

from __future__ import annotations

import pytest

from swarm.core.skeptic_loop import (
    MAX_SKEPTIC_ROUNDS_CAP,
    run_skeptic_rework_loop,
)
from swarm.core.team_rosters import (
    reset_team_rosters,
    save_team_rosters,
    skeptic_blueprint_for_agent,
)


@pytest.fixture(autouse=True)
def _clean_rosters(monkeypatch):
    monkeypatch.setenv("SWARM_TEST_MODE", "1")
    reset_team_rosters({})
    yield
    save_team_rosters()


def _seed_skeptic_roster():
    reset_team_rosters(
        {
            "alpha": {
                "id": "alpha",
                "name": "Alpha Team",
                "members": [
                    {"id": "worker", "kind": "blueprint", "source": "blueprint:jeeves", "role": "default"},
                    {
                        "id": "rev",
                        "kind": "blueprint",
                        "source": "blueprint:skeptic",
                        "role": "skeptic",
                    },
                ],
                "wires": {"handoff": True, "as_tool": False},
            }
        }
    )
    save_team_rosters()


class TestSkepticBlueprintForAgent:
    def test_resolves_wired_skeptic(self):
        _seed_skeptic_roster()
        assert skeptic_blueprint_for_agent("alpha", "jeeves") == "skeptic"

    def test_no_skeptic_returns_none(self):
        _seed_skeptic_roster()
        assert skeptic_blueprint_for_agent("alpha", "no-such-agent") is None

    def test_disabled_wires_return_none(self):
        _seed_skeptic_roster()
        from swarm.core.team_rosters import get_roster, upsert_roster

        roster = get_roster("alpha")
        roster["wires"] = {"handoff": False, "as_tool": False}
        upsert_roster(roster)
        assert skeptic_blueprint_for_agent("alpha", "jeeves") is None

    def test_missing_roster_returns_none(self):
        assert skeptic_blueprint_for_agent("ghost", "jeeves") is None


class TestRunSkepticReworkLoop:
    @pytest.mark.asyncio
    async def test_pass_on_first_review_runs_worker_once(self):
        worker_prompts: list[str] = []

        async def worker(prompt: str) -> str:
            worker_prompts.append(prompt)
            return "done"

        async def review(_prompt, _output):
            return "YES"

        result = await run_skeptic_rework_loop(
            prompt="do it",
            first_output="done",
            worker_fn=worker,
            review_fn=review,
        )
        assert worker_prompts == []
        assert result.rounds == 0
        assert result.attempts == 1
        assert result.accomplished is True

    @pytest.mark.asyncio
    async def test_fail_then_pass_runs_one_rework_round(self):
        prompts: list[str] = []

        async def worker(prompt: str) -> str:
            prompts.append(prompt)
            return "fixed output"

        verdicts = iter(["NO\nmissing the summary section", "YES"])

        async def review(_prompt, _output):
            return next(verdicts)

        result = await run_skeptic_rework_loop(
            prompt="write summary.md",
            first_output="talked but wrote nothing",
            worker_fn=worker,
            review_fn=review,
        )
        assert len(prompts) == 1
        assert "Skeptic findings" in prompts[0]
        assert "missing the summary section" in prompts[0]
        assert result.rounds == 1
        assert result.attempts == 2
        assert result.accomplished is True
        assert result.findings == ["missing the summary section"]

    @pytest.mark.asyncio
    async def test_retries_bounded_by_max_rounds(self):
        rounds_seen: list[int] = []

        async def worker(_prompt: str) -> str:
            return "still incomplete"

        async def review(_prompt, _output):
            return "NO\nstill wrong"

        async def on_round(round_i, _rework, _output):
            rounds_seen.append(round_i)
            return True

        result = await run_skeptic_rework_loop(
            prompt="p",
            first_output="bad",
            worker_fn=worker,
            review_fn=review,
            max_rounds=3,
            on_round=on_round,
        )
        assert rounds_seen == [1, 2, 3]
        assert result.rounds == 3
        assert result.attempts == 4
        assert result.accomplished is False
        assert len(result.findings) == 3

    @pytest.mark.asyncio
    async def test_cost_guardrail_abort_stops_spending(self):
        calls: list[int] = []

        async def worker(_prompt: str) -> str:
            calls.append(1)
            return "reworked"

        async def review(_prompt, _output):
            return "NO\nkeep failing"

        async def on_round(_round_i, _rework, _output):
            return False  # host pulls the brake after the first rework

        result = await run_skeptic_rework_loop(
            prompt="p",
            first_output="bad",
            worker_fn=worker,
            review_fn=review,
            max_rounds=5,
            on_round=on_round,
        )
        assert len(calls) == 1
        assert result.accomplished is None  # honestly unknown — no final review ran
        assert result.findings  # the open critique stands

    @pytest.mark.asyncio
    async def test_round_budget_is_clamped_to_cap(self):
        calls: list[str] = []

        async def worker(_prompt: str) -> str:
            calls.append("run")
            return "nope"

        async def review(_prompt, _output):
            return "NO\nnope"

        result = await run_skeptic_rework_loop(
            prompt="p",
            first_output="bad",
            worker_fn=worker,
            review_fn=review,
            max_rounds=999,
        )
        assert result.rounds == MAX_SKEPTIC_ROUNDS_CAP
        assert len(calls) == MAX_SKEPTIC_ROUNDS_CAP

    @pytest.mark.asyncio
    async def test_no_review_fn_short_circuits(self):
        result = await run_skeptic_rework_loop(
            prompt="p",
            first_output="out",
            worker_fn=lambda p: p,
            review_fn=None,
        )
        assert result.accomplished is None
        assert result.rounds == 0
        assert result.output == "out"

    @pytest.mark.asyncio
    async def test_prose_verdict_fails_closed(self):
        started: list[str] = []

        async def worker(prompt: str) -> str:
            started.append(prompt)
            return "reworked"

        async def review(_prompt, _output):
            return "I feel the answer is probably fine overall"  # no token

        result = await run_skeptic_rework_loop(
            prompt="p",
            first_output="out",
            worker_fn=worker,
            review_fn=review,
        )
        assert started, "prose verdict must not parse as PASS"
        assert result.accomplished is False

    def test_normalize_rounds(self):
        from swarm.core.skeptic_loop import normalize_skeptic_rounds

        assert normalize_skeptic_rounds(None) == 2
        assert normalize_skeptic_rounds("3") == 3
        assert normalize_skeptic_rounds(0) == 1
        assert normalize_skeptic_rounds(999) == MAX_SKEPTIC_ROUNDS_CAP

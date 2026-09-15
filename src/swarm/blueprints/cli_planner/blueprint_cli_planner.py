"""CLI Planner blueprint — Magentic-One-style ledger.

A planner CLI maintains a *task ledger*: it drafts an initial plan, delegates
subtasks to specialist worker CLIs one at a time, inspects each result, and
**re-plans on stall** — adding follow-up subtasks until the goal is met or a
round budget is exhausted — then synthesizes the final answer.

This is the iterative, reactive cousin of ``cli_map``: where map does one
decompose → distribute → reduce pass, planner loops, letting the plan grow in
response to what the workers actually produced.

Request model: ``model: "cli_planner"``. Config block ``cli_planner``:
``{ "planner": <cli>, "workers": [<cli>...] (or "worker": <cli>), "max_rounds": int }``
(falls back to ``cli_map`` / ``cli_fusion`` config). Per-request ``params`` may set
``planner``, ``workers``/``worker``, ``max_rounds``, ``workdir``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import CliKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.consensus import safe_json

logger = logging.getLogger(__name__)

DEFAULT_MAX_ROUNDS = 4
MAX_ROUNDS_CEILING = 10
MAX_SUBTASKS = 12

PLAN_TEMPLATE = """PLAN THE GOAL below by drafting a task ledger: an ordered list of concrete
subtasks a specialist agent can each carry out. Return ONLY a JSON object:
{{"subtasks": ["<subtask 1>", "<subtask 2>", ...]}}
Use as few subtasks as the goal needs.

Goal:
{goal}
"""

REPLAN_TEMPLATE = """PROGRESS REVIEW of work on this goal:
<goal>
{goal}
</goal>

Completed subtasks and their results so far:
{completed}

Decide whether the goal is met. Return ONLY a JSON object:
{{"done": true or false, "new_subtasks": ["<follow-up subtask>", ...], "synthesis": "<best answer to the goal so far>"}}
Add new_subtasks ONLY if something essential is still missing; otherwise return an empty list and set done to true.
"""

SYNTH_TEMPLATE = """The goal was:
<goal>
{goal}
</goal>

All completed subtasks and results:
{completed}

Write the final answer to the goal, integrating the results. Return only the answer.
"""


class CliPlannerBlueprint(CliKindBase):
    """Plan, delegate, review, re-plan on stall, then synthesize."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_planner",
        "title": "CLI Planner (Magentic-One-style ledger)",
        "description": (
            "A planner maintains a task ledger, delegates subtasks to worker CLIs, "
            "reviews results, and re-plans on stall until the goal is met, then "
            "synthesizes. The iterative cousin of cli_map."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "planner", "magentic", "multi-agent", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_planner", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[str | None, list[str]]:
        """Resolve (planner, workers), falling back to cli_map / cli_fusion config."""
        pc = (self._config or {}).get("cli_planner") or {}
        mc = (self._config or {}).get("cli_map") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}
        preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}

        planner = params.get("planner") or pc.get("planner") or mc.get("planner") or fusion.get("default_cli")
        workers = params.get("workers") or pc.get("workers") or mc.get("workers")
        if not workers:
            single = params.get("worker") or pc.get("worker") or mc.get("worker")
            workers = [single] if single else (preset.get("panel") or registry.available() or registry.names())

        known = set(registry.names())
        workers = [w for w in (workers or []) if w in known]
        if planner and planner not in known:
            planner = None
        return planner, workers

    def _max_rounds(self, params: dict[str, Any]) -> int:
        raw = params.get("max_rounds", ((self._config or {}).get("cli_planner") or {}).get("max_rounds", DEFAULT_MAX_ROUNDS))
        try:
            return max(1, min(int(raw), MAX_ROUNDS_CEILING))
        except (TypeError, ValueError):
            return DEFAULT_MAX_ROUNDS

    @staticmethod
    def _completed_block(completed: list[tuple[str, str, str]]) -> str:
        if not completed:
            return "(nothing completed yet)"
        return "\n\n".join(f"### {sub}\n_(by {w})_\n{text}" for sub, w, text in completed)

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        goal = support.render_prompt(messages)
        if not goal:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        planner, workers = self._resolve(params, registry)
        if not planner:
            yield support.message_chunk(
                "No planner CLI is configured for cli_planner. Add a 'cli_planner' "
                "block (or a 'cli_map'/'cli_fusion' default) to your swarm config "
                "(see docs/CLI_FUSION.md).",
                final=True,
            )
            return
        if not workers:
            yield support.message_chunk("No worker CLIs are configured for cli_planner.", final=True)
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return
        max_rounds = self._max_rounds(params)

        # 1. Initial plan → the ledger of open subtasks.
        yield support.progress_chunk(f"_Planning with `{planner}`…_")
        pres = await registry.get(planner).run(PLAN_TEMPLATE.format(goal=goal), workdir=workdir)
        plan = safe_json(pres.text) if pres.ok else None
        open_q = [str(s) for s in (plan or {}).get("subtasks", []) if str(s).strip()][:MAX_SUBTASKS]
        if not open_q:
            yield support.message_chunk("Planner produced no subtasks.", final=True)
            return
        yield support.progress_chunk(f"_Ledger seeded with {len(open_q)} subtask(s)._")

        completed: list[tuple[str, str, str]] = []
        synthesis: str | None = None
        added_total = 0

        # 2. Work the ledger, re-planning after each subtask.
        for round_i in range(max_rounds):
            if not open_q:
                break
            subtask = open_q.pop(0)
            worker = registry.get(workers[round_i % len(workers)])
            yield support.progress_chunk(
                f"_Round {round_i + 1}/{max_rounds}: `{worker.name}` on “{subtask[:60]}”…_"
            )
            res = await worker.run(subtask, workdir=workdir)
            if res.ok and res.text.strip():
                completed.append((subtask, worker.name, res.text))
            else:
                yield support.progress_chunk(f"_• {worker.name} failed on a subtask ({res.error or 'empty'})._")

            # 3. Re-plan: is the goal met, or does the ledger need more?
            rres = await registry.get(planner).run(
                REPLAN_TEMPLATE.format(goal=goal, completed=self._completed_block(completed)),
                workdir=workdir,
            )
            verdict = safe_json(rres.text) if rres.ok else None
            if isinstance(verdict, dict):
                if isinstance(verdict.get("synthesis"), str) and verdict["synthesis"].strip():
                    synthesis = verdict["synthesis"].strip()
                if bool(verdict.get("done")):
                    yield support.progress_chunk(f"_Planner marked the goal met after round {round_i + 1}._")
                    break
                for ns in verdict.get("new_subtasks", []) or []:
                    if str(ns).strip() and added_total < MAX_SUBTASKS:
                        open_q.append(str(ns))
                        added_total += 1
                        yield support.progress_chunk(f"_Re-planned: added subtask “{str(ns)[:60]}”._")

        if not completed:
            yield support.message_chunk("Every worker subtask failed.", final=True)
            return

        # 4. Synthesize — prefer the planner's last synthesis, else a final synth call.
        worker_names = list(dict.fromkeys(w for _s, w, _r in completed))  # unique, order-preserving
        meta = support.backend_meta(worker_names, judge=planner)
        if synthesis:
            yield support.message_chunk(synthesis, final=True, meta=meta)
            return
        yield support.progress_chunk(f"_Synthesizing final answer with `{planner}`…_")
        sres = await registry.get(planner).run(
            SYNTH_TEMPLATE.format(goal=goal, completed=self._completed_block(completed)), workdir=workdir
        )
        if sres.ok and sres.text.strip():
            yield support.message_chunk(sres.text, final=True, meta=meta)
            return
        yield support.message_chunk(self._completed_block(completed), final=True, meta=meta)

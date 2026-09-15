"""CLI Map blueprint — decompose → distribute → reduce.

The complement to ``cli_fusion``. Where fusion sends the *same* question to a
panel and finds consensus, map splits *one task* into independent subtasks,
distributes them across worker CLIs in parallel, and reduces the results into a
single answer. Divide-and-conquer for scale, not redundancy for confidence.

Request model: ``model: "cli_map"``. Config block ``cli_map``:
``{ "planner": <cli>, "workers": [<cli>...] (or "worker": <cli>), "reducer": <cli>,
"max_items": int }`` (falls back to ``cli_fusion`` config). Per-request ``params``
may set ``items`` (explicit subtasks, skipping the planner), ``planner``,
``workers``/``worker``, ``reducer``, ``max_items``, ``workdir``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import CliKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.consensus import safe_json

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITEMS = 6
DEFAULT_MAX_CONCURRENCY = 8

PLAN_TEMPLATE = """Decompose the user's task into a list of INDEPENDENT subtasks that can each be
done separately and then combined. Return ONLY a JSON object:
{{"subtasks": ["<subtask 1>", "<subtask 2>", ...]}}
Use at most {max_items} subtasks; fewer is fine. If the task is atomic, return one.

Task:
{prompt}
"""

REDUCE_TEMPLATE = """The user's original task was:
<task>
{prompt}
</task>

It was split into subtasks, each completed independently by a worker agent:

{results}

Combine these into a single, coherent answer to the ORIGINAL task. Resolve any
overlap or contradiction. Return only the combined answer.
"""


class CliMapBlueprint(CliKindBase):
    """Plan → map across workers → reduce."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_map",
        "title": "CLI Map (decompose & distribute)",
        "description": (
            "Split one task into subtasks, distribute them across worker CLIs in "
            "parallel, and reduce the results into a single answer. Divide-and-"
            "conquer, complementing cli_fusion's consensus."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "map-reduce", "decompose", "multi-agent", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_map", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[str | None, list[str], str | None]:
        """Resolve (planner, workers, reducer), falling back to cli_fusion config."""
        mc = (self._config or {}).get("cli_map") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        planner = params.get("planner") or mc.get("planner") or fusion.get("default_cli")
        reducer = params.get("reducer") or mc.get("reducer") or fusion.get("default_cli")
        workers = params.get("workers") or mc.get("workers")
        if not workers:
            single = params.get("worker") or mc.get("worker")
            if single:
                workers = [single]
            else:
                preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}
                workers = preset.get("panel") or registry.available() or registry.names()

        known = set(registry.names())
        workers = [w for w in (workers or []) if w in known]
        if planner and planner not in known:
            planner = None
        if reducer and reducer not in known:
            reducer = None
        return planner, workers, reducer

    def _max_items(self, params: dict[str, Any]) -> int:
        raw = params.get("max_items", ((self._config or {}).get("cli_map") or {}).get("max_items", DEFAULT_MAX_ITEMS))
        try:
            return max(1, min(int(raw), 20))
        except (TypeError, ValueError):
            return DEFAULT_MAX_ITEMS

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        planner, workers, reducer = self._resolve(params, registry)
        if not workers:
            yield support.message_chunk(
                "No worker CLIs are configured for map. Add a 'cli_map' block (or a "
                "'cli_fusion' preset) to your swarm config (see docs/CLI_FUSION.md).",
                final=True,
            )
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return
        max_items = self._max_items(params)

        # 1. Decompose — explicit items, else the planner.
        items = params.get("items")
        if isinstance(items, list) and items:
            subtasks = [str(x) for x in items][:max_items]
            yield support.progress_chunk(f"_Using {len(subtasks)} explicit subtask(s)._")
        elif planner:
            yield support.progress_chunk(f"_Planning with `{planner}`…_")
            pres = await registry.get(planner).run(
                PLAN_TEMPLATE.format(prompt=prompt, max_items=max_items), workdir=workdir
            )
            plan = safe_json(pres.text) if pres.ok else None
            subtasks = [str(s) for s in (plan or {}).get("subtasks", []) if str(s).strip()][:max_items]
            if not subtasks:
                yield support.message_chunk("Planner produced no subtasks.", final=True)
                return
            yield support.progress_chunk(f"_Planned {len(subtasks)} subtask(s)._")
        else:
            yield support.message_chunk(
                "No planner is configured and no explicit `items` were provided.", final=True
            )
            return

        # 2. Map — distribute subtasks across workers (round-robin), in parallel.
        yield support.progress_chunk(
            f"_Mapping {len(subtasks)} subtask(s) across {', '.join(workers)}…_"
        )
        sem = asyncio.Semaphore(DEFAULT_MAX_CONCURRENCY)

        async def _do(index: int, subtask: str):
            worker = registry.get(workers[index % len(workers)])
            async with sem:
                res = await worker.run(subtask, workdir=workdir)
            return subtask, worker.name, res

        mapped = await asyncio.gather(*(_do(i, s) for i, s in enumerate(subtasks)))
        for subtask, wname, res in mapped:
            if not res.ok:
                yield support.progress_chunk(f"_• {wname} failed on a subtask: {res.error}_")
        ok = [(s, w, r) for s, w, r in mapped if r.ok]
        if not ok:
            yield support.message_chunk("All map workers failed.", final=True)
            return

        # 3. Reduce — a reducer CLI combines, else labeled concatenation.
        block = "\n\n".join(f"### Subtask: {s}\n_(by {w})_\n{r.text}" for s, w, r in ok)
        worker_names = list(dict.fromkeys(w for _s, w, _r in ok))  # unique, order-preserving
        if reducer:
            yield support.progress_chunk(f"_Reducing {len(ok)} result(s) with `{reducer}`…_")
            rres = await registry.get(reducer).run(
                REDUCE_TEMPLATE.format(prompt=prompt, results=block), workdir=workdir
            )
            if rres.ok and rres.text.strip():
                yield support.message_chunk(
                    rres.text, final=True, meta=support.backend_meta(worker_names, judge=reducer)
                )
                return
            yield support.progress_chunk(f"_Reducer failed ({rres.error}); returning subtask results._")
        yield support.message_chunk(block, final=True, meta=support.backend_meta(worker_names))

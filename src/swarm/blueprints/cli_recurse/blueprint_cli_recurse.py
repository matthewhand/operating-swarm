"""CLI Recurse — recursive divide-and-conquer that breaks a problem down to any depth.

Where ``cli_map`` decomposes *once* (one level: split → distribute → reduce), this
blueprint recurses: each subproblem is handed to a **fresh instance of this same
blueprint**, which decides whether to solve it directly or split it further. The
tree grows until every leaf is atomic — so an arbitrarily large problem is broken
into pieces of any size by leaning into recursion.

Each node does one of two things:

* **solve** (base case) — the problem is atomic, or a limiter stopped further
  splitting → a solver CLI answers it directly; or
* **split + synthesize** — a decomposer CLI returns N subproblems; each is solved
  by a recursively-instantiated child node; a synthesizer CLI combines the child
  answers into this node's answer.

Three limiters keep recursion finite and bounded (any one can stop a node):

* ``max_depth``        — hard cap on how deep the tree can go (leaves solve directly);
* ``max_subproblems``  — cap on fan-out width per node;
* ``max_nodes``        — a **shared global budget** across the whole tree; once spent,
  remaining nodes solve directly instead of splitting (prevents blow-up).

Request model: ``model: "cli_recurse"``. Config block ``cli_recurse``:
``{ "decomposer": <cli>, "solver": <cli>, "synthesizer": <cli>, "max_depth": int,
"max_subproblems": int, "max_nodes": int }`` (falls back to ``cli_fusion`` config).
Per-request ``params`` may override any of those plus ``show_tree``, ``workdir``.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import CliKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.consensus import safe_json

logger = logging.getLogger(__name__)

DEFAULT_MAX_DEPTH = 3
DEFAULT_MAX_SUBPROBLEMS = 4
DEFAULT_MAX_NODES = 20
HARD_DEPTH_CAP = 8
HARD_NODES_CAP = 200

# Sentinel key used to carry a node's answer back up through the progress stream.
_RESULT = "__recurse_result__"

DECOMPOSE_TEMPLATE = """You are decomposing a problem for a divide-and-conquer solver.

Decide: is this problem ATOMIC (small enough to answer well in a single step), or
should it be SPLIT into independent sub-problems that are each easier and can be
combined afterward? Only split when it genuinely helps; prefer atomic for simple
problems. Return ONLY a JSON object, no prose:
{{"atomic": true}}
  -- or --
{{"atomic": false, "subproblems": ["<sub 1>", "<sub 2>", ...]}}
Use at most {max_n} subproblems. Each must be self-contained and solvable alone.

Problem:
{prompt}
"""

SOLVE_TEMPLATE = """Solve this problem directly and concisely. Return only the answer.

Problem:
{prompt}
"""

SYNTH_TEMPLATE = """A problem was split into sub-problems, each solved independently:

{results}

Combine these into a single, coherent answer to the ORIGINAL problem below.
Resolve any overlap or contradiction. Return only the combined answer.

Original problem:
{prompt}
"""


class _Budget:
    """Shared, mutable global node budget across the whole recursion tree."""

    def __init__(self, total: int) -> None:
        self._remaining = total

    def remaining(self) -> int:
        return self._remaining

    def spend(self, n: int) -> None:
        self._remaining -= n


class CliRecurseBlueprint(CliKindBase):
    """Recursively break a problem down to any depth, then synthesize back up."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_recurse",
        "title": "CLI Recurse (recursive divide & conquer)",
        "description": (
            "Recursively decompose a problem: each subproblem is handed to a fresh "
            "instance of this blueprint that decides to solve it or split it again, "
            "until every leaf is atomic. Depth/width/node limiters bound the tree."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "recursive", "decompose", "divide-and-conquer", "multi-agent", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_recurse", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    # --- config resolution --------------------------------------------- #

    def _pick(self, role: str, params: dict[str, Any], registry: CliAdapterRegistry) -> str | None:
        """Resolve a single CLI for a role, falling back to cli_fusion's default."""
        cfg = (self._config or {}).get("cli_recurse") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}
        name = params.get(role) or cfg.get(role) or fusion.get("default_cli")
        known = set(registry.names())
        if name and name in known:
            return name
        # Fall back to the first available/known CLI.
        for cand in (registry.available() or registry.names()):
            return cand
        return None

    def _int(self, key: str, params: dict[str, Any], default: int, hard_cap: int) -> int:
        cfg = (self._config or {}).get("cli_recurse") or {}
        raw = params.get(key, cfg.get(key, default))
        try:
            return max(1, min(int(raw), hard_cap))
        except (TypeError, ValueError):
            return default

    # --- recursion ------------------------------------------------------ #

    async def _solve_node(self, prompt: str, depth: int, budget: _Budget, ctx: SimpleNamespace):
        """Async-generator recursion: yields progress chunks, then a {_RESULT: text} sentinel."""
        indent = "│  " * depth
        # Base case: a limiter (depth or global budget) forces a direct solve.
        forced = depth >= ctx.max_depth or budget.remaining() <= 0
        subproblems: list[str] = []

        if not forced:
            yield support.progress_chunk(f"{indent}├─ d{depth}: assessing…")
            dres = await ctx.decomposer.run(
                DECOMPOSE_TEMPLATE.format(prompt=prompt, max_n=ctx.max_subproblems), workdir=ctx.workdir
            )
            data = safe_json(dres.text) if dres.ok else None
            if isinstance(data, dict) and not data.get("atomic", False):
                subproblems = [str(s) for s in (data.get("subproblems") or []) if str(s).strip()]
                subproblems = subproblems[: ctx.max_subproblems]

        if not subproblems:
            reason = "limiter" if forced else "atomic"
            yield support.progress_chunk(f"{indent}└─ d{depth}: solving directly ({reason})")
            sres = await ctx.solver.run(SOLVE_TEMPLATE.format(prompt=prompt), workdir=ctx.workdir)
            ctx.backends.add(ctx.solver.name)
            ctx.leaves[0] += 1
            yield {_RESULT: sres.text if (sres.ok and sres.text.strip()) else f"(unsolved: {sres.error})"}
            return

        # Recurse: charge the global budget for the nodes we're about to create.
        budget.spend(len(subproblems))
        yield support.progress_chunk(
            f"{indent}├─ d{depth}: split into {len(subproblems)} (budget {max(0, budget.remaining())} left)"
        )

        child_answers: list[tuple[str, str]] = []
        for sub in subproblems:
            # Self-instantiate: each subproblem is handled by a fresh instance of
            # THIS blueprint, which may itself split further or solve directly.
            child = type(self)(config=self._config)
            child.set_params(self._params)
            answer = ""
            async for chunk in child._solve_node(sub, depth + 1, budget, ctx):
                if isinstance(chunk, dict) and _RESULT in chunk:
                    answer = chunk[_RESULT]
                else:
                    yield chunk  # bubble child progress up to the stream
            child_answers.append((sub, answer))

        # Synthesize this node's answer from its children.
        yield support.progress_chunk(f"{indent}└─ d{depth}: synthesizing {len(child_answers)}")
        block = "\n\n".join(f"### Sub-problem: {s}\n{a}" for s, a in child_answers)
        synres = await ctx.synthesizer.run(
            SYNTH_TEMPLATE.format(prompt=prompt, results=block), workdir=ctx.workdir
        )
        ctx.backends.add(ctx.synthesizer.name)
        yield {_RESULT: synres.text if (synres.ok and synres.text.strip()) else block}

    # --- entrypoint ----------------------------------------------------- #

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)
        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        decomposer = self._pick("decomposer", params, registry)
        solver = self._pick("solver", params, registry)
        synthesizer = self._pick("synthesizer", params, registry)
        if not (decomposer and solver and synthesizer):
            yield support.message_chunk(
                support.unconfigured_cli_message("No CLI is configured for cli_recurse"),
                final=True,
            )
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return

        ctx = SimpleNamespace(
            decomposer=registry.get(decomposer),
            solver=registry.get(solver),
            synthesizer=registry.get(synthesizer),
            max_depth=self._int("max_depth", params, DEFAULT_MAX_DEPTH, HARD_DEPTH_CAP),
            max_subproblems=self._int("max_subproblems", params, DEFAULT_MAX_SUBPROBLEMS, 12),
            workdir=workdir,
            backends=set(),
            leaves=[0],  # mutable counter shared across the tree
        )
        budget = _Budget(self._int("max_nodes", params, DEFAULT_MAX_NODES, HARD_NODES_CAP))

        yield support.progress_chunk(
            f"_Recursing (max_depth={ctx.max_depth}, max_subproblems={ctx.max_subproblems}, "
            f"max_nodes={budget.remaining()}) with `{decomposer}`…_"
        )

        answer = ""
        async for chunk in self._solve_node(prompt, 0, budget, ctx):
            if isinstance(chunk, dict) and _RESULT in chunk:
                answer = chunk[_RESULT]
            else:
                yield chunk

        yield support.progress_chunk(f"_Done — {ctx.leaves[0]} leaf problem(s) solved._")
        yield support.message_chunk(
            answer, final=True, meta=support.backend_meta(sorted(ctx.backends), judge=synthesizer)
        )

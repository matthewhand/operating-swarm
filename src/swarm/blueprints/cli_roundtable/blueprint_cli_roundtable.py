"""CLI Roundtable blueprint — group-chat debate.

Several CLIs debate in a *shared transcript* across bounded rounds. Each round
every debater sees the others' latest positions, so they react to each other —
unlike ``cli_fusion``, where the panel answers once in isolation and a judge
reconciles. A moderator decides after each round whether the table has converged
(conclude) or should keep going, and produces the final synthesis.

Request model: ``model: "cli_roundtable"``. Config block ``cli_roundtable``:
``{ "debaters": [<cli>...], "moderator": <cli>, "rounds": int }`` (falls back to
a ``cli_fusion`` preset panel + judge). Per-request ``params`` may set
``debaters``, ``moderator``, ``rounds``, ``workdir``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.consensus import safe_json

logger = logging.getLogger(__name__)

DEFAULT_ROUNDS = 2
MAX_ROUNDS = 4
MAX_CONCURRENCY = 8

DEBATER_TEMPLATE = """You are participant "{name}" in a panel debate on this question:
<question>
{question}
</question>

Discussion so far:
{transcript}

Give your position in 2-4 sentences. If you disagree with another participant, say
why specifically. Do not repeat points already settled. Be concise.
"""

MODERATOR_TEMPLATE = """You are the moderator of a panel debate on this question:
<question>
{question}
</question>

The latest round of positions:
{positions}

Decide whether the panel has converged enough to conclude. Return ONLY a JSON object:
{{"done": true or false, "synthesis": "<the best combined answer so far>", "next_prompt": "<if not done, the specific point the panel should resolve next>"}}
"""


class CliRoundtableBlueprint(BlueprintBase):
    """Run a bounded multi-CLI debate moderated to a synthesized conclusion."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_roundtable",
        "title": "CLI Roundtable (group-chat debate)",
        "description": (
            "Several CLIs debate in a shared transcript across bounded rounds, "
            "reacting to each other; a moderator decides when to conclude and "
            "synthesizes the result. Group chat over heterogeneous CLIs."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "group-chat", "debate", "multi-agent", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_roundtable", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[list[str], str | None]:
        """Resolve (debaters, moderator), falling back to a cli_fusion preset."""
        rc = (self._config or {}).get("cli_roundtable") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}
        preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}

        debaters = params.get("debaters") or rc.get("debaters") or preset.get("panel")
        if not debaters:
            # Avoid spawning every configured CLI (chat prove / short turns).
            # Prefer an explicit fusion default, else a single available CLI.
            default_cli = fusion.get("default_cli")
            available = registry.available() or registry.names()
            if default_cli and default_cli in set(registry.names()):
                debaters = [default_cli]
            elif available:
                debaters = [available[0]]
            else:
                debaters = []
        moderator = (
            params.get("moderator")
            or rc.get("moderator")
            or preset.get("judge")
            or fusion.get("default_cli")
        )

        known = set(registry.names())
        debaters = [d for d in (debaters or []) if d in known]
        if moderator and moderator not in known:
            moderator = None
        return debaters, moderator

    def _rounds(self, params: dict[str, Any]) -> int:
        raw = params.get("rounds", ((self._config or {}).get("cli_roundtable") or {}).get("rounds", DEFAULT_ROUNDS))
        try:
            return max(1, min(int(raw), MAX_ROUNDS))
        except (TypeError, ValueError):
            return DEFAULT_ROUNDS

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        question = support.render_prompt(messages)
        if not question:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        debaters, moderator = self._resolve(params, registry)
        if not debaters:
            yield support.message_chunk(
                "No debater CLIs are configured for the roundtable. Add a "
                "'cli_roundtable' block (or a 'cli_fusion' preset) to your swarm "
                "config (see docs/CLI_FUSION.md).",
                final=True,
            )
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return
        rounds = self._rounds(params)
        sem = asyncio.Semaphore(MAX_CONCURRENCY)
        yield support.progress_chunk(
            f"_Roundtable: {len(debaters)} debater(s) over up to {rounds} round(s)…_"
        )

        transcript = "(no prior discussion)"
        last_positions: list[tuple[str, str]] = []
        synthesis: str | None = None

        for round_i in range(rounds):
            yield support.progress_chunk(f"_Round {round_i + 1}/{rounds}: debaters responding…_")

            async def _one(name: str, transcript=transcript):
                adapter = registry.get(name)
                async with sem:
                    res = await adapter.run(
                        DEBATER_TEMPLATE.format(name=name, question=question, transcript=transcript),
                        workdir=workdir,
                    )
                return name, res

            results = await asyncio.gather(*(_one(d) for d in debaters))
            positions = [(name, res.text) for name, res in results if res.ok and res.text.strip()]
            for name, res in results:
                if not (res.ok and res.text.strip()):
                    yield support.progress_chunk(f"_• {name} did not respond ({res.error or 'empty'})._")
            if not positions:
                yield support.progress_chunk("_No debater responded this round._")
                break
            last_positions = positions

            # Grow the shared transcript with this round's positions.
            block = "\n".join(f"[{name}] {text}" for name, text in positions)
            transcript = f"{transcript}\n\n--- Round {round_i + 1} ---\n{block}".lstrip()

            if not moderator:
                continue  # no moderator: keep debating to the round bound, then concatenate

            yield support.progress_chunk(f"_Moderator `{moderator}` reviewing round {round_i + 1}…_")
            mres = await registry.get(moderator).run(
                MODERATOR_TEMPLATE.format(question=question, positions=block), workdir=workdir
            )
            verdict = safe_json(mres.text) if mres.ok else None
            if isinstance(verdict, dict):
                if isinstance(verdict.get("synthesis"), str) and verdict["synthesis"].strip():
                    synthesis = verdict["synthesis"].strip()
                if bool(verdict.get("done")):
                    yield support.progress_chunk(f"_Moderator concluded after round {round_i + 1}._")
                    break
                nxt = verdict.get("next_prompt")
                if isinstance(nxt, str) and nxt.strip():
                    transcript = f"{transcript}\n\n[moderator] Focus next on: {nxt.strip()}"

        debater_names = [name for name, _ in last_positions]
        if synthesis:
            yield support.message_chunk(
                synthesis, final=True, meta=support.backend_meta(debater_names, judge=moderator)
            )
            return
        # No moderator synthesis — return the final round's positions, labeled.
        if last_positions:
            block = "\n\n".join(f"### {name}\n{text}" for name, text in last_positions)
            yield support.message_chunk(block, final=True, meta=support.backend_meta(debater_names))
            return
        yield support.message_chunk("The roundtable produced no positions.", final=True)

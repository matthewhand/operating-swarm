"""Hybrid Swarm blueprint: a REST reasoning step MIXED with CLI agents.

A larger orchestrated blueprint that, in a single ``run()``, routes across both
a REST-style reasoning step *and* a CLI consensus panel. It combines three
composable layers:

  * a REST-style LLM reasoning step (deterministic under ``SWARM_TEST_MODE``),
  * a grok CLI *persona*        (:func:`swarm.core.cli_tools.cli_persona`),
  * a cross-model *consensus*   (:func:`swarm.core.consensus.run_consensus`
                                 via :func:`swarm.core.cli_tools.consensus_fn`).

Determinism in tests has TWO independent switches:
  * REST half -> stubbed when ``os.environ["SWARM_TEST_MODE"]`` is set.
  * CLI half  -> driven by a configured ``cli_agents`` block of fake echo CLIs
                 (see tests/blueprints/test_hybrid_swarm.py), so no model/network.

Request model: ``model: "hybrid_swarm"``. Config block ``hybrid_swarm``:
  ``{ "grok": "<cli-name>", "panel": ["<cli>", ...], "judge": "<cli>" }``
falls back to the ``cli_fusion`` ``default_cli`` / ``default_preset``.
Per-request ``params`` may override grok / panel / judge / workdir.
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import ApiKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.cli_tools import cli_persona, consensus_fn  # granular tool layer
from swarm.core.consensus import run_consensus  # or call this directly

logger = logging.getLogger(__name__)


class HybridSwarmBlueprint(ApiKindBase):
    """REST reasoning + grok persona + consensus panel, in one run()."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "hybrid_swarm",
        "title": "Hybrid Swarm (REST + CLI agents)",
        "description": (
            "A larger orchestrated blueprint that routes across a REST reasoning "
            "step, a grok CLI persona, and a cross-model CLI consensus panel in a "
            "single request."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "fusion", "rest", "consensus", "hybrid", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "hybrid_swarm", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    # --- config resolution: grok persona + consensus panel ---------------- #

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[str | None, list[str], str | None]:
        """Resolve (grok_cli, panel, judge), falling back to cli_fusion config."""
        hc = (self._config or {}).get("hybrid_swarm") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        grok = params.get("grok") or hc.get("grok") or fusion.get("default_cli")
        panel = params.get("panel") or hc.get("panel")
        judge = params.get("judge") or hc.get("judge")
        if not panel:
            preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}
            panel = preset.get("panel")
            judge = judge or preset.get("judge")

        known = set(registry.names())
        # grok defaults to the first available CLI if still unset.
        if not grok:
            avail = registry.available() or registry.names()
            grok = avail[0] if avail else None
        if grok and grok not in known:
            grok = None
        panel = [n for n in (panel or []) if n in known]
        if judge and judge not in known:
            judge = None
        return grok, panel, judge

    # --- the REST step (deterministic under SWARM_TEST_MODE) -------------- #

    async def _rest_reason(self, prompt: str) -> str:
        """A single REST-style LLM reasoning call.

        Under ``SWARM_TEST_MODE`` we return a fixed stub so the REST half is
        deterministic with no network — the same idiom blueprint_gawd /
        blueprint_zeus use. Replace the body with your real OpenAI/Anthropic
        client call in production.
        """
        if os.environ.get("SWARM_TEST_MODE"):
            return f"[rest-plan] {prompt}"
        # Real REST reasoning: one openai-agents Agent (the LLM orchestrator),
        # degrading gracefully so a missing/unreachable LLM never sinks the run.
        try:
            from agents import Runner

            agent = self.make_agent(
                name="Orchestrator",
                instructions=(
                    "You are an orchestrator. In 1-2 sentences, outline how to "
                    "answer the user's request and what to route to sub-agents."
                ),
                tools=[],
            )
            result = await Runner.run(agent, prompt)
            return str(result.final_output)
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash the run
            return f"[rest-plan unavailable: {exc}] {prompt}"

    # --- entry point ------------------------------------------------------ #

    async def run(
        self, messages: list[dict[str, Any]], **kwargs: Any
    ) -> AsyncGenerator[dict[str, Any], None]:
        # Snapshot params before any await (a cached instance may be shared).
        params = dict(self._params)

        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        grok_name, panel_names, judge_name = self._resolve(params, registry)

        # ---- 1. REST reasoning step (the master plan) -------------------- #
        yield support.progress_chunk("_Reasoning (REST step)…_")
        plan = await self._rest_reason(prompt)
        # The REST plan steers the CLI sub-questions below.
        sub_question = f"{prompt}\n\n--- Plan ---\n{plan}"

        # ---- 2. grok CLI persona step ------------------------------------ #
        grok_answer = ""
        if grok_name:
            yield support.progress_chunk(f"_Asking the grok persona (`{grok_name}`)…_")
            ask_grok = cli_persona(registry.get(grok_name))  # async (str) -> str
            grok_answer = await ask_grok(sub_question)
            # cli_persona never raises: failures arrive as "[<name> unavailable: …]".

        # ---- 3. consensus panel step ------------------------------------- #
        consensus_answer = ""
        if panel_names:
            yield support.progress_chunk(
                f"_Escalating to consensus over {', '.join(panel_names)}…_"
            )
            panel = registry.resolve_panel(panel_names)
            judge = registry.get(judge_name) if judge_name else None

            # The granular tool callable collapses the panel -> one answer.
            # (For the full ConsensusResult — analysis, per-panelist rows, ok flag,
            # next_step — call run_consensus(...) directly instead.)
            consensus = consensus_fn(panel, judge)  # async (str) -> str
            consensus_answer = await consensus(sub_question)

        # ---- 4. combine REST + CLI outputs into the final answer --------- #
        from swarm.core.model_text import is_usable_model_text, sanitize_model_text

        plan = sanitize_model_text(plan)
        grok_answer = sanitize_model_text(grok_answer)
        consensus_answer = sanitize_model_text(consensus_answer)
        if not is_usable_model_text(plan):
            plan = ""
        parts: list[str] = []
        if plan:
            parts.append(f"REST plan:\n{plan}")
        if grok_answer:
            parts.append(f"grok persona:\n{grok_answer}")
        if consensus_answer:
            parts.append(f"Consensus:\n{consensus_answer}")
        if not (grok_answer or consensus_answer):
            if registry.names():
                parts.append("(CLI persona produced no text)")
            else:
                parts.append(
                    "(no CLI agents configured — add a 'cli_agents' block; see docs/CLI_FUSION.md)"
                )
        if not parts:
            parts.append(
                "(planner returned no usable text — check the orchestration LLM profile)"
            )

        yield support.message_chunk("\n\n".join(parts), final=True)


# Keep ``run_consensus`` importable from this module for callers that want the
# full ConsensusResult directly (kept here so the alternative path is obvious).
__all__ = ["HybridSwarmBlueprint", "run_consensus"]

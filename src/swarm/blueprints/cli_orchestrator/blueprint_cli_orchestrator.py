"""CLI Orchestrator blueprint — granular consensus.

The prototype of "fusion as a composable primitive". A cheap **router** CLI runs
a single inference and answers directly; when it judges the question high-stakes
(correctness-critical, security/production, contested) it *escalates that one
question* to a cross-model **consensus** check over a panel — instead of fanning
out on every request. Single inference by default, consensus on demand.

Request model: ``model: "cli_orchestrator"``. Config block ``cli_orchestrator``:
``{ "router": <cli>, "panel": [<cli>...], "judge": <cli> }`` (falls back to the
``cli_fusion`` default_cli / default_preset). Per-request ``params`` may override
``router`` / ``panel`` / ``judge`` / ``workdir``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import CliKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.consensus import run_consensus, safe_json

logger = logging.getLogger(__name__)

ROUTER_TEMPLATE = """You are a fast router agent. Answer the user's question directly and concisely.
Then decide whether the question is high-stakes enough to warrant a cross-model
consensus check — i.e. correctness-critical, security- or production-impacting,
genuinely contested, or where being wrong is costly. Routine/low-stakes questions
should NOT escalate.

Return ONLY a JSON object:
{{"answer": "<your direct answer>", "escalate": true_or_false, "reason": "<one short line>"}}

Question:
{prompt}
"""


class CliOrchestratorBlueprint(CliKindBase):
    """Single-inference router that escalates hard questions to consensus."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_orchestrator",
        "title": "CLI Orchestrator (granular consensus)",
        "description": (
            "A cheap router CLI answers directly and escalates only high-stakes "
            "questions to a cross-model consensus panel. Fusion as a granular "
            "tool, not a whole-request mode."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "orchestrator", "consensus", "routing", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_orchestrator", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[str | None, list[str], str | None]:
        """Resolve (router, panel, judge), falling back to cli_fusion config."""
        oc = (self._config or {}).get("cli_orchestrator") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        router = params.get("router") or oc.get("router") or fusion.get("default_cli")
        panel = params.get("panel") or oc.get("panel")
        judge = params.get("judge") or oc.get("judge")
        if not panel:
            preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}
            panel = preset.get("panel")
            judge = judge or preset.get("judge")
        if not router:
            available = registry.available() or registry.names()
            router = available[0] if available else None

        known = set(registry.names())
        panel = [n for n in (panel or []) if n in known]
        if judge and judge not in known:
            judge = None
        if router and router not in known:
            router = None
        return router, panel, judge

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        router, panel_names, judge_name = self._resolve(params, registry)
        if not router:
            yield support.message_chunk(
                "No router CLI is configured. Add a 'cli_orchestrator' block (or a "
                "'cli_fusion.default_cli') to your swarm config (see docs/CLI_FUSION.md).",
                final=True,
            )
            return

        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return

        # 1. Single routing inference.
        yield support.progress_chunk(f"_Routing with `{router}` (single inference)…_")
        rres = await registry.get(router).run(ROUTER_TEMPLATE.format(prompt=prompt), workdir=workdir)
        decision = safe_json(rres.text) if rres.ok else None
        quick = ((decision or {}).get("answer") or "").strip() or (rres.text if rres.ok else "")
        escalate = bool((decision or {}).get("escalate"))
        reason = str((decision or {}).get("reason") or "").strip()

        # 2. Resolve directly unless the router escalated (and a panel exists).
        if rres.ok and not escalate:
            yield support.progress_chunk(f"_Resolved directly — no consensus needed ({reason or 'low-stakes'})._")
            yield support.message_chunk(quick, final=True, meta=support.backend_meta([router]))
            return
        if not panel_names:
            yield support.message_chunk(
                quick or "Router produced no answer and no consensus panel is configured.",
                final=True,
            )
            return

        # 3. Escalate this one question to a consensus panel.
        yield support.progress_chunk(
            f"_Escalating to consensus over {', '.join(panel_names)} "
            f"({reason or 'router flagged high-stakes'})…_"
        )
        panel = registry.resolve_panel(panel_names)
        judge = registry.get(judge_name) if judge_name else None
        cons = await run_consensus(prompt, panel, judge, workdirs=dict.fromkeys(registry.names(), workdir))
        for r in cons.results:
            if not r.ok:
                yield support.progress_chunk(f"_• {r.name} failed: {r.error}_")
        if not cons.ok:
            yield support.message_chunk(quick or "All consensus panelists failed.", final=True)
            return
        yield support.message_chunk(
            cons.answer, final=True, meta=support.backend_meta([r.name for r in cons.ok_results], judge_name)
        )

"""Hybrid team blueprint: a REST reasoning step MIXED with CLI agents.

A small "team" that mixes backends in a single ``run()``:

  * a REST-style LLM reasoning step (the *coordinator*; deterministic under
    ``SWARM_TEST_MODE``),
  * a grok CLI *persona*        (:func:`swarm.core.cli_tools.cli_persona` over a
    :class:`~swarm.core.cli_adapter.CliAdapter`),
  * a cross-model *consensus*   (:func:`swarm.core.cli_tools.consensus_fn` /
    :func:`swarm.core.consensus.run_consensus`).

The REST coordinator holds the master plan and delegates sub-questions to the
grok/claude CLI personas (exposed as ``cli_tools`` callables) and to a consensus
panel — that is the MIX: one REST inference reaching for CLI personas mid-run.

**claude-orchestrated delegation.** When a ``claude`` cli_agent is configured,
the coordinator step uses ``claude -p`` as the *orchestration brain*: it returns
a JSON plan + role delegations,

    {"plan": "...", "delegations": [{"role": "agent", "task": "..."}, ...]}

which :meth:`run` parses (:meth:`_parse_delegations`) and routes back through the
per-step model machinery — each delegation runs on its role's model
(``orchestration`` / ``agent`` / ``auxiliary``; see :attr:`ROLE_PROFILES` and
:meth:`_agent_for_role`). Without claude it falls back to the orchestration-role
LLM plan with no delegations, so the per-step routing from the prior change still
applies and behaviour is unchanged under ``SWARM_TEST_MODE``.

Deterministic in tests two ways, independently:

  * REST half -> stubbed when ``os.environ["SWARM_TEST_MODE"]`` is set.
  * CLI half  -> driven by a configured ``cli_agents`` block of fake echo CLIs
                 (``python -c '... print(...)'``; see
                 ``tests/blueprints/test_hybrid_team.py``), so no model/network.

Request model: ``model: "hybrid_team"``. Config block ``hybrid_team``::

    {"grok": "<cli-name>", "panel": ["<cli>", ...], "judge": "<cli>"}

falls back to the ``cli_fusion`` ``default_cli`` / ``default_preset``. Per-request
``params`` may override ``grok`` / ``panel`` / ``judge`` / ``workdir`` / ``timeout``.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
import re
import threading
import time
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.kind_bases import ApiKindBase, TeamKindBase
from swarm.core.cli_adapter import CliAdapterRegistry
from swarm.core.cli_tools import cli_persona, consensus_fn  # the granular tool layer
from swarm.core.consensus import run_consensus  # noqa: F401  (Option B; see run())

logger = logging.getLogger(__name__)


class HybridTeamBlueprint(TeamKindBase):
    """REST coordinator + grok CLI persona + consensus panel, in one run()."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "hybrid_team",
        "title": "Hybrid Team (REST coordinator + CLI agents)",
        "description": (
            "A REST coordinator that reasons, then delegates to a grok CLI "
            "persona and a cross-model consensus panel — backends mixed in a "
            "single request."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "fusion", "rest", "consensus", "hybrid", "openai-compatible"],
        # Blueprint-level default for any step that does NOT request a specific
        # role (see ROLE_PROFILES). hybrid_team mixes a smart coordinator with
        # cheaper execution steps, so the default leans capable-but-not-maximal:
        # good reasoning, some weight on speed. Per-step roles below override it.
        # A hint only — explicit llm_profile / DEFAULT_LLM / LITELLM_MODEL win.
        "inference_profile": {"intelligence": 0.7, "speed": 0.5},
        "required_mcp_servers": [],
        "env_vars": [],
    }

    # Per-step inference intents. Each maps a sub-task *role* to an
    # inference_profile (see core/inference_profile.py) that BlueprintBase scores
    # against the tagged profiles in swarm_config.json's `llm` section. This is
    # what lets a single run() mix models by step: planning gets the smartest
    # model; cheap/simple steps get a fast, inexpensive one.
    ROLE_PROFILES: ClassVar[dict[str, dict[str, float]]] = {
        # planning, coordination, multi-agent work -> the smartest available
        "orchestration": {"intelligence": 0.95},
        # general coding / reasoning -> capable, with mild cost awareness
        "agent": {"intelligence": 0.7, "cost": 0.4},
        # testing, revision, simple execution -> fast and cheap
        "auxiliary": {"speed": 0.9, "cost": 0.9},
    }

    # The orchestration brain (claude -p, when configured) is asked to emit a
    # structured plan + role delegations as JSON, which run() parses and routes
    # back through _agent_for_role. Plain-text replies degrade to "plan, no
    # delegations" so a non-JSON model never breaks the run.
    _DELEGATION_INSTRUCTIONS: ClassVar[str] = (
        "You are the orchestration brain for a small agent team. Read the user's "
        "request, produce a brief plan, then delegate concrete sub-tasks to roles. "
        "Respond with ONLY a JSON object (no prose, no code fences) of the form: "
        '{"plan": "<1-2 sentence plan>", "delegations": '
        '[{"role": "orchestration|agent|auxiliary", "task": "<what to do>"}]}. '
        "Use 'auxiliary' for cheap/simple/testing/revision steps, 'agent' for "
        "general coding and reasoning, and 'orchestration' for further "
        "planning/coordination. At most 3 delegations; use [] if none are needed."
    )

    # Parallel-delegation tuning. Delegations run concurrently on a small thread
    # pool; launches are staggered to be gentle on free-CLI rate limits, and each
    # delegation has a hard timeout so one slow/hung sub-task can't stall the rest.
    _DELEGATION_MAX_WORKERS: ClassVar[int] = 4
    _DELEGATION_TIMEOUT_S: ClassVar[float] = 120.0
    _DELEGATION_LAUNCH_DELAY_S: ClassVar[float] = 0.25

    def __init__(
        self,
        blueprint_id: str = "hybrid_team",
        config=None,
        config_path=None,
        **kwargs,
    ):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    # --- config resolution: grok persona + consensus panel ---------------- #

    def _resolve(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> tuple[str | None, list[str], str | None]:
        """Resolve (grok_cli, panel, judge), falling back to cli_fusion config."""
        hc = (self._config or {}).get("hybrid_team") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        grok = params.get("grok") or hc.get("grok") or fusion.get("default_cli")
        panel = params.get(support.PARAM_PANEL) or hc.get("panel")
        judge = params.get(support.PARAM_JUDGE) or hc.get("judge")
        if not panel:
            preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}
            panel = preset.get("panel")
            judge = judge or preset.get("judge")

        known = set(registry.names())
        # Prefer grok, then agy — never pick claude just because it sorts first.
        if not grok:
            avail = list(registry.available() or registry.names())
            for preferred in ("grok", "agy"):
                if preferred in known or preferred in avail:
                    grok = preferred
                    break
            if not grok:
                grok = next((n for n in avail if n != "claude"), None)
        if grok and grok not in known:
            grok = None
        panel = [n for n in (panel or []) if n in known]
        if judge and judge not in known:
            judge = None
        return grok, panel, judge

    # --- per-step model routing ------------------------------------------- #

    def _agent_for_role(self, role: str, name: str, instructions: str, tools=None):
        """Create an openai-agents Agent whose model is chosen for a sub-task ``role``.

        Maps ``role`` (e.g. "orchestration", "agent", "auxiliary") to an
        inference_profile via :attr:`ROLE_PROFILES` and lets BlueprintBase score
        it against the configured ``llm`` profiles. An unknown role falls back to
        the blueprint's own metadata ``inference_profile``. The choice is logged
        so it is obvious which model each step used.
        """
        profile = self.ROLE_PROFILES.get(role)
        logger.info("[hybrid_team] step role=%s -> inference_profile=%s", role, profile)
        return self.make_agent(
            name=name,
            instructions=instructions,
            tools=list(tools or []),
            inference_profile=profile,
        )

    # --- claude-orchestrated delegation ----------------------------------- #

    def _claude_persona(self, registry):
        """Claude orchestrator only when ``cli_agents.claude`` is in config.

        A host ``claude`` binary on PATH (catalog merge) must not become the
        planning brain — operator default is LiteLLM + grok.
        """
        configured = ((self._config or {}).get("cli_agents") or {})
        if "claude" not in configured:
            return None
        try:
            if "claude" in set(registry.names()):
                return cli_persona(registry.get("claude"))
        except Exception:  # noqa: BLE001 — never let wiring issues sink the run
            pass
        return None

    @staticmethod
    def _extract_json_object(raw: str) -> dict | None:
        """Best-effort JSON object from a model reply (handles prose / fences)."""
        if not raw:
            return None
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:  # noqa: BLE001
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    obj = json.loads(m.group(0))
                    return obj if isinstance(obj, dict) else None
                except Exception:  # noqa: BLE001
                    return None
        return None

    def _parse_delegations(self, raw: str, fallback: str = "") -> tuple[str, list[dict]]:
        """Parse the brain's reply into ``(plan, delegations)``.

        Accepts ``{"plan": ..., "delegations": [{"role", "task"}]}`` (possibly
        wrapped in prose). Delegations with an empty task or a role outside
        :attr:`ROLE_PROFILES` are dropped. Any non-JSON reply degrades to
        ``(raw or fallback, [])`` — a plain plan with no delegations.
        """
        obj = self._extract_json_object(raw)
        if obj is None:
            return (raw or fallback), []
        plan = str(obj.get("plan") or "").strip() or (raw or fallback)
        delegations: list[dict] = []
        for d in obj.get("delegations") or []:
            if not isinstance(d, dict):
                continue
            role = str(d.get("role") or "").strip().lower()
            task = str(d.get("task") or "").strip()
            if not task:
                continue
            if role in self.ROLE_PROFILES:
                delegations.append({"role": role, "task": task})
            else:
                logger.info("[hybrid_team] dropping delegation with unknown role=%r", d.get("role"))
        return plan, delegations

    async def _orchestrate(self, prompt: str, registry) -> tuple[str, list[dict]]:
        """Run the orchestration brain; return ``(plan, delegations)``.

        Prefers ``claude -p`` (the orchestration brain) when a ``claude``
        cli_agent is configured: it returns structured JSON that we parse into
        role delegations. Without claude, falls back to the orchestration-role
        LLM plan (no delegations). Deterministic stub under ``SWARM_TEST_MODE``.
        Always degrades gracefully — a missing brain never sinks the run.
        """
        if os.environ.get("SWARM_TEST_MODE"):
            return f"[rest-plan] {prompt}", []
        claude = self._claude_persona(registry)
        if claude is None:
            return await self._rest_reason(prompt), []
        try:
            raw = await claude(f"{self._DELEGATION_INSTRUCTIONS}\n\nUser request:\n{prompt}")
        except Exception as exc:  # noqa: BLE001 — degrade to a plain plan
            return f"[orchestration unavailable: {exc}] {prompt}", []
        return self._parse_delegations(raw, fallback=prompt)

    async def _run_delegation(self, deleg: dict) -> str:
        """Execute one delegation on its role's model (per ROLE_PROFILES).

        Deterministic under ``SWARM_TEST_MODE``; degrades to a marker string on
        any failure so one bad sub-task never sinks the run.
        """
        role, task = deleg["role"], deleg["task"]
        if os.environ.get("SWARM_TEST_MODE"):
            return f"[{role}] {task}"
        try:
            from agents import Runner

            agent = self._agent_for_role(
                role,
                name=f"{role.title()}Worker",
                instructions="Complete the delegated sub-task concisely and accurately.",
            )
            result = await Runner.run(agent, task)
            return str(result.final_output)
        except Exception as exc:  # noqa: BLE001
            return f"[{role} unavailable: {exc}] {task}"

    def _role_model(self, role: str) -> str | None:
        """The llm profile name a role would resolve to (for observability), or None."""
        profile = self.ROLE_PROFILES.get(role)
        if not profile:
            return None
        try:
            from swarm.core.inference_profile import resolve
            return resolve(profile, self._llm_candidates())
        except Exception:  # noqa: BLE001
            return None

    async def _execute_delegations(self, delegations: list[dict]) -> AsyncGenerator[dict, None]:
        """Run delegations in parallel on a ThreadPoolExecutor, yielding each result
        dict as it completes (out of order).

        Each result is ``{role, task, status: completed|failed, result|error,
        model_used}``. Failures are isolated (one bad sub-task never kills the
        others), each has a hard ``_DELEGATION_TIMEOUT_S`` ceiling, and launches
        are staggered by ``_DELEGATION_LAUNCH_DELAY_S`` to protect free-CLI rate
        limits. Deterministic under ``SWARM_TEST_MODE`` (``_run_delegation`` stubs).
        """
        launch_gate = threading.Lock()  # serialize *starts* to stagger launches

        def _work(d: dict) -> dict:
            role, task = d["role"], d["task"]
            model_used = self._role_model(role)
            with launch_gate:
                time.sleep(self._DELEGATION_LAUNCH_DELAY_S)
            base = {"role": role, "task": task, "model_used": model_used}
            try:
                # Own event loop per worker thread, with a hard per-task timeout.
                out = asyncio.run(
                    asyncio.wait_for(self._run_delegation(d), timeout=self._DELEGATION_TIMEOUT_S)
                )
                return {**base, "status": "completed", "result": out}
            except (TimeoutError, asyncio.TimeoutError):
                return {**base, "status": "failed", "error": f"timed out after {self._DELEGATION_TIMEOUT_S:.0f}s"}
            except Exception as exc:  # noqa: BLE001 — isolate per-delegation failures
                return {**base, "status": "failed", "error": str(exc)}

        max_workers = min(self._DELEGATION_MAX_WORKERS, max(1, len(delegations)))
        loop = asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [loop.run_in_executor(pool, _work, d) for d in delegations]
            for fut in asyncio.as_completed(futures):
                yield await fut

    # --- the REST step (deterministic under SWARM_TEST_MODE) -------------- #

    async def _rest_reason(self, prompt: str) -> str:
        """The coordinator's master-plan step — an *orchestration* sub-task.

        Under ``SWARM_TEST_MODE`` we return a fixed stub so the REST half is
        deterministic with no network — the same idiom blueprint_gawd /
        blueprint_zeus use. In production it runs an Agent on the smartest
        available model (the "orchestration" role) and degrades gracefully — if
        no LLM is configured/reachable, the CLI half still runs — so a missing
        key never sinks the whole hybrid.
        """
        if os.environ.get("SWARM_TEST_MODE"):
            return f"[rest-plan] {prompt}"
        try:
            from agents import Runner

            agent = self._agent_for_role(
                "orchestration",
                name="Coordinator",
                instructions=(
                    "You are a planning coordinator. In 1-2 sentences, give a brief "
                    "plan for answering the user's request — what to check and which "
                    "sub-questions to delegate."
                ),
            )
            result = await Runner.run(agent, prompt)
            return str(result.final_output)
        except Exception as exc:  # noqa: BLE001 — degrade, don't crash the run
            return f"[rest-plan unavailable: {exc}] {prompt}"

    async def _synthesize(self, parts: list[str], params: dict[str, Any]) -> str:
        """Optionally polish the combined sections into one answer on a *cheap*
        model (the "auxiliary" role) — a simple-execution sub-task.

        Opt-in via ``params['synthesize']`` or the ``hybrid_team`` config block's
        ``synthesize`` flag. Disabled under ``SWARM_TEST_MODE`` and on any
        failure, where it returns the plain concatenation (the default,
        deterministic behaviour). This is what makes routing dynamic *per step*:
        the coordinator plans on an ``orchestration`` model while this final pass
        runs on an ``auxiliary`` one — two models in a single run.
        """
        joined = "\n\n".join(parts)
        hc = (self._config or {}).get("hybrid_team") or {}
        want = bool(params.get("synthesize", hc.get("synthesize", False)))
        if not want or os.environ.get("SWARM_TEST_MODE"):
            return joined
        try:
            from agents import Runner

            agent = self._agent_for_role(
                "auxiliary",
                name="Synthesizer",
                instructions=(
                    "Combine the sections below into one concise, well-formatted "
                    "answer for the user. Preserve the facts; do not invent."
                ),
            )
            result = await Runner.run(agent, joined)
            return str(result.final_output)
        except Exception as exc:  # noqa: BLE001 — degrade to the raw join
            logger.info("[hybrid_team] auxiliary synthesis unavailable: %s", exc)
            return joined

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
        from swarm.core.workdir import WorkdirEscapeError

        try:
            workdir = support.resolve_workdir(params)
        except WorkdirEscapeError as e:
            yield support.message_chunk(str(e), final=True)
            return

        # ---- 1. orchestration: plan + (optional) claude-driven delegations  #
        yield support.progress_chunk("_Coordinator reasoning (REST step)…_")
        plan, delegations = await self._orchestrate(prompt, registry)
        # The plan steers the CLI sub-questions below.
        sub_question = f"{prompt}\n\n--- Plan ---\n{plan}"

        # ---- 1b. execute the brain's delegations IN PARALLEL ------------- #
        # Each {role, task} from claude runs on its role's model
        # (orchestration/agent/auxiliary) via _agent_for_role, concurrently on a
        # small thread pool. Results arrive out of order; each is surfaced as a
        # `delegation_progress` chunk (also captured into the persisted Responses
        # progress array). Empty under SWARM_TEST_MODE / when no claude brain.
        delegated: list[tuple[str, str]] = []
        if delegations:
            yield support.progress_chunk(
                f"_Delegating {len(delegations)} sub-task(s) in parallel…_"
            )
            async for ev in self._execute_delegations(delegations):
                summary = ev["result"] if ev["status"] == "completed" else (
                    f"[{ev['role']} {ev['status']}: {ev.get('error')}]"
                )
                delegated.append((ev["role"], summary))
                yield {
                    "type": "delegation_progress",
                    "content": (
                        f"_• {ev['role']} {ev['status']}"
                        + (f" on `{ev['model_used']}`" if ev.get("model_used") else "")
                        + "_"
                    ),
                    "delegation": ev,
                }

        # ---- 2. grok CLI persona step ------------------------------------ #
        grok_answer = ""
        if grok_name:
            yield support.progress_chunk(f"_Delegating to the grok persona (`{grok_name}`)…_")
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

            if workdir:
                # Full ConsensusResult path: surface per-panelist failures, honour workdir.
                cons = await run_consensus(
                    sub_question, panel, judge,
                    workdirs=dict.fromkeys(registry.names(), workdir),
                )
                for r in cons.results:
                    if not r.ok:
                        yield support.progress_chunk(f"_• {r.name} failed: {r.error}_")
                consensus_answer = cons.answer or "(no consensus reached)"
            else:
                # Granular tool callable: collapse the panel -> one answer.
                consensus = consensus_fn(panel, judge)  # async (str) -> str
                consensus_answer = await consensus(sub_question)

        # ---- 4. combine REST + delegated + CLI outputs into the answer --- #
        from swarm.core.model_text import is_usable_model_text, sanitize_model_text

        plan = sanitize_model_text(plan)
        grok_answer = sanitize_model_text(grok_answer)
        consensus_answer = sanitize_model_text(consensus_answer)
        if not is_usable_model_text(plan) or "claude unavailable" in plan.lower():
            plan = ""
        parts: list[str] = []
        if plan:
            parts.append(f"REST plan:\n{plan}")
        for role, out in delegated:
            cleaned = sanitize_model_text(out)
            if is_usable_model_text(cleaned):
                parts.append(f"Delegated [{role}]:\n{cleaned}")
        if grok_answer:
            parts.append(f"grok persona:\n{grok_answer}")
        if consensus_answer:
            parts.append(f"Consensus:\n{consensus_answer}")
        if not (grok_answer or consensus_answer or delegated):
            if registry.names():
                parts.append("(CLI persona produced no text)")
            else:
                parts.append(support.UNCONFIGURED_CLI_AGENTS_MESSAGE)
        if not parts:
            parts.append(
                "(planner returned no usable text — check the orchestration LLM profile)"
            )

        # Optional cheap "auxiliary" synthesis pass (off by default / in tests):
        # demonstrates per-step routing — planning ran on 'orchestration', this
        # final polish runs on 'auxiliary'.
        final = await self._synthesize(parts, params)
        yield support.message_chunk(final, final=True)

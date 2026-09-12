"""CLI Pipeline blueprint — sequential refinement.

The sequential complement to ``cli_fusion``. Where fusion sends the *same*
prompt to a panel **in parallel** and finds consensus, pipeline chains CLIs **in
order**: each stage refines the previous stage's output. Different backends play
to their strengths in sequence — a fast model drafts, a strong model reviews, a
third polishes.

Request model: ``model: "cli_pipeline"``. Config block ``cli_pipeline``:
``{ "stages": [<cli> | {"cli": <cli>, "instruction": <str>}, ...] }`` (falls back
to a ``cli_fusion`` preset panel). Per-request ``params`` may set ``stages``
(same shape) and ``workdir``.

Each stage after the first sees the running output, not just the original
prompt. A failed stage is skipped — the last good output carries forward — so a
single flaky backend degrades the pipeline rather than breaking it.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.cli_adapter import CliAdapterRegistry

logger = logging.getLogger(__name__)

MAX_STAGES = 8

DEFAULT_INSTRUCTION = (
    "Improve the draft below: fix errors, fill gaps, and tighten it. Return only "
    "the improved version, not a commentary."
)

REFINE_TEMPLATE = """The original task was:
<task>
{prompt}
</task>

The current draft (produced by an earlier stage) is:
<draft>
{draft}
</draft>

{instruction}
"""


class CliPipelineBlueprint(BlueprintBase):
    """Run a prompt through an ordered chain of CLIs, each refining the last."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "cli_pipeline",
        "title": "CLI Pipeline (sequential refinement)",
        "description": (
            "Chain CLIs in order: each stage refines the previous stage's output "
            "(draft then review then polish). The sequential complement to "
            "cli_fusion's parallel panel."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["cli", "sequential", "pipeline", "multi-agent", "openai-compatible"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "cli_pipeline", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _resolve_stages(
        self, params: dict[str, Any], registry: CliAdapterRegistry
    ) -> list[tuple[str, str | None]]:
        """Resolve the ordered stage list into (cli_name, instruction) pairs.

        A stage may be a bare cli name or ``{"cli": name, "instruction": str}``.
        Unknown CLIs are dropped. Falls back to a ``cli_fusion`` preset panel.
        """
        pc = (self._config or {}).get("cli_pipeline") or {}
        fusion = (self._config or {}).get("cli_fusion") or {}

        raw = params.get("stages") or pc.get("stages")
        if not raw:
            preset = (fusion.get("presets") or {}).get(fusion.get("default_preset")) or {}
            # Prefer an explicit panel / default_cli over "every CLI in series"
            # (which routinely exceeds chat prove budgets on multi-CLI hosts).
            default_cli = fusion.get("default_cli")
            available = registry.available() or registry.names()
            if preset.get("panel"):
                raw = preset.get("panel")
            elif default_cli and default_cli in set(registry.names()):
                raw = [default_cli]
            elif available:
                raw = [available[0]]
            else:
                raw = []

        known = set(registry.names())
        stages: list[tuple[str, str | None]] = []
        for item in raw or []:
            if isinstance(item, dict):
                name = item.get("cli") or item.get("name")
                instruction = item.get("instruction") or item.get("role")
            else:
                name, instruction = item, None
            if name and name in known:
                stages.append((str(name), instruction))
        return stages[:MAX_STAGES]

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        params = dict(self._params)

        prompt = support.render_prompt(messages)
        if not prompt:
            yield support.message_chunk("No prompt provided.", final=True)
            return

        registry = support.apply_overrides(support.build_registry(self._config), params)
        stages = self._resolve_stages(params, registry)
        if not stages:
            yield support.message_chunk(
                "No pipeline stages are configured. Add a 'cli_pipeline' block (or a "
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
        names = ", ".join(n for n, _ in stages)
        yield support.progress_chunk(f"_Pipeline of {len(stages)} stage(s): {names}…_")

        draft: str | None = None
        contributed: list[str] = []  # stages that actually shaped the output
        for i, (name, instruction) in enumerate(stages):
            adapter = registry.get(name)
            if draft is None:
                # First stage works the raw task (optionally with its instruction).
                stage_prompt = f"{instruction}\n\n{prompt}" if instruction else prompt
                label = f"stage {i + 1}/{len(stages)} `{name}` (draft)"
            else:
                stage_prompt = REFINE_TEMPLATE.format(
                    prompt=prompt, draft=draft, instruction=instruction or DEFAULT_INSTRUCTION
                )
                label = f"stage {i + 1}/{len(stages)} `{name}` (refine)"
            yield support.progress_chunk(f"_Running {label}…_")

            res = await adapter.run(stage_prompt, workdir=workdir)
            if res.ok and res.text.strip():
                draft = res.text
                contributed.append(name)
            else:
                # Skip a failed stage; the last good draft carries forward.
                yield support.progress_chunk(
                    f"_• {name} failed ({res.error or 'empty output'}); carrying prior draft forward._"
                )

        if draft is None:
            yield support.message_chunk("Every pipeline stage failed.", final=True)
            return
        yield support.message_chunk(draft, final=True, meta=support.backend_meta(contributed))

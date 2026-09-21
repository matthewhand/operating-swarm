"""Hybrid MoA blueprint — workflow B coordinator consults MoA (A) then acts.

Model id: ``hybrid_moa``.

Flow:
1. ``consult_moa`` (read-only panel → orchestrator determination, no act)
2. Return determination; optional workspace write of decision.md when workdir set
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, ClassVar

from swarm.core.kind_bases import TeamKindBase
from swarm.core.moa.config import resolve_moa_preset
from swarm.core.persona_swarm import run_hybrid_scripted

logger = logging.getLogger(__name__)


class HybridMoABlueprint(TeamKindBase):
    """Persona implementer applies MoA consensus (champagne A←B)."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "hybrid_moa",
        "title": "Hybrid MoA (consult panel, then write decision)",
        "description": (
            "Coordinator runs Mixture of Agents (read-only participants) then "
            "the implementer persona writes decision.md. Grok-backed panel by "
            "default when configured; fake for CI."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["moa", "hybrid", "persona", "consensus", "readonly-panel"],
        "aliases": ["moa_hybrid", "hybrid-consensus"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "hybrid_moa", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _moa_settings(self) -> dict[str, Any]:
        moa_cfg = dict((self._config or {}).get("moa") or {})
        preset = self._params.get("preset")
        if preset:
            try:
                moa_cfg = resolve_moa_preset(moa_cfg, str(preset))
            except KeyError as e:
                logger.warning("%s", e)
        # Per-request overrides
        for key in ("backend", "participants", "permission", "fake_responses", "timeout"):
            if key in self._params:
                moa_cfg[key] = self._params[key]
        return moa_cfg

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        parts = []
        for m in messages or []:
            if isinstance(m, dict) and m.get("content"):
                role = (m.get("role") or "user").upper()
                parts.append(f"{role}: {m['content']}")
        question = "\n\n".join(parts).strip()
        if not question:
            yield {
                "messages": [{"role": "assistant", "content": "No prompt provided."}],
                "final": True,
            }
            return

        if os.environ.get("SWARM_TEST_MODE"):
            content = f"[hybrid-moa test-mode] {question}"
            yield {
                "messages": [{"role": "assistant", "content": content}],
                "role": "assistant",
                "content": content,
                "final": True,
                "meta": {"hybrid_moa": True, "test_mode": True},
            }
            return

        settings = self._moa_settings()
        backend = str(settings.get("backend") or "fake")
        participants = settings.get("participants") or ["analyst", "critic"]
        if isinstance(participants, str):
            participants = [p.strip() for p in participants.split(",") if p.strip()]
        fake = settings.get("fake_responses")
        from swarm.core.workdir import (
            WorkdirEscapeError,
            cleanup_run_workdir,
            is_auto_workdir_request,
            resolve_confined_workdir,
        )

        raw_workdir = self._params.get("workdir") or self._params.get("cwd")
        auto_workdir = is_auto_workdir_request(raw_workdir)
        try:
            workdir = str(resolve_confined_workdir(raw_workdir, create=True))
        except WorkdirEscapeError as e:
            yield {
                "messages": [{"role": "assistant", "content": str(e)}],
                "final": True,
            }
            return
        try:
            seed = {}
            notes_path = Path(workdir) / "notes.txt"
            if notes_path.is_file():
                seed = None  # use existing workspace
            else:
                seed = {"notes.txt": question[:2000]}

            result = await run_hybrid_scripted(
                workdir,
                question,
                seed_files=seed,
                moa_backend=backend,
                moa_participants=list(participants),
                moa_fake_responses=dict(fake) if isinstance(fake, dict) else None,
            )
            content = result.final or (result.steps[0].output if result.steps else "")
            meta = {
                "hybrid_moa": True,
                "moa": True,
                "backends": list(participants),
                "writes": list(result.writes),
                "steps": [s.persona for s in result.steps],
            }
            yield {
                "messages": [{"role": "assistant", "content": content}],
                "role": "assistant",
                "content": content,
                "final": True,
                "meta": meta,
            }
        finally:
            if auto_workdir:
                cleanup_run_workdir(workdir)

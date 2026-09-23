"""MoA orchestrator blueprint — scripted consensus then specialists.

Model id: ``moa_orchestrator``.

1. Collect read-only MoA consensus (``consult_moa``, always no-act).
2. Task purpose-specific R/W specialists (implementer, tester, docs, researcher)
   via the **scripted** team runner (not a live openai-agents Runner).

``params.tasks`` formats (via :func:`swarm.core.moa.team.parse_team_tasks`)::

    # pipe-separated string
    "implementer:apply|tester:verify@qa/notes.md|docs:adr@docs/ADR.md"

    # list of dicts (API-friendly)
    [{"purpose": "implementer", "instruction": "apply", "output_path": "out.md"}]
"""

from __future__ import annotations

import logging
import os
from typing import Any, ClassVar

from swarm.core.kind_bases import TeamKindBase
from swarm.core.moa.agents_orchestrator import run_moa_agents_orchestrator
from swarm.core.moa.config import resolve_moa_preset
from swarm.core.moa.team import (
    SPECIALIST_PURPOSES,
    SpecialistTask,
    parse_team_tasks,
)

logger = logging.getLogger(__name__)


class MoAOrchestratorBlueprint(TeamKindBase):
    """MoA panel then scripted R/W specialists (not a live Runner)."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "moa_orchestrator",
        "title": "MoA Orchestrator (consensus then specialists)",
        "description": (
            "Collects read-only MoA consensus (Grok/fake/acpx), then runs "
            "scripted purpose specialists (implementer, tester, docs, researcher) "
            "via WorkspaceTools. Panelists never write. Default path does not "
            "start a live openai-agents Runner."
        ),
        "version": "0.1.0",
        "author": "Open Swarm Team",
        "tags": ["moa", "orchestrator", "specialists", "hybrid", "scripted"],
        "aliases": ["moa-orch", "agents_moa"],
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(
        self,
        blueprint_id: str = "moa_orchestrator",
        config=None,
        config_path=None,
        **kwargs,
    ):
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
        for key in ("backend", "participants", "permission", "fake_responses", "timeout"):
            if key in self._params:
                moa_cfg[key] = self._params[key]
        # SWARM_TEST_MODE: force fake backend so API smoke / CI never hit network.
        if os.environ.get("SWARM_TEST_MODE") and "backend" not in self._params:
            moa_cfg["backend"] = "fake"
        return moa_cfg

    def _parse_tasks(self) -> list[SpecialistTask] | None:
        """Delegate to shared ``parse_team_tasks`` (supports @output paths).

        Accepts ``params.tasks`` or alias ``params.team_tasks`` (CLI naming).
        """
        raw = self._params.get("tasks")
        if raw is None or raw == "":
            raw = self._params.get("team_tasks")
        return parse_team_tasks(raw)

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
                "role": "assistant",
                "content": "No prompt provided.",
                "final": True,
            }
            return

        settings = self._moa_settings()
        backend = str(settings.get("backend") or "fake")
        participants = settings.get("participants") or ["analyst", "critic"]
        if isinstance(participants, str):
            participants = [p.strip() for p in participants.split(",") if p.strip()]
        if not participants:
            participants = ["analyst", "critic"]
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
            msg = str(e)
            yield {
                "messages": [{"role": "assistant", "content": msg}],
                "role": "assistant",
                "content": msg,
                "final": True,
            }
            return
        try:
            tasks = self._parse_tasks()

            result = await run_moa_agents_orchestrator(
                workdir,
                question,
                specialist_tasks=tasks,
                seed_files={"notes.txt": question[:2000]},
                moa_backend=backend,
                moa_participants=list(participants),
                moa_fake_responses=dict(fake) if isinstance(fake, dict) else None,
            )

            # Human-readable summary of the full orchestration
            lines = [
                "# MoA Agents Orchestrator",
                "",
                "## Consensus (read-only panel)",
                result.determination or "(empty)",
                "",
                "## Specialist tasks",
            ]
            for s in result.specialist_results:
                status = "ok" if s.ok else "FAIL"
                lines.append(f"### {s.persona} [{status}]")
                lines.append(s.output[:2000] if s.output else "(no output)")
                lines.append("")
            content = "\n".join(lines)
            meta = {
                "moa_orchestrator": True,
                "moa": True,
                "backends": list(participants),
                "specialists": [s.persona for s in result.specialist_results],
                "writes": list(result.writes),
                "specialist_purposes": sorted(SPECIALIST_PURPOSES),
                "specialists_ok": all(s.ok for s in result.specialist_results)
                if result.specialist_results
                else True,
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

"""Mixture of Agents blueprint — read-only CLI consensus via MoA orchestrator.

Primary model id: ``moa`` / ``mixture_of_agents``.
Legacy aliases: ``cli_fusion``, ``cli_ensemble`` (same blueprint class; read-only MoA only).
"""

from __future__ import annotations

import logging
import os
import shutil
from typing import Any, ClassVar

from swarm.blueprints.common import unavailable_seat as unavailable
from swarm.core.blueprint_base import BlueprintBase
from swarm.core.moa import MoAOrchestrator, PermissionMode
from swarm.core.moa.backends import FakeParticipantBackend
from swarm.core.moa.cli import build_backend

logger = logging.getLogger(__name__)

# Legacy product names that resolve to MoA (read-only), not multi-writer fusion.
LEGACY_ALIASES = frozenset({"cli_fusion", "cli_ensemble", "fusion", "ensemble"})


class MoABlueprint(BlueprintBase):
    """Expose Mixture of Agents over the blueprint runner."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "moa",
        "title": "Mixture of Agents (read-only CLI consensus)",
        "description": (
            "Fan a question to N read-only participants (fake for CI, grok for live "
            "consensus, optional acpx for multi-vendor). Orchestrator determines "
            "consensus and alone may act/write. Codex is not required. "
            "Legacy aliases: cli_fusion, cli_ensemble."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["moa", "mixture-of-agents", "consensus", "readonly", "cli", "grok"],
        # Discoverable as model ids on /v1/models and /v1/chat/completions
        "aliases": sorted(LEGACY_ALIASES | {"mixture_of_agents"}),
        "required_mcp_servers": [],
        "env_vars": [],
    }

    def __init__(self, blueprint_id: str = "moa", config=None, config_path=None, **kwargs):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}
        #: True when :meth:`_backend` fell back to placeholder opinions because
        #: no live MoA backend was configured. Set by :meth:`_backend`, read by
        #: :meth:`run`. Those opinions report ``ok=True``, so without this the
        #: orchestrator synthesizes a consensus out of "needs grok on PATH".
        self._stubbed_panel = False

    def set_params(self, params: dict[str, Any] | None) -> None:
        self._params = dict(params or {})

    def _participants(self) -> list[str]:
        params = self._params
        moa_cfg = (self._config or {}).get("moa") or {}
        raw = params.get("participants") or moa_cfg.get("participants") or []
        if isinstance(raw, str):
            return [p.strip() for p in raw.split(",") if p.strip()]
        names = [str(p) for p in raw]
        if names:
            return names
        # Defaults: multi-seat labels for fake; single grok seat for live grok.
        kind = self._resolved_kind()
        if kind == "grok":
            return ["grok"]
        return ["analyst", "critic"]

    def _resolved_kind(self, *, testing: bool | None = None) -> str:
        """Operator UI defaults to grok when installed; CI stays fake."""
        params = self._params
        moa_cfg = (self._config or {}).get("moa") or {}
        explicit = params.get("backend") or moa_cfg.get("backend")
        if explicit:
            return str(explicit).lower()
        if testing is None:
            testing = bool(
                os.environ.get("PYTEST_CURRENT_TEST")
                or os.environ.get("SWARM_TEST_MODE")
            )
        if testing:
            return "fake"
        if shutil.which("grok"):
            return "grok"
        return "fake"

    def _backend(self):
        """Resolve participant backend: fake (params/tests) | grok | acpx.

        Live first-class path is grok. Codex is not required.
        """
        params = self._params
        moa_cfg = (self._config or {}).get("moa") or {}
        timeout = float(
            params.get("timeout")
            or moa_cfg.get("default_timeout")
            or 60
        )
        if params.get("fake_responses"):
            # The caller wrote the opinions, so the panel is theirs, not a
            # simulation this seat invented. Nothing to label.
            self._stubbed_panel = False
            return FakeParticipantBackend(dict(params["fake_responses"]))
        kind = self._resolved_kind()
        if kind == "fake":
            seats = self._participants()
            # Every opinion below is a placeholder string this seat generated.
            # Two outcomes, both labelled:
            #   - tests / the smoke matrix want determinism: run it, and say so;
            #   - a live host with no reachable backend: refuse outright, because
            #     the orchestrator cannot tell these from real opinions and
            #     synthesizes a confident consensus out of them.
            self._stubbed_panel = True
            if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("SWARM_TEST_MODE"):
                stubs = {
                    n: f"(stub opinion from {n} — set params.fake_responses or backend=grok)"
                    for n in seats
                }
                return FakeParticipantBackend(stubs)
            stubs = {
                n: (
                    f"{n}: MoA live consensus needs grok on PATH "
                    "(or set moa.backend=grok in swarm_config)."
                )
                for n in seats
            }
            return FakeParticipantBackend(stubs)
        self._stubbed_panel = False
        return build_backend(backend=kind, timeout=timeout)

    def _permission(self) -> str:
        moa_cfg = (self._config or {}).get("moa") or {}
        raw = self._params.get("permission") or moa_cfg.get("permission") or "approve-reads"
        if raw in (PermissionMode.APPROVE_ALL.value, "approve-all", "write"):
            # Hard clamp: MoA participants never get write approval.
            logger.warning("MoA clamped participant permission %r → approve-reads", raw)
            return PermissionMode.APPROVE_READS.value
        return str(raw)

    async def run(self, messages: list[dict[str, Any]], **kwargs) -> Any:
        question_parts = []
        for m in messages or []:
            if isinstance(m, dict) and m.get("content"):
                role = (m.get("role") or "user").upper()
                question_parts.append(f"{role}: {m['content']}")
        question = "\n\n".join(question_parts).strip()
        if not question:
            yield {"role": "assistant", "content": "No prompt provided.", "final": True}
            return

        participants = self._participants()
        if not participants:
            yield {
                "role": "assistant",
                "content": (
                    "No MoA participants configured. Set params.participants or "
                    "moa.participants (e.g. [\"grok\"] or [\"analyst\",\"critic\"])."
                ),
                "final": True,
            }
            return

        backend = self._backend()
        hermetic = bool(
            os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("SWARM_TEST_MODE")
        )
        if self._stubbed_panel and not hermetic:
            # No live panel was reachable. Say so before spending a turn on it —
            # the stub opinions would otherwise synthesize into a confident
            # "— synthesized by orchestrator from N participants".
            yield unavailable.cannot_answer_chunk(
                self.blueprint_id or "moa",
                why=(
                    "no live MoA backend is available — the configured "
                    f"participants ({', '.join(participants)}) are placeholder "
                    "opinions, not model output"
                ),
                remedy=(
                    "install and authenticate the CLI the panel names (grok is "
                    "the live path) and set `moa.backend`, or pass "
                    "`params.fake_responses` to script a deterministic panel "
                    "deliberately"
                ),
                backends=participants,
            )
            return
        orch = MoAOrchestrator(
            backend=backend,
            participant_permission=self._permission(),
        )
        from swarm.core.workdir import (
            WorkdirEscapeError,
            cleanup_run_workdir,
            is_auto_workdir_request,
            resolve_confined_workdir,
        )

        raw_cwd = self._params.get("workdir") or self._params.get("cwd")
        auto_cwd = is_auto_workdir_request(raw_cwd)
        try:
            cwd = str(resolve_confined_workdir(raw_cwd, create=True))
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
            # Determination always orchestrator-side (default synthesizer or inject later).
            result = await orch.run(
                question,
                participants,
                cwd=cwd,
                act=bool(self._params.get("act")),
                action=self._params.get("action"),
            )
            det = result.determination
            from swarm.core.model_text import sanitize_model_text

            ok_names = [o.name for o in result.ok_opinions]
            # A panel that returned nothing produces the orchestrator's
            # "No usable participant opinions." — a *synthesizer* sentence, not
            # an answer, and with no indication that N participants were consulted
            # and all of them failed (out of credit, not installed, timed out).
            # The sweep read that as a 3.9s reply from a working seat. When no
            # participant spoke, say so and name the per-seat failure instead.
            if not ok_names:
                yield unavailable.cannot_answer_chunk(
                    self.blueprint_id or "moa",
                    why=(
                        f"none of the {len(result.opinions)} MoA participants "
                        f"({', '.join(o.name for o in result.opinions) or 'none'}) "
                        f"returned an opinion"
                    ),
                    remedy=(
                        "check the participants can run: install/auth the CLI "
                        "they name (grok for the live panel), or set "
                        "`moa.backend` / `params.participants` in "
                        "swarm_config.json. Set `params.fake_responses` for a "
                        "deterministic offline panel."
                    ),
                    detail=unavailable.participant_failures(result.opinions),
                    backends=[o.name for o in result.opinions],
                )
                return

            answer = sanitize_model_text(det.answer if det else "No determination.")
            meta = {
                "moa": True,
                # system_fingerprint uses backends=… (orchestrator-owned panel that answered)
                "backends": ok_names,
                "participants": [o.name for o in result.opinions],
                "ok_participants": ok_names,
                "act": bool(result.act_result),
            }
            if self._stubbed_panel:
                # The panel is the deterministic one. Say so above the
                # determination rather than letting a synthesized
                # "— synthesized by orchestrator from N participants" stand in
                # for a real consensus.
                answer = "\n\n".join(
                    [
                        unavailable.simulated_panel_notice(
                            seats=participants, explicit=False
                        ),
                        answer,
                    ]
                )
                meta["simulated_panel"] = True
                meta["backend"] = "fake"
                unavailable.mark_unusable(
                    self.blueprint_id or "moa",
                    "ran the deterministic MoA panel; no live participants",
                )
            message = {"role": "assistant", "content": answer}
            # ChatCompletionsView accepts {messages: [...]} final shape + meta side-channel.
            yield {
                "messages": [message],
                "role": "assistant",
                "content": answer,
                "final": True,
                "meta": meta,
                "opinions": [
                    {"name": o.name, "ok": o.ok, "text": o.text, "error": o.error}
                    for o in result.opinions
                ],
            }
        finally:
            if auto_cwd:
                cleanup_run_workdir(cwd)


# Legacy model ids are registered via metadata["aliases"] only (no class aliases —
# those confused discovery with multi-subclass warnings).

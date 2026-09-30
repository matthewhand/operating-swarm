"""ocr_reviewer — CLI seat that runs Alibaba Open Code Review (#1363).

Kind ``cli``. Default role ``skeptic`` (pass / request changes). The same
seat can be retagged ``gate``; every review already prints both a skeptic
verdict and a gate classification (safe / hold).

The turn runs ``ocr review --format json`` in the chat workdir. ``ocr``
keeps its own model endpoint. This seat does not send an Alibaba credential
and does not register an MCP server — upstream MCP transport and tool names
are not verified.
"""

from __future__ import annotations

from typing import Any, ClassVar

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core.cli_adapter import CliAdapter, CliResult
from swarm.core.kind_bases import CliKindBase
from swarm.core.ocr_review import (
    OCR_MISSING_MESSAGE,
    ocr_resume_rejected,
    resume_allowed,
)
from swarm.core.workdir import WorkdirEscapeError


class OcrReviewerBlueprint(CliKindBase):
    """Run ``ocr review --format json`` and report skeptic + gate verdicts."""

    metadata: ClassVar[dict[str, Any]] = {
        "name": "ocr_reviewer",
        "title": "Open Code Review",
        "description": (
            "CLI reviewer seat for Alibaba Open Code Review. Runs "
            "`ocr review --format json` and reports a skeptic verdict "
            "(pass / request changes) and a gate classification (safe / hold). "
            "Uses the endpoint configured in `ocr` itself — no hosted Alibaba "
            "account. Retag the seat as gate to classify pending changes."
        ),
        "version": "0.1.0",
        "author": "Operating Swarm Team",
        "tags": ["cli", "review", "skeptic", "gate", "ocr"],
        "role": "skeptic",
        "rail": True,
        "required_mcp_servers": [],
        "env_vars": [],
    }

    DEFAULT_CLI_ID: ClassVar[str] = "ocr"

    def __init__(
        self,
        blueprint_id: str = "ocr_reviewer",
        config=None,
        config_path=None,
        **kwargs,
    ):
        super().__init__(blueprint_id, config=config, config_path=config_path, **kwargs)
        self._params: dict[str, Any] = {}

    def set_params(self, params: dict[str, Any] | None) -> None:
        """Capture per-request params forwarded by the chat consumer."""
        self._params = dict(params or {})

    def _turn_params(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        params = dict(self._params)
        extra = kwargs.get("params")
        if isinstance(extra, dict):
            params.update(extra)
        return params

    def _instruction(self, messages: list[dict[str, Any]]) -> str:
        for message in reversed(messages or []):
            if (message.get("role") or "user") == "user" and message.get("content"):
                return str(message["content"]).strip()
        if messages:
            return str(messages[-1].get("content") or "").strip()
        return ""

    def _adapter(self, params: dict[str, Any]) -> CliAdapter:
        from swarm.core.cli_catalog import apply_model, catalog_entry
        from swarm.core.model_namespace import model_valid_for_provider

        entry = catalog_entry("ocr") or {
            "cmd": ["ocr", "review", "--format", "json"],
            "parse": "ocr",
            "prompt_mode": "none",
            "mode": "readonly",
            "timeout": 600,
        }
        model = str(params.get("model") or params.get("cli_model") or "").strip()
        config = self._config if isinstance(self._config, dict) else None
        if model and model_valid_for_provider("cli", "ocr", model, config):
            entry = apply_model(entry, "ocr", model)
        return CliAdapter.from_config("ocr", entry)

    def _resume_session(self, params: dict[str, Any], prompt: str) -> str | None:
        """Return a session id only for a range, commit, or scan turn.

        Workspace review rejects ``--resume`` before the model runs, so an
        explicit ``cli_session_id`` is ignored on those turns too. A stored
        thread id is used only for a mode upstream will continue.
        """
        if not resume_allowed(prompt):
            return None
        explicit = str(params.get("cli_session_id") or "").strip()
        if explicit:
            return explicit
        from swarm.core.cli_sessions import get_cli_session, resolve_thread

        ref = resolve_thread(params, default_agent=self.blueprint_id)
        if ref is None:
            return None
        return get_cli_session(
            ref[0],
            ref[1],
            "ocr",
            conversation_id=str(params.get("conversation_id") or ""),
        )

    def _remember_session(self, params: dict[str, Any], session_id: str | None) -> None:
        from swarm.core.cli_sessions import put_cli_session, resolve_thread

        ref = resolve_thread(params, default_agent=self.blueprint_id)
        if ref is None:
            return
        put_cli_session(
            ref[0],
            ref[1],
            "ocr",
            session_id,
            conversation_id=str(params.get("conversation_id") or ""),
        )

    async def _invoke(
        self,
        adapter: CliAdapter,
        prompt: str,
        workdir: str | None,
        session_id: str | None,
    ) -> CliResult:
        return await adapter.run(prompt, workdir=workdir, session_id=session_id)

    async def run(self, messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        params = self._turn_params(kwargs)
        prompt = self._instruction(messages)
        try:
            workdir = support.resolve_workdir(params, required=False)
        except WorkdirEscapeError as exc:
            yield support.message_chunk(str(exc), final=True)
            return

        adapter = self._adapter(params)
        if not adapter.is_available():
            yield support.message_chunk(
                OCR_MISSING_MESSAGE,
                final=True,
                meta=support.fatal_config_meta(support.backend_meta(["ocr"])),
            )
            return

        session_id = self._resume_session(params, prompt)
        result = await self._invoke(adapter, prompt, workdir, session_id)
        if session_id and not result.ok:
            from swarm.core.cli_sessions import is_resume_failure

            refusal = f"{result.error or ''} {getattr(result, 'stderr', '') or ''}"
            if is_resume_failure(result) or ocr_resume_rejected(refusal):
                self._remember_session(params, None)
                result = await self._invoke(adapter, prompt, workdir, None)
                session_id = None
        if result.ok and result.session_id and resume_allowed(prompt):
            self._remember_session(params, result.session_id)

        if getattr(result, "terminated", False):
            yield support.terminated_notice_chunk()
            return

        if not result.ok and not (result.text or "").strip():
            error = result.error or ""
            if _missing_ocr_binary(error, workdir):
                text = OCR_MISSING_MESSAGE
                meta = support.fatal_config_meta(support.backend_meta(["ocr"]))
            else:
                text = error or "Open Code Review failed."
                meta = self._failure_meta(text)
            yield support.message_chunk(text, final=True, meta=meta)
            return

        body = (result.text or "").strip() or (
            result.error or "Open Code Review failed."
        )
        if result.error and result.error not in body:
            body = f"{body}\n\n{result.error}"
        meta = support.backend_meta(["ocr"])
        if not result.ok:
            meta = self._failure_meta(result.error or body, meta)
        yield support.message_chunk(body, final=True, meta=meta)

    def _failure_meta(
        self, text: str, meta: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Fatal-config only for a broken install or a dead resume.

        A timeout or a non-zero review stays in the transcript. Stamping
        every failure as fatal config drops it from history.
        """
        from swarm.core.cli_session_error import is_fatal_config_error
        from swarm.core.cli_sessions import is_resume_failure_text

        base = dict(meta or support.backend_meta(["ocr"]))
        if is_fatal_config_error(text) or is_resume_failure_text(text):
            return support.fatal_config_meta(base)
        return base


def _launch_path_key(value: str) -> str:
    """Compare launch paths without trailing slashes or slash direction."""
    return value.replace("\\", "/").rstrip("/").lower()


def _quoted_enoent_path(lowered: str) -> str | None:
    """Path inside ``No such file or directory: '...'`` / ``"..."``."""
    for quote in ("'", '"'):
        marker = f"no such file or directory: {quote}"
        start = lowered.find(marker)
        if start < 0:
            continue
        start += len(marker)
        end = lowered.find(quote, start)
        if end <= start:
            continue
        return lowered[start:end]
    return None


def _missing_ocr_binary(error: str, workdir: str | None = None) -> bool:
    """True only for the adapter's own missing-executable errors.

    ``ocr`` is already on PATH when this runs (the seat returned earlier
    otherwise). A review stderr that merely contains ``not found`` — a
    missing source file, a missing session file — must stay verbatim.

    ``failed to launch`` plus ``No such file or directory`` is also how
    Python reports a missing cwd. The quoted path is the binary when its
    basename is ``ocr`` or ``ocr.exe`` and it is not the cwd for this turn.
    A checkout directory named ``ocr`` stays the raw launch error.
    """
    lowered = (error or "").lower()
    if "executable not found" in lowered:
        return True
    if "failed to launch" not in lowered or "no such file or directory" not in lowered:
        return False
    missing = _quoted_enoent_path(lowered)
    if missing is None:
        return False
    if workdir and _launch_path_key(missing) == _launch_path_key(workdir):
        return False
    base = missing.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return base in {"ocr", "ocr.exe"}


# Back-compat alias: #1363 originally used code_reviewer as the OCR seat id.
CodeReviewerBlueprint = OcrReviewerBlueprint

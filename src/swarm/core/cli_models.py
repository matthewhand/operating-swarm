"""Non-interactive list-models probes for catalogued CLI adapters (REQ-44).

Each catalog CLI exposes a real list/help/models command (see
``cli_catalog.LIST_MODELS``). This module runs that argv with stdin closed and
a hard timeout, then parses boring model ids out of stdout.

Missing CLI, unknown name, nonzero exit, empty stdout, or timeout →
``{cli, models: []}`` plus a warning. Never raises to the caller. Never hangs.
Secrets are stripped from parsed ids and redacted from warnings.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from swarm.core import cli_catalog
from swarm.core.cli_adapter import TERM_GRACE
from swarm.utils.redact import SENSITIVE_PATTERNS, is_sensitive_key, redact_uri_credentials

logger = logging.getLogger(__name__)

# Keys commonly used as the model id in JSON catalogs (gemini / codex / …).
_JSON_ID_KEYS = ("modelId", "model_id", "slug", "id", "model", "name")
# Collections that wrap a list of models.
_JSON_LIST_KEYS = ("models", "data", "items", "available", "catalog")

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mK]")
# Boring ids: provider/model, dotted slugs, dates. Reject spaces and flags.
_MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:@+-]{0,200}$")
_SECRET_PREFIX_RE = re.compile(
    r"(?i)^(sk-|gsk_|xai-|AIza|ghp_|github_pat_|Bearer\s|-----BEGIN)"
)
_HEADER_WORDS = frozenset(
    {
        "id",
        "ids",
        "model",
        "models",
        "name",
        "names",
        "slug",
        "available",
        "catalog",
        "provider",
        "type",
        "tier",
        # Spinner/banner words some CLIs print before the list (agy prints
        # ``Fetching available models...``). Real model ids never look like
        # these, and a banner on stdout must not become a dropdown option.
        "fetching",
        "loading",
    }
)

RunExec = Callable[[list[str], float], Awaitable[tuple[int | None, str, str]]]


@dataclass
class ListModelsResult:
    """Outcome of one list-models probe. ``as_dict`` is the public JSON shape."""

    cli: str
    models: list[str]
    warning: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"cli": self.cli, "models": list(self.models)}
        if self.warning:
            out["warning"] = self.warning
        return out


def list_models(name: str, *, timeout: float | None = None) -> ListModelsResult:
    """Synchronous probe. Safe to call from Typer / Django (no event loop)."""
    return asyncio.run(probe_list_models(name, timeout=timeout))


def list_models_all(*, timeout: float | None = None) -> list[ListModelsResult]:
    """Probe every catalogued CLI (sorted). Never raises."""
    return asyncio.run(probe_list_models_all(timeout=timeout))


async def probe_list_models_all(*, timeout: float | None = None) -> list[ListModelsResult]:
    names = [n for n in cli_catalog.catalog_names() if n in cli_catalog.LIST_MODELS]
    rows = await asyncio.gather(*(probe_list_models(n, timeout=timeout) for n in names))
    return list(rows)


async def probe_list_models(
    name: str,
    *,
    timeout: float | None = None,
    which: Callable[[str], str | None] | None = None,
    run_exec: RunExec | None = None,
) -> ListModelsResult:
    """Run ``name``'s catalogued list-models argv. Never raises."""
    argv = cli_catalog.list_models_argv(name)
    if argv is None:
        warning = f"unknown CLI {name!r}; no list-models probe in the catalog"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    t = float(cli_catalog.LIST_MODELS_TIMEOUT if timeout is None else timeout)
    if t <= 0:
        warning = f"{name}: list-models timeout must be positive"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    exe = _resolve_executable(argv[0], which=which)
    if exe is None:
        warning = f"{name}: CLI not installed (no {argv[0]!r} on PATH)"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    resolved = [exe, *argv[1:]]
    runner = run_exec or _run_exec
    try:
        code, stdout, stderr = await runner(resolved, t)
    except asyncio.TimeoutError:
        warning = f"{name}: list-models probe timed out after {t:.1f}s"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)
    except Exception as exc:  # never crash the caller
        warning = _safe_warning(f"{name}: list-models probe failed: {exc}")
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    if code is None:
        warning = f"{name}: list-models probe timed out after {t:.1f}s"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)
    if code != 0:
        detail = (stderr or stdout or f"exit {code}").strip().splitlines()
        snippet = detail[0] if detail else f"exit {code}"
        warning = _safe_warning(f"{name}: list-models probe failed: {snippet}")
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    models = parse_models_stdout(stdout)
    if not models:
        warning = f"{name}: list-models probe returned no model ids"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)
    return ListModelsResult(cli=name, models=models)


def parse_models_stdout(stdout: str) -> list[str]:
    """Extract boring model ids from a CLI's list-models stdout.

    JSON (array / object / ``models`` wrapper) is preferred; otherwise each
    non-header line's first token is considered. Secrets and junk are dropped.
    """
    text = _strip_ansi(stdout or "").strip()
    if not text:
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return _ids_from_lines(text)
    return _dedupe(_ids_from_json(data))


def _ids_from_json(data: Any) -> list[str]:
    if isinstance(data, str):
        token = data.strip()
        return [token] if _is_model_id(token) else []
    if isinstance(data, list):
        out: list[str] = []
        for item in data:
            out.extend(_ids_from_json(item))
        return out
    if not isinstance(data, dict):
        return []
    for key in _JSON_LIST_KEYS:
        if key in data:
            return _ids_from_json(data[key])
    for key in _JSON_ID_KEYS:
        if is_sensitive_key(key):
            continue
        val = data.get(key)
        if isinstance(val, str) and _is_model_id(val.strip()):
            return [val.strip()]
    out = []
    for key, val in data.items():
        if is_sensitive_key(str(key)):
            continue
        out.extend(_ids_from_json(val))
    return out


def _ids_from_lines(text: str) -> list[str]:
    ids: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        token = line.split()[0].strip("•-*|:,")
        if token.lower() in _HEADER_WORDS:
            continue
        if _is_model_id(token):
            ids.append(token)
    return _dedupe(ids)


def _is_model_id(token: str) -> bool:
    if not token or token.lower() in _HEADER_WORDS:
        return False
    if _SECRET_PREFIX_RE.match(token):
        return False
    if "=" in token:  # KEY=value env dumps
        return False
    return bool(_MODEL_ID_RE.match(token))


def _dedupe(ids: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in ids:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


def _safe_warning(message: str) -> str:
    """Redact key-shaped tokens from probe warnings (never emit secrets)."""
    redacted = message
    for pattern in SENSITIVE_PATTERNS:
        redacted = re.sub(pattern, "[REDACTED]", redacted)
    redacted = redact_uri_credentials(redacted)
    redacted = _SECRET_PREFIX_RE.sub("[REDACTED]", redacted)
    return redacted


def _resolve_executable(
    argv0: str, *, which: Callable[[str], str | None] | None = None
) -> str | None:
    if os.path.sep in argv0:
        return argv0 if os.path.isfile(argv0) and os.access(argv0, os.X_OK) else None
    finder = which or cli_catalog.which_cli
    return finder(argv0)


async def _run_exec(argv: list[str], timeout: float) -> tuple[int | None, str, str]:
    """Run argv with stdin closed. Kill the process group on timeout."""
    env = os.environ.copy()
    env["PATH"] = cli_catalog.host_cli_path(env.get("PATH", ""))
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            env=env,
        )
    except (OSError, ValueError):
        raise
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        await _terminate(proc)
        return None, "", ""
    return proc.returncode, _decode(stdout_b), _decode(stderr_b)


async def _terminate(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is not None or not proc.pid or proc.pid <= 1:
        return
    try:
        pgid = os.getpgid(proc.pid)
        if pgid <= 1:
            return
    except (ProcessLookupError, OSError):
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            return
        try:
            await asyncio.wait_for(proc.wait(), timeout=TERM_GRACE)
            return
        except asyncio.TimeoutError:
            continue


def _decode(blob: bytes | None) -> str:
    if not blob:
        return ""
    return blob.decode("utf-8", errors="replace")

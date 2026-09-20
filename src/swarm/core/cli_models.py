"""Non-interactive list-models probes for catalogued CLI adapters (REQ-44 / REQ-877).

Each catalog CLI exposes a real list/help/models command (see
``cli_catalog.LIST_MODELS``). This module runs that argv with stdin closed and
a hard timeout, then parses boring model ids out of stdout.

Missing CLI → catalog ``CLI_MODELS`` presets when known (display hint for a
CLI that is not installed). Unknown name, nonzero exit, empty stdout, or
timeout → last-good cached models when available, otherwise an honest
``{cli, models: []}``, plus a warning — a probe that ran and failed never
reports fabricated presets (#272). Never raises to the caller. Never hangs.
Secrets are stripped from parsed ids and redacted from warnings.

Profile loading (``/v1/llm-profiles/``) uses ``list_models_many``: concurrent
probes, a 1.5s cap, TTL cache, and stale-while-revalidate so reloads do not
block on CLI subprocesses.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import signal
import threading
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from typing import Any

from swarm.core import cli_catalog
from swarm.core.async_utils import run_coro_sync
from swarm.core.cli_adapter import TERM_GRACE
from swarm.utils.redact import (
    SENSITIVE_PATTERNS,
    is_sensitive_key,
    redact_uri_credentials,
)

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

# REQ-877: profile-loading probes stay bounded, cached, and concurrent.
PROBE_TIMEOUT_S = 1.5
PROBE_CACHE_TTL_S = 10 * 60.0  # 10 minutes (within the 5–15 min window)
PROBE_TERM_GRACE_S = 0.25  # SIGTERM→SIGKILL for list-models only; not agent runs


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


@dataclass
class _CacheEntry:
    ts: float
    result: ListModelsResult
    last_good: ListModelsResult | None = None


_RESULT_CACHE: dict[str, _CacheEntry] = {}
_CACHE_LOCK = threading.Lock()
_IN_FLIGHT: set[str] = set()


def clear_probe_cache() -> None:
    """Drop cached probe results. Tests call this between cases."""
    with _CACHE_LOCK:
        _RESULT_CACHE.clear()
        _IN_FLIGHT.clear()


def list_models(name: str, *, timeout: float | None = None) -> ListModelsResult:
    """Synchronous probe. Safe to call from Typer / Django (no event loop)."""
    return list_models_many([name], timeout=timeout)[0]


def list_models_all(*, timeout: float | None = None) -> list[ListModelsResult]:
    """Probe every catalogued CLI (sorted). Never raises."""
    names = [
        n
        for n in cli_catalog.catalog_names()
        if n in cli_catalog.LIST_MODELS or n in cli_catalog.CLI_MODELS
    ]
    return list_models_many(names, timeout=timeout)


def list_models_many(
    names: Iterable[str],
    *,
    timeout: float | None = None,
) -> list[ListModelsResult]:
    """Probe ``names`` concurrently with TTL cache. Never raises.

    Default (``timeout is None``) is the REQ-877 profile-loading path: 1.5s
    cap, cache with TTL, last-good fallback, and stale-while-revalidate so a
    warm or expired cache never blocks the caller on a CLI subprocess.
    An explicit ``timeout`` bypasses the cache (tests / one-shot CLI).
    """
    ordered = [str(n) for n in names]
    if not ordered:
        return []
    if timeout is not None:
        return _run_many_sync(ordered, float(timeout))

    t = _default_timeout()
    now = time.monotonic()
    hits: dict[str, ListModelsResult] = {}
    stale: list[str] = []
    missing: list[str] = []
    with _CACHE_LOCK:
        for name in ordered:
            entry = _RESULT_CACHE.get(name)
            if entry is None:
                missing.append(name)
                continue
            hits[name] = _serve_entry(entry)
            if now - entry.ts >= PROBE_CACHE_TTL_S:
                stale.append(name)
    if stale:
        _schedule_refresh(stale, t)
    if missing:
        for row in _run_many_sync(missing, t):
            hits[row.cli] = _remember(row)
    empty = "list-models helper returned no payload"
    return [
        hits.get(
            name, ListModelsResult(cli=name, models=[], warning=f"{name}: {empty}")
        )
        for name in ordered
    ]


async def probe_list_models_all(
    *, timeout: float | None = None
) -> list[ListModelsResult]:
    names = [
        n
        for n in cli_catalog.catalog_names()
        if n in cli_catalog.LIST_MODELS or n in cli_catalog.CLI_MODELS
    ]
    return await probe_list_models_many(names, timeout=timeout)


async def probe_list_models_many(
    names: Iterable[str],
    *,
    timeout: float | None = None,
) -> list[ListModelsResult]:
    """Run list-models probes concurrently. Never raises."""
    ordered = [str(n) for n in names]
    if not ordered:
        return []
    rows = await asyncio.gather(
        *(probe_list_models(n, timeout=timeout) for n in ordered)
    )
    return list(rows)


def _catalog_presets(name: str) -> list[str]:
    raw = cli_catalog.CLI_MODELS.get(name) or []
    return [str(item).strip() for item in raw if str(item).strip()]


def _result_with_optional_presets(name: str, warning: str) -> ListModelsResult:
    """Known-CLI-missing → catalog presets when known, else empty + warning.

    Presets are a display hint for a CLI that is not installed on this host,
    never a substitute for a probe that ran and failed (#272): timeouts, auth
    failures, and empty stdout report honestly empty so the cache's last-good
    survives and the UI does not pin fabricated model ids.
    """
    logger.warning(warning)
    return ListModelsResult(cli=name, models=_catalog_presets(name), warning=warning)


def _result_runtime_failure(name: str, warning: str) -> ListModelsResult:
    """A probe that ran and failed: honest empty models + redacted warning."""
    logger.warning(warning)
    return ListModelsResult(cli=name, models=[], warning=warning)


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
        presets = _catalog_presets(name)
        if presets:
            warning = f"{name}: no list-models probe; using catalog presets"
            logger.warning(warning)
            return ListModelsResult(cli=name, models=presets, warning=warning)
        warning = f"unknown CLI {name!r}; no list-models probe in the catalog"
        logger.warning(warning)
        return ListModelsResult(cli=name, models=[], warning=warning)

    t = _default_timeout() if timeout is None else float(timeout)
    if t <= 0:
        return _result_runtime_failure(name, f"{name}: list-models timeout must be positive")

    exe = _resolve_executable(argv[0], which=which)
    if exe is None:
        # #716: name the searched scope — a container deployment scans only
        # its mounts, and a bare "on PATH" reads as nonsense to a user whose
        # host install is simply not visible in-container.
        return _result_with_optional_presets(
            name,
            f"{name}: CLI not installed — no {argv[0]!r} on the scanned PATH "
            "(user bin dirs + SWARM_CLI_PATH_DIRS + PATH)",
        )

    resolved = [exe, *argv[1:]]
    runner = run_exec or _run_exec
    try:
        code, stdout, stderr = await runner(resolved, t)
    except asyncio.TimeoutError:
        return _result_runtime_failure(
            name, f"{name}: list-models probe timed out after {t:.1f}s"
        )
    except Exception as exc:  # never crash the caller
        return _result_runtime_failure(
            name, _safe_warning(f"{name}: list-models probe failed: {exc}")
        )

    if code is None:
        return _result_runtime_failure(
            name, f"{name}: list-models probe timed out after {t:.1f}s"
        )
    if code != 0:
        detail = (stderr or stdout or f"exit {code}").strip().splitlines()
        snippet = detail[0] if detail else f"exit {code}"
        return _result_runtime_failure(
            name, _safe_warning(f"{name}: list-models probe failed: {snippet}")
        )

    models = parse_models_stdout(stdout)
    if not models:
        return _result_runtime_failure(
            name, f"{name}: list-models probe returned no model ids"
        )
    return ListModelsResult(cli=name, models=models)


def parse_models_stdout(stdout: str) -> list[str]:
    """Extract boring model ids from a CLI's list-models stdout.

    JSON (array / object / ``models`` wrapper) is preferred; otherwise each
    non-header line's first token is considered. A ``provider`` / ``model``
    table (``pi --list-models``) is joined as ``provider/model`` so the
    dropdown lists pin-able ids, not bare provider names. Secrets and junk
    are dropped.
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
    table = _is_provider_model_table(text)
    ids: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip("•-*|:,") for p in line.split() if p.strip("•-*|:,")]
        if not parts:
            continue
        if parts[0].lower() in _HEADER_WORDS:
            continue
        token = _line_model_id(parts, table=table)
        if token:
            ids.append(token)
    return _dedupe(ids)


def _is_provider_model_table(text: str) -> bool:
    """True when stdout is a ``provider  model  …`` table (pi --list-models)."""
    for raw in text.splitlines():
        parts = [p.lower() for p in raw.strip().split()]
        if len(parts) >= 2 and parts[0] == "provider" and parts[1] == "model":
            return True
    return False


def _line_model_id(parts: list[str], *, table: bool) -> str | None:
    """One pin-able id from a split line. Table rows join provider/model."""
    first = parts[0]
    if table:
        if len(parts) < 2:
            return None  # bare provider name is not a pin-able model
        provider, model = first, parts[1]
        if not _is_model_id(provider) or not _is_model_id(model):
            return None
        if "/" in provider or ":" in provider:
            composed = provider.replace(":", "/", 1)
        else:
            composed = f"{provider}/{model}"
        return composed if _is_model_id(composed) else None
    return first if _is_model_id(first) else None


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


def _default_timeout() -> float:
    return min(float(cli_catalog.LIST_MODELS_TIMEOUT), PROBE_TIMEOUT_S)


def _serve_entry(entry: _CacheEntry) -> ListModelsResult:
    if entry.result.models:
        return entry.result
    if entry.last_good and entry.last_good.models:
        return ListModelsResult(
            cli=entry.result.cli,
            models=list(entry.last_good.models),
            warning=entry.result.warning,
        )
    return entry.result


def _remember(row: ListModelsResult) -> ListModelsResult:
    with _CACHE_LOCK:
        prev = _RESULT_CACHE.get(row.cli)
        last_good = prev.last_good if prev is not None else None
        if row.models and "not installed" not in (row.warning or ""):
            # A real probe result refreshes last-good. Catalog presets from a
            # missing-CLI probe are a display hint only and must not evict the
            # last real model list (#272).
            last_good = row
        entry = _CacheEntry(ts=time.monotonic(), result=row, last_good=last_good)
        _RESULT_CACHE[row.cli] = entry
        return _serve_entry(entry)


def _run_many_sync(names: list[str], timeout: float) -> list[ListModelsResult]:
    return run_coro_sync(probe_list_models_many(names, timeout=timeout))


def _schedule_refresh(names: list[str], timeout: float) -> None:
    to_start: list[str] = []
    with _CACHE_LOCK:
        for name in names:
            if name in _IN_FLIGHT:
                continue
            _IN_FLIGHT.add(name)
            to_start.append(name)
    if not to_start:
        return
    threading.Thread(
        target=_refresh_names,
        args=(to_start, timeout),
        name="cli-model-probe",
        daemon=True,
    ).start()


def _refresh_names(names: list[str], timeout: float) -> None:
    try:
        for row in _run_many_sync(names, timeout):
            _remember(row)
    except Exception:
        logger.warning("background CLI model probe failed", exc_info=True)
    finally:
        with _CACHE_LOCK:
            for name in names:
                _IN_FLIGHT.discard(name)


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
        await _terminate(proc, grace=PROBE_TERM_GRACE_S)
        return None, "", ""
    return proc.returncode, _decode(stdout_b), _decode(stderr_b)


async def _terminate(
    proc: asyncio.subprocess.Process, *, grace: float = TERM_GRACE
) -> None:
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
            await asyncio.wait_for(proc.wait(), timeout=grace)
            return
        except asyncio.TimeoutError:
            continue


def _decode(blob: bytes | None) -> str:
    if not blob:
        return ""
    return blob.decode("utf-8", errors="replace")

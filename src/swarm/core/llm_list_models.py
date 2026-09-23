"""Consume REQ-44 (#360) list-models payloads for REQ-43 auto-pick.

#360 owns CLI list-models probes (``swarm.core.cli_models`` +
``GET /v1/cli-agents/<cli>/models``). This module **does not** scrape
``--help`` and does not spawn CLIs. When the sibling helper is importable,
auto-pick consumes ``{cli, models: [...], warning?}``. Until #360 merges,
the picker stubs on the OpenAI ``/v1/models`` list shape plus fixtures.

User-visible warnings never include REQ/Issue ticket jargon.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

logger = logging.getLogger("swarm.llm_list_models")

SOURCE_REQ44 = "req44"
SOURCE_STUB = "stub"

# Calm Settings / API copy. Never put REQ-xx or Issue numbers in product UI.
SKIPPED_NO_CLI_COPY = "No CLI agents connected — add a CLI to list models"
HELPER_UNAVAILABLE_COPY = (
    "Could not list models from connected CLIs; using the configured catalog instead."
)

_TICKET_JARGON_RE = re.compile(
    r"\(?\bREQ-\d+\b\)?"
    r"|\(?\bIssue\s+#?\d+\b\)?"
    r"|#\d+\b",
    re.IGNORECASE,
)

# Live REQ-44 probes are cached per connected CLI set so Settings / chat
# do not re-run each CLI on every resolve. TTL matches cli_models (5–15 min).
# Tests call clear_discovery_cache().
_DISCOVERY_TTL_S = 10 * 60.0
_DISCOVERY_CACHE: dict[tuple[str, ...], tuple[float, list[dict[str, Any]], str, list[str]]] = {}


def clear_discovery_cache() -> None:
    _DISCOVERY_CACHE.clear()
    try:
        from swarm.core.cli_models import clear_probe_cache
    except ImportError:
        return
    clear_probe_cache()

# REQ-44 public JSON shape (one CLI) and the OpenAI /v1/models list shape.
# {cli, models: [...], warning?}
# {object: "list", data: [{id, owned_by?}]}


def req44_helper_available() -> bool:
    """True when #360's ``swarm.core.cli_models`` helper is importable."""
    return _req44_list_models() is not None


def _req44_list_models() -> Callable[[str], Any] | None:
    try:
        from swarm.core.cli_models import list_models
    except ImportError:
        return None
    return list_models


def _in_test_mode() -> bool:
    flag = os.environ.get("SWARM_TEST_MODE", "").lower()
    if flag in {"1", "true", "yes", "t", "y"}:
        return True
    return "PYTEST_CURRENT_TEST" in os.environ


def configured_cli_names(config: dict[str, Any] | None) -> list[str]:
    """Connected ``cli_agents`` keys only — not every installed catalog CLI."""
    block = (config or {}).get("cli_agents")
    if not isinstance(block, dict):
        return []
    return [str(name) for name in block if str(name).strip()]


def sanitize_ui_warning(text: str) -> str:
    """Strip REQ/Issue ticket jargon from copy shown in product UI."""
    if not text or not str(text).strip():
        return ""
    cleaned = _TICKET_JARGON_RE.sub(" ", str(text))
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip(" \t;,.-\u2014")


def sanitize_ui_warnings(warnings: Iterable[str]) -> list[str]:
    """Deduped, ticket-jargon-free warning list for Settings / API."""
    out: list[str] = []
    for raw in warnings:
        cleaned = sanitize_ui_warning(raw)
        if cleaned and cleaned not in out:
            out.append(cleaned)
    return out


def probe_cli_names(
    config: dict[str, Any] | None,
    *,
    installed: Iterable[str] | None = None,
    include_installed: bool = False,
) -> list[str]:
    """CLI ids to probe: configured agents, plus installed catalog CLIs when asked.

    ``installed`` is an explicit list (tests). Live Settings passes
    ``include_installed=True`` so PATH CLIs are probed even when
    ``cli_agents`` is empty. This function never scrapes ``--help``.
    """
    names = list(configured_cli_names(config))
    seen = {name.lower() for name in names}
    extras: Iterable[str]
    if installed is not None:
        extras = installed
    elif include_installed:
        extras = _installed_probe_names(config)
    else:
        extras = []
    for raw in extras:
        name = str(raw).strip()
        if not name or name.lower() in seen:
            continue
        names.append(name)
        seen.add(name.lower())
    return names


def _installed_probe_names(config: dict[str, Any] | None) -> list[str]:
    try:
        from swarm.core.cli_catalog import has_list_models, installed_host_clis
    except ImportError:
        return []
    return [name for name in installed_host_clis(config) if has_list_models(name)]


def normalize_list_models_payload(payload: Any) -> list[dict[str, Any]]:
    """Accept REQ-44 ``{cli, models}`` (or a list of those) or ``/v1/models``.

    Never raises. Unknown shapes → empty list.
    """
    if payload is None:
        return []
    if isinstance(payload, (str, Path)):
        return _load_fixture(payload)
    if isinstance(payload, list):
        if not payload:
            return []
        if all(isinstance(item, str) for item in payload):
            models = [item.strip() for item in payload if isinstance(item, str) and item.strip()]
            return [{"cli": "v1/models", "models": models}] if models else []
        if all(isinstance(item, dict) and "models" in item for item in payload):
            return [_clean_req44(item) for item in payload if isinstance(item, dict)]
        if all(isinstance(item, dict) and "id" in item for item in payload):
            return _from_openai_data(payload)
        out: list[dict[str, Any]] = []
        for item in payload:
            out.extend(normalize_list_models_payload(item))
        return out
    if isinstance(payload, dict):
        if "cli" in payload and "models" in payload:
            return [_clean_req44(payload)]
        if isinstance(payload.get("data"), list):
            return _from_openai_data(payload["data"], owned_by=payload.get("object") or "v1/models")
        if isinstance(payload.get("models"), list):
            return [_clean_req44({"cli": payload.get("cli") or "catalog", "models": payload["models"], "warning": payload.get("warning")})]
    return []


def _from_openai_data(rows: Iterable[Any], *, owned_by: str = "v1/models") -> list[dict[str, Any]]:
    models: list[str] = []
    for row in rows:
        if isinstance(row, str) and row.strip():
            models.append(row.strip())
            continue
        if isinstance(row, dict):
            ident = row.get("id")
            if isinstance(ident, str) and ident.strip():
                models.append(ident.strip())
    if not models:
        return []
    return [{"cli": str(owned_by or "v1/models"), "models": models}]


def _clean_req44(row: dict[str, Any]) -> dict[str, Any]:
    cli = row.get("cli")
    cli_id = str(cli).strip() if cli is not None and str(cli).strip() else "catalog"
    raw = row.get("models") or []
    models: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                models.append(item.strip())
            elif isinstance(item, dict):
                ident = item.get("id") or item.get("model")
                if isinstance(ident, str) and ident.strip():
                    models.append(ident.strip())
    out: dict[str, Any] = {"cli": cli_id, "models": models}
    warning = row.get("warning")
    if isinstance(warning, str) and warning.strip():
        out["warning"] = warning.strip()
    return out


def _load_fixture(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("list-models fixture %s unreadable: %s", target, exc)
        return [{"cli": target.stem, "models": [], "warning": f"fixture {target} unreadable"}]
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        models = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        return [{"cli": target.stem, "models": models}] if models else []
    return normalize_list_models_payload(data)


def load_list_models_fixtures(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load REQ-44 or ``/v1/models`` fixtures. No secrets expected in files."""
    rows: list[dict[str, Any]] = []
    for path in paths:
        rows.extend(normalize_list_models_payload(path))
    return rows


def _as_req44_dict(result: Any, name: str) -> dict[str, Any]:
    if hasattr(result, "as_dict"):
        try:
            result = result.as_dict()
        except Exception:
            result = None
    if isinstance(result, dict):
        cleaned = normalize_list_models_payload(result)
        return cleaned[0] if cleaned else {"cli": name, "models": [], "warning": f"{name}: empty list-models payload"}
    return {"cli": name, "models": [], "warning": f"{name}: list-models helper returned no payload"}


def _probe_live_many(names: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    """Shipped concurrent/cached probe path. Never raises."""
    from swarm.core.cli_models import list_models_many

    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    try:
        raw_rows = list_models_many(names)
    except Exception as exc:  # never crash Settings / auto-pick
        warning = f"list-models helper failed: {exc}"
        logger.warning(warning)
        for name in names:
            rows.append({"cli": name, "models": [], "warning": warning})
        return rows, [warning]
    for raw in raw_rows:
        name = str(getattr(raw, "cli", None) or "catalog")
        row = _as_req44_dict(raw, name)
        if row.get("warning"):
            row["warning"] = sanitize_ui_warning(str(row["warning"])) or row["warning"]
            warnings.append(str(row["warning"]))
        rows.append(row)
    return rows, warnings


def discover_cli_model_lists(
    config: dict[str, Any] | None = None,
    *,
    helper: Callable[[str], Any] | None | bool = None,
    v1_models: Any = None,
    fixtures: Iterable[str | Path | dict[str, Any]] | None = None,
    probe: bool | None = None,
    installed: Iterable[str] | None = None,
) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Return ``({cli, models}…, source, warnings)``.

    * ``helper`` — injected REQ-44 ``list_models(name)``. ``None`` tries the
      real import. ``False`` forces the stub path (tests / no probe).
    * Live probes run only when the helper exists, ``probe`` is true, and we
      are not in ``SWARM_TEST_MODE``. This PR never scrapes ``--help``.
    * When CLIs are installed on PATH (or passed via ``installed``), the
      probe runs even if ``cli_agents`` is empty.
    * Stub path consumes ``v1_models`` (OpenAI list) + fixtures + optional
      ``config['v1_models']`` / ``config['list_models']``.
    """
    warnings: list[str] = []

    resolved_helper: Callable[[str], Any] | None
    if helper is False:
        resolved_helper = None
    elif helper is None or helper is True:
        resolved_helper = _req44_list_models()
    else:
        resolved_helper = helper

    should_probe = probe
    if should_probe is None:
        should_probe = resolved_helper is not None and not _in_test_mode()

    names = probe_cli_names(
        config,
        installed=installed,
        include_installed=bool(should_probe and not _in_test_mode() and installed is None),
    )

    if resolved_helper is not None and should_probe and names:
        cache_key = tuple(names)
        if helper is None:
            cached_probe = _DISCOVERY_CACHE.get(cache_key)
            if cached_probe is not None:
                ts, rows, source, cached_warnings = cached_probe
                if time.monotonic() - ts < _DISCOVERY_TTL_S:
                    return rows, source, cached_warnings
            rows, warnings = _probe_live_many(names)
            result = (rows, SOURCE_REQ44, sanitize_ui_warnings(warnings))
            _DISCOVERY_CACHE[cache_key] = (time.monotonic(),) + result
            return result
        rows = []
        for name in names:
            try:
                raw = resolved_helper(name)
            except Exception as exc:  # never crash Settings / auto-pick
                warning = f"{name}: list-models helper failed: {exc}"
                logger.warning(warning)
                rows.append({"cli": name, "models": [], "warning": warning})
                warnings.append(warning)
                continue
            row = _as_req44_dict(raw, name)
            if row.get("warning"):
                row["warning"] = sanitize_ui_warning(str(row["warning"])) or row["warning"]
                warnings.append(str(row["warning"]))
            rows.append(row)
        return rows, SOURCE_REQ44, sanitize_ui_warnings(warnings)

    rows = []
    extra = v1_models
    if extra is None and isinstance(config, dict):
        extra = config.get("v1_models")
    if extra is not None:
        rows.extend(normalize_list_models_payload(extra))

    cached = (config or {}).get("list_models") if isinstance(config, dict) else None
    if cached is not None:
        rows.extend(normalize_list_models_payload(cached))

    if fixtures:
        for item in fixtures:
            rows.extend(normalize_list_models_payload(item))

    if not rows:
        if names:
            warning = HELPER_UNAVAILABLE_COPY
            warnings.append(warning)
            for name in names:
                rows.append({"cli": name, "models": [], "warning": warning})
        elif extra is None and not fixtures:
            # Nothing connected and nothing stubbed — caller still has config llm.
            pass

    source = SOURCE_STUB
    if resolved_helper is not None and should_probe and not names:
        source = SOURCE_REQ44
        warnings.append(SKIPPED_NO_CLI_COPY)
    return rows, source, sanitize_ui_warnings(warnings)

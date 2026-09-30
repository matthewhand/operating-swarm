"""Optional Composio connector catalog source (#1327).

Composio's catalog is a large, OAuth-managed connector set that widens the
Plugins marketplace beyond the Official MCP Registry. This module mirrors
:mod:`swarm.core.mcp_registry`: TTL cache, paged fetch, last-good on failure,
``plugin_spec_from_*`` -> OS plugin spec, and honest warnings.

Two robustness rules from #1327 are load-bearing here:

* **Partial, not fail-closed** — a mid-page failure keeps the pages already
  fetched and reports ``stalled_reason``; the caller merges what is available.
* **A stall must say why** — failures are classified (dns / timeout / tls /
  rate_limit / offline / http_<status>) via
  :mod:`swarm.core.catalog_fetch`, never a bare exception class name.

Secrets never appear: the Composio API key is used only as a request header,
and env values are never emitted into items. Auth to each connector is OAuth,
so no env placeholder is required.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable

from swarm.core import catalog_fetch
from swarm.core import mcp_registry
from swarm.core.paths import get_user_cache_dir_for_swarm

logger = logging.getLogger(__name__)

COMPOSIO_TOOLKITS_URL = "https://backend.composio.dev/api/v3/toolkits"
COMPOSIO_MCP_URL_TEMPLATE = "https://mcp.composio.dev/{slug}"
COMPOSIO_API_KEY_ENV = "COMPOSIO_API_KEY"
CACHE_TTL_S = 24 * 60 * 60
PAGE_LIMIT = 100
MAX_PAGES = 3
REQUEST_TIMEOUT_S = 15.0

FetchJson = Callable[[str, dict[str, str], dict[str, str]], tuple[int, Any]]

SOURCE_ID = "composio"
SOURCE_LABEL = "Composio"
COMMUNITY_NOTE = "Community / external content — not vetted by open-swarm."


def cache_path() -> Path:
    return get_user_cache_dir_for_swarm() / "composio.json"


def _slug(name: str) -> str:
    return mcp_registry._slug(name)


def _toolkit_slug(toolkit: dict[str, Any]) -> str:
    raw = str(toolkit.get("slug") or toolkit.get("name") or "").strip()
    return _slug(raw)


def plugin_spec_from_toolkit(toolkit: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one Composio toolkit to an OS ``mcpServers`` plugin spec.

    Emits a ``remote`` (streamable-http) spec pointing at Composio's hosted MCP
    server for the toolkit. Auth is the Composio OAuth flow, so no secret is
    embedded and no env placeholder is required.
    """
    if not isinstance(toolkit, dict):
        return None
    slug = _toolkit_slug(toolkit)
    if not slug:
        return None
    label = mcp_registry.public_text(toolkit.get("name") or slug, 80) or slug
    note = mcp_registry.public_text(toolkit.get("description") or toolkit.get("meta_description"))
    spec: dict[str, Any] = {
        "name": f"composio-{slug}",
        "label": label,
        "kind": "remote",
        "source": SOURCE_ID,
        "url": COMPOSIO_MCP_URL_TEMPLATE.format(slug=slug),
        "type": "streamable-http",
        "note": note,
        "toolkit": slug,
        "auth": "oauth",
    }
    return spec


def normalize_composio_item(toolkit: Any) -> dict[str, Any] | None:
    """Project one Composio toolkit row onto the stable public catalog shape."""
    if not isinstance(toolkit, dict):
        return None
    spec = plugin_spec_from_toolkit(toolkit)
    if spec is None:
        return None
    slug = spec["toolkit"]
    tools_count = toolkit.get("tools_count") or toolkit.get("toolsCount")
    try:
        tools_count = int(tools_count)
    except (TypeError, ValueError):
        tools_count = 0
    return {
        "id": f"composio:{slug}",
        "kind": "plugins",
        "name": spec["label"],
        "summary": spec.get("note") or "",
        "source": SOURCE_ID,
        "source_label": SOURCE_LABEL,
        "external": True,
        "installable": True,
        "installed": False,
        "html_url": f"https://composio.dev/toolkits/{slug}",
        "required_env": [],
        "tools_provided": [],
        "danger_notes": [
            COMMUNITY_NOTE,
            "OAuth-managed by Composio — sign in to authorize this connector.",
        ],
        "plugin": spec,
        "tool_count": tools_count,
    }


def _load_cache(path: Path) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict) or not isinstance(raw.get("items"), list):
        return None
    return raw


def _save_cache(path: Path, payload: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("Composio catalog cache write failed: %s", exc)


def _is_fresh(payload: dict[str, Any], *, now: float, ttl: float) -> bool:
    try:
        fetched_at = float(payload.get("fetched_at"))
    except (TypeError, ValueError):
        return False
    return (now - fetched_at) < ttl


def _next_cursor(payload: dict[str, Any]) -> str:
    return str(
        payload.get("next_cursor") or payload.get("nextCursor") or payload.get("cursor") or ""
    ).strip()


def _fetch_pages(
    fetch: FetchJson, headers: dict[str, str]
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """Fetch up to ``MAX_PAGES`` pages, keeping partial results on failure.

    Returns ``(items, warnings, stalled_reason)``. A stall never discards the
    pages already fetched.
    """
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    stalled_reason: str | None = None
    cursor = ""
    seen_ids: set[str] = set()
    for _page in range(MAX_PAGES):
        params: dict[str, str] = {"limit": str(PAGE_LIMIT)}
        if cursor:
            params["cursor"] = cursor
        try:
            status, payload = fetch(COMPOSIO_TOOLKITS_URL, headers, params)
        except Exception as exc:  # network error, DNS, timeout, TLS — honest degrade
            stalled_reason = catalog_fetch.classify_fetch_exception(exc)
            warnings.append(
                f"Composio request failed: {exc.__class__.__name__} ({stalled_reason})."
            )
            break
        reason = catalog_fetch.classify_fetch_status(status, payload)
        if reason is not None:
            stalled_reason = reason
            warnings.append(catalog_fetch.stall_message(SOURCE_LABEL, reason))
            break
        if not isinstance(payload, dict):
            stalled_reason = "payload"
            warnings.append("Composio payload was not a toolkit list.")
            break
        rows = payload.get("items")
        if rows is None:
            rows = payload.get("toolkits")
        if not isinstance(rows, list):
            stalled_reason = "payload"
            warnings.append("Composio payload was not a toolkit list.")
            break
        for row in rows:
            item = normalize_composio_item(row)
            if item is None or item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            items.append(item)
        cursor = _next_cursor(payload)
        if not cursor:
            break
    if not items and not warnings:
        warnings.append("Composio returned no connectors.")
    return items, warnings, stalled_reason


def _default_fetch(url: str, headers: dict[str, str], params: dict[str, str]) -> tuple[int, Any]:
    from swarm.core.marketplace import fetch_json_urllib

    return fetch_json_urllib(url, headers, params)


def composio_enabled_from_config(config: dict[str, Any] | None = None) -> bool:
    """Whether the Composio source is enabled in ``swarm_config`` settings.

    Reads ``settings.marketplace.composio.enabled``. Defaults to ``False`` and
    never raises: an absent/malformed config means "off", not an error.
    """
    if config is None:
        try:
            from swarm.core.requirements import load_active_config

            config = load_active_config()
        except Exception:
            return False
    if not isinstance(config, dict):
        return False
    settings = config.get("settings")
    if not isinstance(settings, dict):
        return False
    marketplace = settings.get("marketplace")
    if not isinstance(marketplace, dict):
        return False
    composio = marketplace.get("composio")
    if not isinstance(composio, dict):
        return False
    return bool(composio.get("enabled"))


def fetch_composio_servers(
    *,
    fetch_json: FetchJson | None = None,
    cache_file: Path | None = None,
    now: float | None = None,
    ttl: float = CACHE_TTL_S,
    force: bool = False,
    enabled: bool = True,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Return cached Composio connector items.

    Fresh cache is reused. Stale/missing cache triggers one poll. A failure
    returns last-good items plus a classified ``stalled_reason`` — never a
    fabricated list and never an unbounded wait.
    """
    path = cache_file if cache_file is not None else cache_path()
    clock = time.time() if now is None else now

    if not enabled:
        return {
            "object": "composio_catalog",
            "items": [],
            "warnings": [
                "Composio source is not configured "
                "(settings.marketplace.composio.enabled is off)."
            ],
            "cached": False,
            "fetched_at": None,
            "stalled_reason": "not_configured",
        }

    key = api_key if api_key is not None else _env_api_key()
    cached = _load_cache(path)
    if cached and not force and _is_fresh(cached, now=clock, ttl=ttl):
        return {
            "object": "composio_catalog",
            "items": list(cached.get("items") or []),
            "warnings": [],
            "cached": True,
            "fetched_at": cached.get("fetched_at"),
            "stalled_reason": None,
        }

    if not key:
        return {
            "object": "composio_catalog",
            "items": list((cached or {}).get("items") or []),
            "warnings": [
                "Composio source is not configured (set COMPOSIO_API_KEY to enable)."
            ],
            "cached": bool(cached and cached.get("items")),
            "fetched_at": (cached or {}).get("fetched_at"),
            "stalled_reason": "not_configured",
        }

    fetch = fetch_json or _default_fetch
    headers = {
        "Accept": "application/json",
        "x-api-key": key,
        "User-Agent": "open-swarm-composio-cache",
    }
    items, warnings, stalled_reason = _fetch_pages(fetch, headers)

    if items:
        payload = {
            "object": "composio_catalog",
            "fetched_at": clock,
            "items": items,
        }
        _save_cache(path, payload)
        return {
            "object": "composio_catalog",
            "items": items,
            "warnings": warnings,
            "cached": False,
            "fetched_at": clock,
            "stalled_reason": stalled_reason,
        }

    if cached and isinstance(cached.get("items"), list) and cached["items"]:
        warnings.append("Showing last-good Composio cache.")
        return {
            "object": "composio_catalog",
            "items": list(cached["items"]),
            "warnings": warnings,
            "cached": True,
            "fetched_at": cached.get("fetched_at"),
            "stalled_reason": stalled_reason or "offline",
        }
    return {
        "object": "composio_catalog",
        "items": [],
        "warnings": warnings or ["Composio is unavailable."],
        "cached": False,
        "fetched_at": None,
        "stalled_reason": stalled_reason or "offline",
    }


def _env_api_key() -> str:
    import os

    return (os.environ.get(COMPOSIO_API_KEY_ENV) or "").strip()

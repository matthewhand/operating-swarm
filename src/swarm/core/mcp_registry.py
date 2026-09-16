"""Cached Official MCP Registry client (REQ-887 / #292).

Primary plugin metadata SoT: ``https://registry.modelcontextprotocol.io``.
Poll/cache (TTL) — do not query on every keystroke. Last-good cache is
returned on offline / rate-limit with an honest warning.

Install format is the existing ``mcpServers`` plugin spec. Env values are
never stored or listed — names become ``${VAR}`` placeholders only.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

from swarm.core.paths import get_user_cache_dir_for_swarm

logger = logging.getLogger(__name__)

MCP_REGISTRY_URL = "https://registry.modelcontextprotocol.io"
MCP_REGISTRY_SERVERS = f"{MCP_REGISTRY_URL}/v0.1/servers"
CACHE_TTL_S = 24 * 60 * 60
PAGE_LIMIT = 100
MAX_PAGES = 3
REQUEST_TIMEOUT_S = 15.0

FetchJson = Callable[[str, dict[str, str], dict[str, str]], tuple[int, Any]]

_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_SECRET_VALUE_RE = re.compile(
    r"sk-[A-Za-z0-9_-]{4,}|bearer\s+[A-Za-z0-9._\-]{8,}",
    re.IGNORECASE,
)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class McpRegistryError(Exception):
    """Honest registry client failure (never a fake catalog)."""

    def __init__(self, message: str, *, code: str = "mcp_registry_error"):
        super().__init__(message)
        self.code = code


def cache_path() -> Path:
    return get_user_cache_dir_for_swarm() / "mcp_registry.json"


def _slug(name: str) -> str:
    raw = (name or "").strip().lower()
    if "/" in raw:
        raw = raw.rsplit("/", 1)[-1]
    slug = _SLUG_RE.sub("-", raw).strip("-")
    return slug or "mcp-server"


def public_text(value: Any, max_len: int = 240) -> str:
    """Listing copy: collapse whitespace; drop secret-shaped values."""
    raw = " ".join(str(value or "").split()).strip()
    if not raw or _SECRET_VALUE_RE.search(raw):
        return ""
    if len(raw) > max_len:
        return raw[: max_len - 1] + "…"
    return raw


def _env_placeholder_map(variables: Any) -> dict[str, str]:
    """Map environmentVariables entries to ``{NAME: ${NAME}}``. Values discarded."""
    out: dict[str, str] = {}
    if not isinstance(variables, list):
        return out
    for item in variables:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not _ENV_NAME_RE.match(name):
            continue
        out[name] = f"${{{name}}}"
    return out


def _arg_values(raw: Any) -> list[str]:
    values: list[str] = []
    if not isinstance(raw, list):
        return values
    for item in raw:
        if isinstance(item, str) and item.strip():
            values.append(item.strip())
        elif isinstance(item, dict):
            val = item.get("value")
            if isinstance(val, str) and val.strip():
                values.append(val.strip())
    return values


def command_from_package(pkg: dict[str, Any]) -> tuple[str, list[str]]:
    """Map a server.json package to local stdio ``(command, args)``."""
    rtype = str(pkg.get("registryType") or pkg.get("registry_type") or "").strip().lower()
    ident = str(pkg.get("identifier") or "").strip()
    hint = str(pkg.get("runtimeHint") or pkg.get("runtime_hint") or "").strip()
    runtime_args = _arg_values(pkg.get("runtimeArguments") or pkg.get("runtime_arguments"))
    pkg_args = _arg_values(pkg.get("packageArguments") or pkg.get("package_arguments"))
    if rtype == "npm":
        cmd = hint or "npx"
        args = list(runtime_args) if runtime_args else ["-y"]
        if ident and ident not in args:
            args.append(ident)
        args.extend(pkg_args)
        return cmd, args
    if rtype in ("pypi", "uv", "uvx"):
        cmd = hint or "uvx"
        args = list(runtime_args)
        if ident and ident not in args:
            args.append(ident)
        args.extend(pkg_args)
        return cmd, args
    if hint:
        args = list(runtime_args)
        if ident and ident not in args:
            args.append(ident)
        args.extend(pkg_args)
        return hint, args
    return "", []


def plugin_spec_from_server(server: dict[str, Any]) -> dict[str, Any] | None:
    """Convert Official Registry ``server.json`` to an OS plugin spec.

    Secrets never appear: env/header values are ``${NAME}`` placeholders.
    """
    if not isinstance(server, dict):
        return None
    raw_name = str(server.get("name") or "").strip()
    if not raw_name:
        return None
    slug = _slug(raw_name)
    label = public_text(server.get("title") or raw_name, 80) or slug
    note = public_text(server.get("description"))
    remotes = server.get("remotes") if isinstance(server.get("remotes"), list) else []
    packages = server.get("packages") if isinstance(server.get("packages"), list) else []

    if remotes:
        remote = remotes[0] if isinstance(remotes[0], dict) else None
        url = str((remote or {}).get("url") or "").strip()
        if url.startswith("http://") or url.startswith("https://"):
            headers = _env_placeholder_map((remote or {}).get("headers"))
            transport = str((remote or {}).get("type") or "sse").strip() or "sse"
            spec: dict[str, Any] = {
                "name": slug,
                "label": label,
                "kind": "remote",
                "source": "generic",
                "url": url,
                "type": transport,
                "note": note,
                "registry_name": raw_name,
            }
            if headers:
                spec["headers"] = headers
                spec["env"] = headers
            return spec

    if packages:
        pkg = packages[0] if isinstance(packages[0], dict) else None
        if not pkg:
            return None
        command, args = command_from_package(pkg)
        if not command:
            return None
        env = _env_placeholder_map(
            pkg.get("environmentVariables") or pkg.get("environment_variables")
        )
        spec = {
            "name": slug,
            "label": label,
            "kind": "local",
            "source": "generic",
            "command": command,
            "args": args,
            "note": note,
            "registry_name": raw_name,
        }
        if env:
            spec["env"] = env
        return spec
    return None


def required_env_names(spec: dict[str, Any] | None) -> list[str]:
    if not isinstance(spec, dict):
        return []
    names: list[str] = []
    for field in ("env", "headers"):
        block = spec.get(field)
        if not isinstance(block, dict):
            continue
        for key in block:
            name = str(key).strip()
            if _ENV_NAME_RE.match(name) and name not in names:
                names.append(name)
    names.sort()
    return names


def normalize_registry_item(entry: Any) -> dict[str, Any] | None:
    """Project one registry list row onto the stable public catalog shape."""
    if not isinstance(entry, dict):
        return None
    server = entry.get("server") if isinstance(entry.get("server"), dict) else entry
    spec = plugin_spec_from_server(server)
    if spec is None:
        return None
    raw_name = str(server.get("name") or spec.get("registry_name") or "").strip()
    meta = {}
    raw_meta = entry.get("_meta")
    if isinstance(raw_meta, dict):
        official = raw_meta.get("io.modelcontextprotocol.registry/official")
        if isinstance(official, dict):
            meta = official
    item = {
        "id": f"mcp:{raw_name}",
        "kind": "plugins",
        "name": spec["label"],
        "summary": spec.get("note") or "",
        "source": "mcp_registry",
        "source_label": "Official MCP Registry",
        "external": True,
        "installable": True,
        "installed": False,
        "html_url": public_text(
            (server.get("repository") or {}).get("url")
            if isinstance(server.get("repository"), dict)
            else server.get("websiteUrl") or server.get("website_url"),
            200,
        )
        or "",
        "version": public_text(server.get("version"), 32),
        "required_env": required_env_names(spec),
        "tools_provided": [],
        "danger_notes": [
            "Community / external content — not vetted by open-swarm.",
        ],
        "plugin": spec,
        "registry_status": public_text(meta.get("status"), 32),
    }
    return item


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
        logger.warning("MCP registry cache write failed: %s", exc)


def _is_fresh(payload: dict[str, Any], *, now: float, ttl: float) -> bool:
    fetched = payload.get("fetched_at")
    try:
        fetched_at = float(fetched)
    except (TypeError, ValueError):
        return False
    return (now - fetched_at) < ttl


def _fetch_pages(fetch: FetchJson, headers: dict[str, str]) -> tuple[list[dict[str, Any]], list[str]]:
    items: list[dict[str, Any]] = []
    warnings: list[str] = []
    cursor = ""
    seen_ids: set[str] = set()
    for _page in range(MAX_PAGES):
        params = {"limit": str(PAGE_LIMIT), "version": "latest"}
        if cursor:
            params["cursor"] = cursor
        try:
            status, payload = fetch(MCP_REGISTRY_SERVERS, headers, params)
        except Exception as exc:
            warnings.append(f"Official MCP Registry request failed: {exc.__class__.__name__}.")
            break
        if status == 429 or (status == 403 and "rate" in str(payload).lower()):
            warnings.append("Official MCP Registry rate limit reached — using cache if available.")
            break
        if status != 200 or not isinstance(payload, dict):
            warnings.append(f"Official MCP Registry returned HTTP {status}.")
            break
        rows = payload.get("servers")
        if not isinstance(rows, list):
            warnings.append("Official MCP Registry payload was not a server list.")
            break
        for row in rows:
            item = normalize_registry_item(row)
            if item is None or item["id"] in seen_ids:
                continue
            seen_ids.add(item["id"])
            items.append(item)
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        cursor = str(meta.get("nextCursor") or meta.get("next_cursor") or "").strip()
        if not cursor:
            break
    if not items and not warnings:
        warnings.append("Official MCP Registry returned no servers.")
    return items, warnings


def _default_fetch(url: str, headers: dict[str, str], params: dict[str, str]) -> tuple[int, Any]:
    from swarm.core.marketplace import fetch_json_urllib

    return fetch_json_urllib(url, headers, params)


def fetch_registry_servers(
    *,
    fetch_json: FetchJson | None = None,
    cache_file: Path | None = None,
    now: float | None = None,
    ttl: float = CACHE_TTL_S,
    force: bool = False,
) -> dict[str, Any]:
    """Return cached Official MCP Registry catalog items.

    Fresh cache is reused. Stale/missing cache triggers one poll. Failure
    returns last-good items plus warnings — never a fabricated list.
    """
    path = cache_file if cache_file is not None else cache_path()
    clock = time.time() if now is None else now
    cached = _load_cache(path)
    if cached and not force and _is_fresh(cached, now=clock, ttl=ttl):
        return {
            "object": "mcp_registry_cache",
            "items": list(cached.get("items") or []),
            "warnings": [],
            "cached": True,
            "fetched_at": cached.get("fetched_at"),
        }

    fetch = fetch_json or _default_fetch
    headers = {
        "Accept": "application/json",
        "User-Agent": "open-swarm-mcp-registry-cache",
    }
    items, warnings = _fetch_pages(fetch, headers)
    if items:
        payload = {
            "object": "mcp_registry_cache",
            "fetched_at": clock,
            "items": items,
        }
        _save_cache(path, payload)
        return {
            "object": "mcp_registry_cache",
            "items": items,
            "warnings": warnings,
            "cached": False,
            "fetched_at": clock,
        }

    if cached and isinstance(cached.get("items"), list) and cached["items"]:
        warnings.append("Showing last-good Official MCP Registry cache.")
        return {
            "object": "mcp_registry_cache",
            "items": list(cached["items"]),
            "warnings": warnings,
            "cached": True,
            "fetched_at": cached.get("fetched_at"),
        }
    return {
        "object": "mcp_registry_cache",
        "items": [],
        "warnings": warnings or ["Official MCP Registry is unavailable."],
        "cached": False,
        "fetched_at": None,
    }

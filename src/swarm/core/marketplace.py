"""GitHub marketplace scan for Teams/Plugins popups (#179).

Scans the GitHub repository-search API for community shareables tagged with
open-swarm topics:

* ``swarm-team-pack``     — shareable team rosters (Teams popup)
* ``swarm-mcp-plugin``    — MCP plugin server packages (Plugins popup)
* ``open-swarm-plugin``   — generic plugin packages (Plugins popup)

Design notes:
* The scan runs server-side so browsers are not subject to GitHub's
  aggressive unauthenticated rate limits, and an optional ``GITHUB_TOKEN``
  (env) is used transparently when present.
* Results are **community/external content** — every response carries
  ``external: true`` and the UI must label it before any install.
* Failures are honest: non-200 from GitHub or a network error returns a
  structured empty result with a warning, never a fabricated list.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

MARKETPLACE_TOPICS_TEAMS = ("swarm-team-pack",)
MARKETPLACE_TOPICS_PLUGINS = ("swarm-mcp-plugin", "open-swarm-plugin")

GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"

#: Per-topic page size; GitHub caps search at 100 but a scan needs fewer.
PER_TOPIC_LIMIT = 10

REQUEST_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class MarketplaceResult:
    """Scan outcome: items plus an honest warning when degraded."""

    object: str
    kind: str
    topics: tuple[str, ...]
    items: tuple[dict, ...]
    warnings: tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "object": self.object,
            "kind": self.kind,
            "topics": list(self.topics),
            "external": True,  # community content — UI must label it
            "items": list(self.items),
            "warnings": list(self.warnings),
        }


def github_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "open-swarm-marketplace-scan",
    }
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def public_item_name(row: dict) -> str:
    """Display name for a GitHub scan row (never a secret)."""
    return str(row.get("name") or row.get("full_name") or "").strip()


def _normalize_item(repo: dict) -> dict:
    """Project a GitHub repo object onto the stable public shape."""
    owner = repo.get("owner") or {}
    return {
        "id": f"{repo.get('full_name', '')}",
        "name": repo.get("name", ""),
        "full_name": repo.get("full_name", ""),
        "owner": owner.get("login", ""),
        "description": repo.get("description") or "",
        "html_url": repo.get("html_url", ""),
        "stars": repo.get("stargazers_count", 0),
        "topics": list(repo.get("topics") or []),
        "updated_at": repo.get("updated_at") or "",
    }


def _sort_key(item: dict):
    return (-item["stars"], item["full_name"].lower())


def scan_marketplace(
    kind: str,
    fetch_json=None,
) -> dict:
    """Scan GitHub for ``kind='teams' | 'plugins'`` by topic tags.

    ``fetch_json`` is injectable for tests:
    ``(url, headers, params) -> (status, payload)``. It defaults to a
    ``urllib`` implementation so the scan works without extra deps.
    """
    topics = MARKETPLACE_TOPICS_TEAMS if kind == "teams" else MARKETPLACE_TOPICS_PLUGINS
    if kind not in ("teams", "plugins"):
        return MarketplaceResult(
            object="marketplace_scan", kind=kind, topics=(), items=(),
            warnings=("Unknown marketplace kind.",),
        ).as_dict()

    fetch = fetch_json or _fetch_json_urllib

    items: dict[str, dict] = {}
    warnings: list[str] = []
    for topic in topics:
        try:
            status_code, payload = fetch(
                GITHUB_SEARCH_URL,
                github_headers(),
                {
                    "q": f"topic:{topic}",
                    "sort": "stars",
                    "order": "desc",
                    "per_page": str(PER_TOPIC_LIMIT),
                },
            )
        except Exception as exc:  # network error, DNS, timeout — honest degrade
            logger.warning("Marketplace scan failed for topic %s: %s", topic, exc)
            warnings.append(f"GitHub search for '{topic}' failed: {exc.__class__.__name__}.")
            continue
        if status_code == 403 and "rate limit" in str(payload).lower():
            warnings.append("GitHub rate limit reached — try again later or set GITHUB_TOKEN.")
            continue
        if status_code != 200 or not isinstance(payload, dict):
            warnings.append(f"GitHub search for '{topic}' returned HTTP {status_code}.")
            continue
        for repo in payload.get("items") or []:
            if not isinstance(repo, dict) or not repo.get("full_name"):
                continue
            normalized = _normalize_item(repo)
            items[normalized["id"]] = normalized  # de-dupe across topics

    if not items and not warnings:
        warnings.append("No community packages found for these tags yet.")

    ordered = sorted(items.values(), key=_sort_key)[: PER_TOPIC_LIMIT * len(topics)]
    return MarketplaceResult(
        object="marketplace_scan",
        kind=kind,
        topics=topics,
        items=tuple(ordered),
        warnings=tuple(warnings),
    ).as_dict()


def fetch_json_urllib(url: str, headers: dict, params: dict | None = None):
    """Default transport: stdlib urllib. Returns ``(status, payload)`` on HTTP errors too."""
    import json as _json
    import urllib.error
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(params or {})
    target = f"{url}?{query}" if query else url
    request = urllib.request.Request(target, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
            return response.status, _json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            payload = _json.loads(body) if body else {"message": str(exc)}
        except _json.JSONDecodeError:
            payload = {"message": body or str(exc)}
        return int(exc.code), payload


def _fetch_json_urllib(url: str, headers: dict, params: dict):
    return fetch_json_urllib(url, headers, params)

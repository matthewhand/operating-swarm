"""Auto-detect a local Operating Swarm instance.

Probes ``http://127.0.0.1:8002`` plus a few common alternative ports, and
honours :data:`ENV_OVERRIDE` (``SWARM_SYSTRAY_BASE_URL``) as the first
candidate. The first base URL whose ``/v1/agents/`` answers is returned.

"Answers" means the endpoint exists: an unauthenticated ``401/403`` still
proves an OS instance is listening (``requires_auth=True``), while a timeout,
connection refusal, or ``404`` does not. When nothing answers the result
degrades honestly to ``base_url=None``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

DEFAULT_HOST = "127.0.0.1"
# 8002 is the documented local admin API; the rest are common alternates.
DEFAULT_PORTS: tuple[int, ...] = (8002, 8000, 8080, 8001, 3000)
ENV_OVERRIDE = "SWARM_SYSTRAY_BASE_URL"
DEFAULT_TIMEOUT = 3.0

Prober = Callable[[str, float], "ProbeResult"]


@dataclass(frozen=True)
class ProbeResult:
    """One candidate's answer to ``/v1/agents/``."""

    reachable: bool
    requires_auth: bool = False
    detail: str = ""


@dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of an auto-detect sweep."""

    base_url: str | None
    requires_auth: bool = False
    tried: tuple[str, ...] = ()
    detail: str = ""

    def __bool__(self) -> bool:
        return self.base_url is not None


def candidate_urls(env: Mapping[str, str] | None = None) -> list[str]:
    """Ordered probe list: env override first, then the common local ports."""
    source = os.environ if env is None else env
    override = str(source.get(ENV_OVERRIDE) or "").strip().rstrip("/")
    urls: list[str] = []
    if override:
        urls.append(override)
    for port in DEFAULT_PORTS:
        urls.append(f"http://{DEFAULT_HOST}:{port}")
    # Preserve order while removing duplicates (e.g. override == a default).
    seen: set[str] = set()
    return [url for url in urls if not (url in seen or seen.add(url))]


def _default_prober(url: str, timeout: float) -> ProbeResult:
    try:
        response = httpx.get(
            f"{url}/v1/agents/",
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )
    except httpx.HTTPError as exc:
        return ProbeResult(False, detail=type(exc).__name__)
    if response.status_code == 200:
        return ProbeResult(True)
    if response.status_code in (401, 403):
        return ProbeResult(True, requires_auth=True, detail=f"http {response.status_code}")
    return ProbeResult(False, detail=f"http {response.status_code}")


def discover(
    *,
    env: Mapping[str, str] | None = None,
    prober: Prober | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    extra_urls: list[str] | None = None,
) -> DiscoveryResult:
    """Return the first reachable OS base URL, or an honest ``None``.

    ``prober`` is injectable so this can be unit-tested without any network.
    """
    probe = prober or _default_prober
    urls = candidate_urls(env)
    if extra_urls:
        urls.extend(url.rstrip("/") for url in extra_urls)
    tried: list[str] = []
    for url in urls:
        tried.append(url)
        try:
            result = probe(url, timeout)
        except Exception:  # noqa: BLE001 — a broken probe is a failed candidate
            continue
        if result.reachable:
            return DiscoveryResult(url, result.requires_auth, tuple(tried), result.detail)
    return DiscoveryResult(None, False, tuple(tried), "no local Operating Swarm answered")

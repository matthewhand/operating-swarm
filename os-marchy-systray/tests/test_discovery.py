"""Auto-detection tests — injectable prober, no live network."""

from __future__ import annotations

from os_marchy_systray.discovery import (
    DEFAULT_PORTS,
    ENV_OVERRIDE,
    ProbeResult,
    candidate_urls,
    discover,
)


def test_candidate_urls_default_order():
    urls = candidate_urls({})
    assert urls[0] == "http://127.0.0.1:8002"
    assert len(urls) == len(DEFAULT_PORTS)
    assert urls == [f"http://127.0.0.1:{port}" for port in DEFAULT_PORTS]


def test_env_override_is_first():
    urls = candidate_urls({ENV_OVERRIDE: "http://swarm.lan:9000/"})
    assert urls[0] == "http://swarm.lan:9000"
    assert "http://127.0.0.1:8002" in urls


def test_discover_picks_first_responding_probe():
    seen: list[str] = []

    def prober(url: str, timeout: float) -> ProbeResult:
        seen.append(url)
        if url == "http://127.0.0.1:8000":
            return ProbeResult(True)
        return ProbeResult(False, detail="refused")

    result = discover(env={}, prober=prober)
    assert result.base_url == "http://127.0.0.1:8000"
    assert result.requires_auth is False
    # 8002 was probed first, then 8000 answered; later ports were never tried.
    assert seen == ["http://127.0.0.1:8002", "http://127.0.0.1:8000"]


def test_discover_accepts_auth_challenge_as_answer():
    def prober(url: str, timeout: float) -> ProbeResult:
        if url == "http://127.0.0.1:8002":
            return ProbeResult(True, requires_auth=True, detail="http 401")
        return ProbeResult(False)

    result = discover(env={}, prober=prober)
    assert result.base_url == "http://127.0.0.1:8002"
    assert result.requires_auth is True


def test_discover_env_override_wins_even_if_later():
    def prober(url: str, timeout: float) -> ProbeResult:
        return ProbeResult(url == "http://swarm.lan:9000")

    result = discover(env={ENV_OVERRIDE: "http://swarm.lan:9000"}, prober=prober)
    assert result.base_url == "http://swarm.lan:9000"
    assert result.tried[0] == "http://swarm.lan:9000"


def test_discover_degrades_honestly_when_none_respond():
    def prober(url: str, timeout: float) -> ProbeResult:
        return ProbeResult(False, detail="refused")

    result = discover(env={}, prober=prober)
    assert result.base_url is None
    assert bool(result) is False
    assert result.requires_auth is False
    assert set(result.tried) == set(candidate_urls({}))
    assert "no local" in result.detail


def test_discover_swallows_a_broken_probe():
    def prober(url: str, timeout: float) -> ProbeResult:
        if url == "http://127.0.0.1:8002":
            raise RuntimeError("probe exploded")
        return ProbeResult(True)

    result = discover(env={}, prober=prober)
    assert result.base_url == "http://127.0.0.1:8000"

"""#1327 — optional Composio catalog source: partial results + stall reasons.

Hermetic: no live Composio host, no secrets. Exercises the shared classifier
and the partial/last-good semantics.
"""

from __future__ import annotations

import json

import pytest

from swarm.core import catalog_fetch
from swarm.core import composio_catalog as composio
from swarm.core import marketplace_catalog as catalog


def _toolkit(slug: str, name: str | None = None, tools: int = 3):
    return {
        "slug": slug,
        "name": name or slug.title(),
        "description": f"{name or slug} connector.",
        "tools_count": tools,
    }


def test_classifier_distinguishes_stall_reasons():
    import socket
    import ssl

    assert catalog_fetch.classify_fetch_exception(TimeoutError("read timed out")) == "timeout"
    assert catalog_fetch.classify_fetch_exception(socket.gaierror("Name or service not known")) == "dns"
    assert catalog_fetch.classify_fetch_exception(ssl.SSLError("bad handshake")) == "tls"
    assert catalog_fetch.classify_fetch_exception(ConnectionRefusedError("nope")) == "offline"
    assert catalog_fetch.classify_fetch_status(429) == "rate_limit"
    assert catalog_fetch.classify_fetch_status(503) == "http_503"
    assert catalog_fetch.classify_fetch_status(200) is None


def test_spec_never_contains_secret_and_is_remote():
    spec = composio.plugin_spec_from_toolkit(_toolkit("gmail"))
    assert spec is not None
    assert spec["kind"] == "remote"
    assert spec["url"] == "https://mcp.composio.dev/gmail"
    assert spec["name"] == "composio-gmail"
    item = composio.normalize_composio_item(_toolkit("gmail", tools=61))
    assert item["id"] == "composio:gmail"
    assert item["source"] == "composio"
    assert item["tool_count"] == 61
    assert item["required_env"] == []
    assert "sk-" not in json.dumps(item)


def test_timeout_returns_partial_pages_and_stalled_reason(tmp_path):
    def fetch(url, headers, params):
        if not params.get("cursor"):
            return 200, {"items": [_toolkit("gmail")], "next_cursor": "page-2"}
        raise TimeoutError("read timed out")

    result = composio.fetch_composio_servers(
        fetch_json=fetch,
        cache_file=tmp_path / "composio.json",
        now=10.0,
        ttl=1.0,
        enabled=True,
        api_key="test-key",
    )
    ids = [row["id"] for row in result["items"]]
    assert ids == ["composio:gmail"]
    assert result["stalled_reason"] == "timeout"
    assert any("timeout" in w.lower() for w in result["warnings"])


def test_rate_limit_uses_last_good_cache(tmp_path):
    cache = tmp_path / "composio.json"
    item = composio.normalize_composio_item(_toolkit("slack"))
    cache.write_text(
        json.dumps({"object": "composio_catalog", "fetched_at": 1.0, "items": [item]}),
        encoding="utf-8",
    )

    def limited(*_a):
        return 429, {"message": "rate limit"}

    result = composio.fetch_composio_servers(
        fetch_json=limited,
        cache_file=cache,
        now=10_000.0,
        ttl=1.0,
        enabled=True,
        api_key="test-key",
    )
    assert result["items"][0]["id"] == "composio:slack"
    assert result["cached"] is True
    assert result["stalled_reason"] == "rate_limit"
    assert any("last-good" in w.lower() for w in result["warnings"])


def test_fresh_cache_is_reused_without_fetch(tmp_path):
    cache = tmp_path / "composio.json"
    item = composio.normalize_composio_item(_toolkit("notion"))
    cache.write_text(
        json.dumps({"object": "composio_catalog", "fetched_at": 1_000.0, "items": [item]}),
        encoding="utf-8",
    )

    def boom(*_a):
        raise AssertionError("must not hit Composio on a fresh cache")

    result = composio.fetch_composio_servers(
        fetch_json=boom,
        cache_file=cache,
        now=1_000.0 + 60,
        ttl=3600,
        enabled=True,
        api_key="test-key",
    )
    assert result["cached"] is True
    assert result["stalled_reason"] is None
    assert result["items"][0]["id"] == "composio:notion"


def test_disabled_source_is_honest_and_never_fetches(tmp_path):
    def boom(*_a):
        raise AssertionError("disabled source must not fetch")

    result = composio.fetch_composio_servers(
        fetch_json=boom,
        cache_file=tmp_path / "composio.json",
        enabled=False,
    )
    assert result["items"] == []
    assert result["stalled_reason"] == "not_configured"
    assert any("not configured" in w.lower() for w in result["warnings"])


def test_enabled_without_api_key_is_not_configured(tmp_path):
    def boom(*_a):
        raise AssertionError("no key -> must not fetch")

    result = composio.fetch_composio_servers(
        fetch_json=boom,
        cache_file=tmp_path / "composio.json",
        enabled=True,
        api_key="",
    )
    assert result["items"] == []
    assert result["stalled_reason"] == "not_configured"


def test_catalog_plugins_merges_composio_and_dedupes(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog.mcp_plugins, "load_mcp_servers", lambda: {})
    monkeypatch.setenv("COMPOSIO_API_KEY", "test-key")

    def fetch(url, headers, params):
        if "registry.modelcontextprotocol.io" in url:
            return 200, {
                "servers": [
                    {
                        "server": {
                            "name": "io.example/fetch",
                            "title": "Fetch",
                            "packages": [
                                {
                                    "registryType": "npm",
                                    "identifier": "@ex/fetch",
                                    "runtimeHint": "npx",
                                }
                            ],
                        }
                    }
                ],
                "metadata": {},
            }
        if "api.github.com/search/repositories" in url:
            return 200, {"items": []}
        raise OSError(url)

    def composio_fetch(url, headers, params):
        assert url == composio.COMPOSIO_TOOLKITS_URL
        assert headers.get("x-api-key") == "test-key"
        return 200, {"items": [_toolkit("gmail"), _toolkit("slack")]}

    result = catalog.catalog_plugins(
        fetch_json=fetch,
        cache_file=tmp_path / "reg.json",
        now=1.0,
        ttl=1.0,
        composio_enabled=True,
        composio_fetch_json=composio_fetch,
        composio_cache_file=tmp_path / "composio.json",
    )
    ids = [row["id"] for row in result["items"]]
    assert "mcp:io.example/fetch" in ids
    assert "composio:gmail" in ids
    assert "composio:slack" in ids
    assert "composio" in result["sources"]
    composio_status = next(s for s in result["source_status"] if s["source"] == "composio")
    assert composio_status["enabled"] is True
    assert composio_status["stalled_reason"] is None
    assert composio_status["item_count"] == 2
    assert "sk-" not in json.dumps(result)


def test_catalog_plugins_disabled_leaves_other_sources_untouched(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog.mcp_plugins, "load_mcp_servers", lambda: {})

    def fetch(url, headers, params):
        if "registry.modelcontextprotocol.io" in url:
            return 200, {
                "servers": [
                    {
                        "server": {
                            "name": "io.example/fetch",
                            "title": "Fetch",
                            "packages": [
                                {
                                    "registryType": "npm",
                                    "identifier": "@ex/fetch",
                                    "runtimeHint": "npx",
                                }
                            ],
                        }
                    }
                ],
                "metadata": {},
            }
        if "api.github.com/search/repositories" in url:
            return 200, {"items": []}
        raise OSError(url)

    result = catalog.catalog_plugins(
        fetch_json=fetch,
        cache_file=tmp_path / "reg.json",
        now=1.0,
        ttl=1.0,
        composio_enabled=False,
    )
    ids = [row["id"] for row in result["items"]]
    assert "mcp:io.example/fetch" in ids
    assert not any(i.startswith("composio:") for i in ids)
    assert "composio" not in result["sources"]
    composio_status = next(s for s in result["source_status"] if s["source"] == "composio")
    assert composio_status["enabled"] is False
    assert composio_status["stalled_reason"] == "not_configured"
    # A disabled optional source must not look like a top-level outage.
    assert result["stalled_reason"] is None

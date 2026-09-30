"""#1327 — Official MCP Registry reports classified stall reasons and partial pages."""

from __future__ import annotations

from swarm.core import mcp_registry


def _entry(name: str = "io.example/fetch"):
    return {
        "server": {
            "name": name,
            "title": "Fetch",
            "packages": [
                {"registryType": "npm", "identifier": "@ex/fetch", "runtimeHint": "npx"}
            ],
        }
    }


def test_mid_page_timeout_keeps_partial_items_and_reports_timeout(tmp_path):
    def fetch(url, headers, params):
        if not params.get("cursor"):
            return 200, {"servers": [_entry()], "metadata": {"nextCursor": "page-2"}}
        raise TimeoutError("read timed out")

    result = mcp_registry.fetch_registry_servers(
        fetch_json=fetch,
        cache_file=tmp_path / "reg.json",
        now=10.0,
        ttl=1.0,
    )
    assert [row["id"] for row in result["items"]] == ["mcp:io.example/fetch"]
    assert result["stalled_reason"] == "timeout"
    # Back-compat warning string is preserved (with the classified reason appended).
    assert any("request failed" in w and "timeout" in w.lower() for w in result["warnings"])


def test_rate_limit_reports_rate_limit_and_uses_cache(tmp_path):
    import json

    cache = tmp_path / "reg.json"
    item = mcp_registry.normalize_registry_item(_entry())
    cache.write_text(
        json.dumps({"object": "mcp_registry_cache", "fetched_at": 1.0, "items": [item]}),
        encoding="utf-8",
    )

    def limited(*_a):
        return 429, {"message": "rate limit"}

    result = mcp_registry.fetch_registry_servers(
        fetch_json=limited,
        cache_file=cache,
        now=10_000.0,
        ttl=1.0,
    )
    assert result["items"]
    assert result["cached"] is True
    assert result["stalled_reason"] == "rate_limit"


def test_offline_classified_as_offline(tmp_path):
    def offline(*_a):
        raise OSError("offline")

    result = mcp_registry.fetch_registry_servers(
        fetch_json=offline,
        cache_file=tmp_path / "reg.json",
        now=10.0,
        ttl=1.0,
    )
    assert result["items"] == []
    assert result["stalled_reason"] == "offline"

"""REQ-887 — Official MCP Registry cached client. No live registry. No secrets."""

from __future__ import annotations

import json

from swarm.core import mcp_registry


def _server_entry(*, name="io.example/fetch", with_secret_desc=False, remote=False):
    desc = "Fetch URLs over HTTP."
    if with_secret_desc:
        desc = "token sk-live-secret-value"
    server = {
        "name": name,
        "title": "Fetch",
        "description": desc,
        "version": "1.2.3",
        "repository": {"url": "https://github.com/example/fetch"},
    }
    if remote:
        server["remotes"] = [{"type": "streamable-http", "url": "https://example.invalid/mcp"}]
    else:
        server["packages"] = [
            {
                "registryType": "npm",
                "identifier": "@ex/fetch",
                "runtimeHint": "npx",
                "runtimeArguments": [{"value": "-y", "type": "positional"}],
                "environmentVariables": [
                    {"name": "FETCH_TOKEN", "isRequired": True, "isSecret": True, "value": "sk-live"},
                    {"name": "not valid", "isRequired": True},
                ],
            }
        ]
    return {
        "server": server,
        "_meta": {"io.modelcontextprotocol.registry/official": {"status": "active", "isLatest": True}},
    }


def test_plugin_spec_uses_env_placeholders_never_secret_values():
    spec = mcp_registry.plugin_spec_from_server(_server_entry()["server"])
    assert spec is not None
    assert spec["command"] == "npx"
    assert spec["args"] == ["-y", "@ex/fetch"]
    assert spec["env"] == {"FETCH_TOKEN": "${FETCH_TOKEN}"}
    dumped = json.dumps(spec)
    assert "sk-live" not in dumped
    assert mcp_registry.required_env_names(spec) == ["FETCH_TOKEN"]


def test_remote_server_maps_to_url_kind():
    spec = mcp_registry.plugin_spec_from_server(_server_entry(remote=True)["server"])
    assert spec["kind"] == "remote"
    assert spec["url"] == "https://example.invalid/mcp"


def test_secret_shaped_description_is_stripped_from_listings():
    item = mcp_registry.normalize_registry_item(_server_entry(with_secret_desc=True))
    assert item is not None
    assert item["summary"] == ""
    assert "sk-live" not in json.dumps(item)


def test_fresh_cache_is_reused_without_fetch(tmp_path):
    cache = tmp_path / "mcp_registry.json"
    item = mcp_registry.normalize_registry_item(_server_entry())
    cache.write_text(
        json.dumps({"object": "mcp_registry_cache", "fetched_at": 1_000.0, "items": [item]}),
        encoding="utf-8",
    )
    calls = []

    def boom(*_a):
        calls.append(1)
        raise AssertionError("must not hit the registry on a fresh cache")

    result = mcp_registry.fetch_registry_servers(
        fetch_json=boom,
        cache_file=cache,
        now=1_000.0 + 60,
        ttl=3600,
    )
    assert result["cached"] is True
    assert result["items"][0]["id"] == "mcp:io.example/fetch"
    assert calls == []


def test_offline_falls_back_to_last_good_cache(tmp_path):
    cache = tmp_path / "mcp_registry.json"
    item = mcp_registry.normalize_registry_item(_server_entry())
    cache.write_text(
        json.dumps({"object": "mcp_registry_cache", "fetched_at": 1.0, "items": [item]}),
        encoding="utf-8",
    )

    def offline(*_a):
        raise OSError("offline")

    result = mcp_registry.fetch_registry_servers(
        fetch_json=offline,
        cache_file=cache,
        now=10_000.0,
        ttl=1.0,
    )
    assert result["items"][0]["id"] == "mcp:io.example/fetch"
    assert result["cached"] is True
    assert any("last-good" in w.lower() or "failed" in w.lower() for w in result["warnings"])


def test_rate_limit_is_honest_and_uses_cache(tmp_path):
    cache = tmp_path / "mcp_registry.json"
    item = mcp_registry.normalize_registry_item(_server_entry())
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
    assert any("rate limit" in w.lower() for w in result["warnings"])


def test_poll_writes_cache(tmp_path):
    cache = tmp_path / "mcp_registry.json"

    def ok(url, headers, params):
        assert "registry.modelcontextprotocol.io" in url
        assert params.get("version") == "latest"
        return 200, {"servers": [_server_entry()], "metadata": {"count": 1}}

    result = mcp_registry.fetch_registry_servers(
        fetch_json=ok,
        cache_file=cache,
        now=50.0,
        ttl=1.0,
    )
    assert result["cached"] is False
    assert cache.is_file()
    stored = json.loads(cache.read_text(encoding="utf-8"))
    assert stored["items"][0]["plugin"]["env"] == {"FETCH_TOKEN": "${FETCH_TOKEN}"}
    assert "sk-live" not in cache.read_text(encoding="utf-8")

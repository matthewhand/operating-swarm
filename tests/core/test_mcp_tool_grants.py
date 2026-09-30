"""#1313 persistent per-bot MCP / connector tool grants."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core import agent_settings as settings_store
from swarm.core.agent_mcp import (
    McpAccessError,
    catalog_tools,
    execute_tool,
    inspect_tool,
    register_mcp,
)
from swarm.core.mcp_tool_grants import (
    McpToolGrantError,
    filter_catalog_rows,
    grants_active,
    intersect_with_grants,
    normalize_mcp_tool_grants,
    resolve_enabled_tools,
    tool_is_granted,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    settings_store.reset_agent_settings_cache()
    from swarm.core import agent_mcp as mcp_store

    mcp_store.reset_agent_mcp_cache()
    yield
    settings_store.reset_agent_settings_cache()
    mcp_store.reset_agent_mcp_cache()


def _config():
    return {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [
                    {"name": "web_fetch", "description": "Fetch a URL"},
                    {"name": "web_search", "description": "Search"},
                ],
            }
        }
    }


def test_normalize_accepts_list_and_csv():
    assert normalize_mcp_tool_grants([" web_search ", "web_fetch", "web_search"]) == [
        "web_search",
        "web_fetch",
    ]
    assert normalize_mcp_tool_grants("web_search, web_fetch") == ["web_search", "web_fetch"]
    assert normalize_mcp_tool_grants(None) == []
    assert grants_active([]) is False
    assert grants_active(["web_search"]) is True


def test_normalize_rejects_malformed():
    with pytest.raises(McpToolGrantError, match="list of tool names"):
        normalize_mcp_tool_grants({"web_search": True})
    with pytest.raises(McpToolGrantError, match="strings"):
        normalize_mcp_tool_grants([1])


def test_intersect_cannot_widen_grants():
    assert intersect_with_grants(["web_search", "leak"], ["web_search"]) == ["web_search"]
    assert intersect_with_grants(["leak"], ["web_search"]) == []


def test_resolve_inactive_without_turn_list():
    assert resolve_enabled_tools("worker") is None
    assert resolve_enabled_tools("worker", {}) is None


def test_resolve_turn_list_when_no_grants():
    assert resolve_enabled_tools("worker", {"enabled_tools": ["web_search"]}) == ["web_search"]
    assert resolve_enabled_tools("worker", {"enabled_tools": []}) == []


def test_malformed_turn_list_cannot_skip_enforcement():
    """Non-strings used to raise. The HTTP chat path swallows that and attaches every tool."""
    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    resolved = resolve_enabled_tools(
        "worker",
        {"enabled_tools": [1, {"name": "web_fetch"}, "web_fetch", "web_search", "x" * 500]},
    )
    assert resolved == ["web_search"]
    assert resolve_enabled_tools("worker", {"enabled_tools": [1, " web_search "]}) == ["web_search"]


def test_explicit_empty_grants_are_deny_all():
    settings_store.set_mcp_tool_grants("worker", [])
    assert settings_store.get_settings("worker")["mcp_tool_grants_set"] is True
    assert resolve_enabled_tools("worker") == []
    assert resolve_enabled_tools("worker", {"enabled_tools": ["web_search", "leak"]}) == []
    assert tool_is_granted("worker", "web_search") is False
    rows = [{"name": "web_search", "server": "fetch"}]
    assert filter_catalog_rows(rows, "worker") == []
    # A bot that never saved a list stays inactive.
    assert resolve_enabled_tools("other") is None
    assert tool_is_granted("other", "web_search") is True
    # An injected empty override is deny-all, same as a saved [].
    assert resolve_enabled_tools("other", {"enabled_tools": ["web_search"]}, grants=[]) == []
    assert resolve_enabled_tools("other", grants=["web_search"]) == ["web_search"]


def test_resolve_persisted_grants_without_turn_list():
    settings_store.set_mcp_tool_grants("worker", ["web_search", "web_fetch"])
    settings_store.reset_agent_settings_cache()
    assert resolve_enabled_tools("worker") == ["web_search", "web_fetch"]
    # Per-bot isolation.
    assert resolve_enabled_tools("other") is None


def test_resolve_intersects_turn_list_with_grants():
    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    assert resolve_enabled_tools(
        "worker", {"enabled_tools": ["web_search", "web_fetch", "leak"]}
    ) == ["web_search"]


def test_tool_is_granted_inactive_allows():
    assert tool_is_granted("worker", "anything") is True
    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    assert tool_is_granted("worker", "web_search") is True
    assert tool_is_granted("worker", "web_fetch") is False


def test_filter_catalog_rows_honours_grants():
    rows = [
        {"name": "web_search", "server": "fetch"},
        {"name": "web_fetch", "server": "fetch"},
    ]
    assert [row["name"] for row in filter_catalog_rows(rows, "nobody")] == [
        "web_search",
        "web_fetch",
    ]
    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    assert [row["name"] for row in filter_catalog_rows(rows, "worker")] == ["web_search"]


def test_settings_roundtrip_and_isolation():
    settings_store.set_mcp_tool_grants("worker", ["web_search", "web_fetch"])
    settings_store.reset_agent_settings_cache()
    assert settings_store.get_mcp_tool_grants("worker") == ["web_search", "web_fetch"]
    assert settings_store.get_mcp_tool_grants("other") == []


def test_settings_rejects_malformed_grants():
    with pytest.raises(ValueError, match="mcp_tool_grants"):
        settings_store.update_settings("worker", {"mcp_tool_grants": {"web_search": True}})


def test_agent_mcp_catalog_and_execute_honour_grants():
    register_mcp("worker", mode="all")
    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    names = {row["name"] for row in catalog_tools("worker", config=_config())}
    assert names == {"web_search"}

    inspect_tool("worker", "web_search", config=_config())
    with pytest.raises(McpAccessError):
        inspect_tool("worker", "web_fetch", config=_config())

    def fake_execute(name, spec, arguments):
        return {"ok": True, "name": name}

    result = execute_tool(
        "worker",
        "web_search",
        {},
        config=_config(),
        execute_fn=fake_execute,
    )
    assert result["ok"] is True
    with pytest.raises(McpAccessError):
        execute_tool("worker", "web_fetch", {}, config=_config(), execute_fn=fake_execute)


def test_plugin_runtime_uses_persisted_grants():
    from swarm.core.mcp_plugins import apply_plugin_mcp_runtime

    settings_store.set_mcp_tool_grants("worker", ["web_search"])
    enabled = resolve_enabled_tools("worker")
    assert enabled == ["web_search"]

    agent = SimpleNamespace(functions=[SimpleNamespace(name="web_search"), SimpleNamespace(name="web_fetch")])
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    apply_plugin_mcp_runtime(blueprint, _config(), enabled)
    assert [fn.name for fn in agent.functions] == ["web_search"]

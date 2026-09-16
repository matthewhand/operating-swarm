"""MCP modes for API managed agents (#142). No live MCP hosts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core import agent_mcp as store
from swarm.core.agent_mcp import (
    EXECUTE_TOOL,
    INSPECT_TOOL,
    LIST_TOOL,
    MODE_ALL,
    MODE_OFF,
    MODE_PROGRESSIVE,
    McpAccessError,
    apply_mcp_to_agent,
    catalog_tools,
    execute_tool,
    get_mcp,
    inspect_tool,
    install_mcp_for_runtime,
    list_tools,
    mcp_fields_from_raw,
    normalize_mcp_mode,
    register_mcp,
    update_mcp,
)
from swarm.core.router_designs import upsert_design, validate_design


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    store.reset_agent_mcp_cache()
    yield
    store.reset_agent_mcp_cache()


def _config():
    return {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [
                    {
                        "name": "web_fetch",
                        "description": "Fetch a URL",
                        "input_schema": {
                            "type": "object",
                            "properties": {"url": {"type": "string"}},
                            "required": ["url"],
                        },
                    }
                ],
            },
            "time": {
                "command": "uvx",
                "args": ["mcp-server-time"],
                "discovered_tools": [{"name": "get_current_time", "description": "Now"}],
            },
            "secret": {
                "command": "uvx",
                "args": ["mcp-server-secret"],
                "enabled": False,
                "discovered_tools": [{"name": "leak", "description": "nope"}],
            },
        }
    }


def test_normalize_mcp_mode_aliases():
    assert normalize_mcp_mode("all_mcp") == MODE_ALL
    assert normalize_mcp_mode("progressive") == MODE_PROGRESSIVE
    assert normalize_mcp_mode(None) == MODE_OFF
    with pytest.raises(ValueError, match="mcp_mode"):
        normalize_mcp_mode("yolo")


def test_mcp_fields_rejected_on_cli_and_remote():
    with pytest.raises(ValueError, match="API managed"):
        mcp_fields_from_raw({"mcp_mode": "all"}, kind="cli")
    with pytest.raises(ValueError, match="API managed"):
        mcp_fields_from_raw({"mcp_mode": "progressive"}, kind="remote")
    assert mcp_fields_from_raw({"mcp_mode": "all"}, kind="personality")["mcp_mode"] == MODE_ALL


def test_register_persists_across_cache_reset(tmp_path, monkeypatch):
    register_mcp("night-editor", mode="all", mcp_servers=["fetch"])
    store.reset_agent_mcp_cache()
    mcp = get_mcp("night-editor")
    assert mcp["mode"] == MODE_ALL
    assert mcp["mcp_servers"] == ["fetch"]
    assert mcp["enabled"] is True
    assert (tmp_path / "agent_mcp.json").is_file()


def test_mode_switch_roundtrip():
    register_mcp("worker", mode="all")
    updated = update_mcp("worker", {"mcp_mode": "progressive"})
    assert updated["mode"] == MODE_PROGRESSIVE
    assert get_mcp("worker")["mode"] == MODE_PROGRESSIVE


def test_all_mode_lists_enabled_tools_not_disabled():
    register_mcp("worker", mode="all")
    names = {row["name"] for row in list_tools("worker", config=_config())}
    assert names == {"web_fetch", "get_current_time"}
    assert "leak" not in names


def test_server_allowlist_filters_catalog():
    register_mcp("worker", mode="all", mcp_servers=["fetch"])
    rows = catalog_tools("worker", config=_config())
    assert [row["name"] for row in rows] == ["web_fetch"]


def test_progressive_inspect_and_execute():
    register_mcp("worker", mode="progressive")
    details = inspect_tool("worker", "web_fetch", config=_config())
    assert details["name"] == "web_fetch"
    assert details["server"] == "fetch"
    assert details["parameters"]["required"] == ["url"]

    def fake_execute(name, spec, arguments):
        assert name == "web_fetch"
        assert arguments == {"url": "https://example.invalid"}
        return {"ok": True, "body": "hi"}

    result = execute_tool(
        "worker",
        "web_fetch",
        {"url": "https://example.invalid"},
        config=_config(),
        execute_fn=fake_execute,
    )
    assert result["ok"] is True
    assert result["result"]["body"] == "hi"


def test_unauthorized_when_mode_off():
    with pytest.raises(McpAccessError) as exc:
        list_tools("nobody", config=_config())
    assert exc.value.status == 403
    assert exc.value.code == "unauthorized"


def test_unauthorized_unknown_or_disabled_tool():
    register_mcp("worker", mode="all", mcp_servers=["fetch"])
    with pytest.raises(McpAccessError):
        inspect_tool("worker", "leak", config=_config())
    with pytest.raises(McpAccessError):
        inspect_tool("worker", "get_current_time", config=_config())


def test_all_mode_attaches_catalog_tools():
    register_mcp("worker", mode="all")
    agent = SimpleNamespace(functions=[], tools=[], mcp_servers=[])
    names = apply_mcp_to_agent(agent, "worker", config=_config())
    assert "web_fetch" in names
    assert "get_current_time" in names
    assert LIST_TOOL not in names
    attached = {getattr(fn, "name", "") for fn in agent.functions}
    assert "web_fetch" in attached


def test_progressive_mode_attaches_meta_tools_only():
    register_mcp("worker", mode="progressive")
    agent = SimpleNamespace(functions=[], tools=[], mcp_servers=[])
    names = apply_mcp_to_agent(agent, "worker", config=_config())
    assert set(names) == {LIST_TOOL, INSPECT_TOOL, EXECUTE_TOOL}
    listed = {getattr(fn, "name", "") for fn in agent.tools}
    assert "web_fetch" not in listed
    assert LIST_TOOL in listed


def test_mode_switch_replaces_tools():
    register_mcp("worker", mode="all")
    agent = SimpleNamespace(functions=[], tools=[], mcp_servers=[])
    apply_mcp_to_agent(agent, "worker", config=_config())
    update_mcp("worker", {"mcp_mode": "progressive"})
    apply_mcp_to_agent(agent, "worker", config=_config())
    names = {getattr(fn, "name", "") for fn in agent.functions}
    assert LIST_TOOL in names
    assert "web_fetch" not in names


def test_install_runtime_uses_caller_id():
    register_mcp("night-editor", mode="progressive")
    agent = SimpleNamespace(functions=[], tools=[], agent_id="night-editor")
    blueprint = SimpleNamespace(agents={"night-editor": agent}, config=_config())
    attached = install_mcp_for_runtime(blueprint, caller_id="night-editor", config=_config())
    assert LIST_TOOL in attached


def test_validate_design_accepts_mcp_mode():
    spec = validate_design({
        "kind": "api",
        "name": "Night Editor",
        "instructions": "Tighten prose.",
        "mcp_mode": "progressive",
        "mcp_servers": ["fetch"],
    })
    assert spec["mcp_mode"] == MODE_PROGRESSIVE
    assert spec["mcp_servers"] == ["fetch"]
    assert spec["agent_type"] == "api"


def test_upsert_design_registers_mcp(tmp_path, monkeypatch):
    spec = upsert_design({
        "kind": "personality",
        "name": "Night Editor",
        "instructions": "Tighten prose.",
        "mcp_mode": "all",
    })
    assert spec["mcp_mode"] == MODE_ALL
    assert get_mcp("night-editor")["mode"] == MODE_ALL

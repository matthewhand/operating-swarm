"""Persistent per-bot mcp_tools grants (#1313). No live MCP hosts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core.agent_mcp import (
    _allowed_tools,
    apply_mcp_to_agent,
    apply_turn_plugin_tools,
    get_mcp,
    install_mcp_for_runtime,
    normalize_mcp_tools,
    register_mcp,
    reset_agent_mcp_cache,
    update_mcp,
)
from swarm.core.mcp_plugins import apply_plugin_mcp_runtime


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    reset_agent_mcp_cache()
    from swarm.core import agent_settings as settings_store

    settings_store.reset_agent_settings_cache()
    yield
    reset_agent_mcp_cache()
    settings_store.reset_agent_settings_cache()


def _config():
    return {
        "mcpServers": {
            "serverA": {
                "command": "uvx",
                "args": ["mcp-server-a"],
                "discovered_tools": [
                    {"name": "tool1", "description": "one"},
                    {"name": "tool2", "description": "two"},
                ],
            },
            "serverB": {
                "command": "uvx",
                "args": ["mcp-server-b"],
                "discovered_tools": [{"name": "tool3", "description": "three"}],
            },
        }
    }


def _names(agent) -> list[str]:
    return sorted(
        {
            str(getattr(fn, "name", "") or "")
            for fn in list(getattr(agent, "functions", []) or [])
            if str(getattr(fn, "name", "") or "")
        }
    )


def _agent():
    return SimpleNamespace(functions=[], tools=[], mcp_servers=[])


def test_normalize_map_star_and_reject():
    assert normalize_mcp_tools(None) == {}
    assert normalize_mcp_tools({"serverA": [" tool1 ", "tool1", "tool2"]}) == {
        "serverA": ["tool1", "tool2"]
    }
    assert normalize_mcp_tools({"serverA": "*"}) == {"serverA": "*"}
    with pytest.raises(ValueError, match="mcp_tools"):
        normalize_mcp_tools(["tool1"])


def test_grant_persists_across_cache_reset():
    update_mcp("worker", {"mcp_mode": "all", "mcp_tools": {"serverA": ["tool1"]}})
    reset_agent_mcp_cache()
    assert get_mcp("worker")["mcp_tools"] == {"serverA": ["tool1"]}
    assert get_mcp("other")["mcp_tools"] == {}


def test_allowed_tools_resolution():
    omitted = {"mcp_tools": {}}
    assert _allowed_tools("serverA", omitted) is None
    star = {"mcp_tools": {"serverA": "*"}}
    assert _allowed_tools("serverA", star) is None
    assert _allowed_tools("serverB", star) == []
    listed = {"mcp_tools": {"serverA": ["tool1"]}}
    assert _allowed_tools("serverA", listed) == ["tool1"]


def test_grant_attaches_only_listed_tool_without_enabled_tools():
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1"]})
    agent = _agent()
    apply_mcp_to_agent(agent, "worker", config=_config())
    assert _names(agent) == ["tool1"]


def test_star_matches_server_select_and_omitted_map_uses_servers():
    register_mcp("select", mode="all", mcp_servers=["serverA"])
    selected = _agent()
    apply_mcp_to_agent(selected, "select", config=_config())

    register_mcp("star", mode="all", mcp_tools={"serverA": "*"})
    starred = _agent()
    apply_mcp_to_agent(starred, "star", config=_config())
    assert _names(selected) == _names(starred) == ["tool1", "tool2"]

    register_mcp("omit", mode="all", mcp_servers=["serverA"])
    assert get_mcp("omit")["mcp_tools"] == {}
    omitted = _agent()
    apply_mcp_to_agent(omitted, "omit", config=_config())
    assert _names(omitted) == ["tool1", "tool2"]


def test_removed_tool_is_detached_on_next_turn():
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1", "tool2"]})
    agent = _agent()
    apply_mcp_to_agent(agent, "worker", config=_config())
    assert _names(agent) == ["tool1", "tool2"]
    update_mcp("worker", {"mcp_tools": {"serverA": ["tool1"]}})
    apply_mcp_to_agent(agent, "worker", config=_config())
    assert _names(agent) == ["tool1"]


def _live_turn(agent_id: str, params: dict, agent, config: dict):
    """Same order as chat completions and the websocket stub."""
    blueprint = SimpleNamespace(
        agents={agent_id: agent},
        starting_agent=agent,
        config=config,
    )
    apply_turn_plugin_tools(blueprint, agent_id, params, config)
    install_mcp_for_runtime(
        blueprint,
        caller_id=agent_id,
        params=params,
        config=config,
    )
    return agent


def test_client_enabled_tools_cannot_widen_the_grant():
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1"]})
    agent = _agent()
    _live_turn("worker", {"enabled_tools": ["tool2"]}, agent, _config())
    assert _names(agent) == ["tool1"]


def test_live_turn_uses_mcp_tools_when_spa_sends_empty_enabled_tools():
    """The chat frame always used to send enabled_tools: [] and skip the map."""
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1"]})
    agent = _agent()
    _live_turn("worker", {"enabled_tools": []}, agent, _config())
    assert _names(agent) == ["tool1"]


def test_live_turn_without_enabled_tools_attaches_the_grant():
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1"]})
    agent = _agent()
    _live_turn("worker", {}, agent, _config())
    assert _names(agent) == ["tool1"]


def test_live_turn_star_ignores_narrow_client_list():
    register_mcp("star", mode="all", mcp_tools={"serverA": "*"})
    agent = _agent()
    _live_turn("star", {"enabled_tools": ["tool2"]}, agent, _config())
    assert _names(agent) == ["tool1", "tool2"]


def test_live_turn_omitted_map_keeps_server_level_tools():
    register_mcp("omit", mode="all", mcp_servers=["serverA"])
    assert get_mcp("omit")["mcp_tools"] == {}
    agent = _agent()
    _live_turn("omit", {"enabled_tools": ["tool2"]}, agent, _config())
    assert _names(agent) == ["tool1", "tool2"]


def test_live_turn_detaches_a_revoked_tool_without_restart():
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1", "tool2"]})
    agent = _agent()
    _live_turn("worker", {"enabled_tools": []}, agent, _config())
    assert _names(agent) == ["tool1", "tool2"]
    update_mcp("worker", {"mcp_tools": {"serverA": ["tool1"]}})
    _live_turn("worker", {"enabled_tools": ["tool1", "tool2"]}, agent, _config())
    assert _names(agent) == ["tool1"]


def test_cli_register_and_update_attach_the_same_tools():
    register_mcp("cli-bot", mode="all", mcp_tools={"serverA": ["tool1"]})
    update_mcp("api-bot", {"mcp_mode": "all", "mcp_tools": {"serverA": ["tool1"]}})
    cli_agent = _agent()
    api_agent = _agent()
    apply_mcp_to_agent(cli_agent, "cli-bot", config=_config())
    apply_mcp_to_agent(api_agent, "api-bot", config=_config())
    assert _names(cli_agent) == _names(api_agent) == ["tool1"]


def test_turn_list_cannot_bypass_explicit_empty_grants():
    """#1494 deny-all must hold when the client sends enabled_tools.

    grants_active([]) is false, so a turn list used to skip the policy and
    attach every named tool. The SPA sends enabled_tools on every send.
    """
    from swarm.core import agent_settings as settings_store

    settings_store.set_mcp_tool_grants("worker", [])
    agent = _agent()
    agent.functions.append(SimpleNamespace(name="web_search"))
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    apply_turn_plugin_tools(
        blueprint,
        "worker",
        {"enabled_tools": ["tool1", "tool2", "web_search"]},
        _config(),
    )
    assert _names(agent) == []


def test_empty_grants_beat_a_saved_mcp_tools_map():
    from swarm.core import agent_settings as settings_store

    settings_store.set_mcp_tool_grants("worker", [])
    register_mcp("worker", mode="all", mcp_tools={"serverA": ["tool1"]})
    agent = _agent()
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    apply_turn_plugin_tools(blueprint, "worker", None, _config())
    assert _names(agent) == []


def test_persistent_map_keeps_unrelated_fixture_tools():
    agent = _agent()
    agent.functions.append(SimpleNamespace(name="web_search"))
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    apply_plugin_mcp_runtime(
        blueprint,
        _config(),
        None,
        persistent_tools={"serverA": ["tool1"]},
    )
    assert _names(agent) == ["tool1", "web_search"]


def test_plugin_runtime_map_beats_a_turn_list():
    agent = _agent()
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    apply_plugin_mcp_runtime(
        blueprint,
        _config(),
        ["tool2"],
        persistent_tools={"serverA": ["tool1"]},
    )
    assert _names(agent) == ["tool1"]

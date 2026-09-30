"""#1406 — extra plugin/MCP tools persist on a routine and attach at run time."""

from __future__ import annotations

import asyncio

from swarm.core import routines as store
from swarm.core.routine_tools import (
    TOOL_OPEN_PULL_REQUEST,
    compose_routine_picker_catalog,
    plugin_ids_from_routine_tools,
    set_plugin_runtime_applier,
)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _interval_trigger():
    return {"kind": "interval", "seconds": 3600}


def test_add_plugin_tool_persists(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Search recap",
            "instruction": "Search then summarize.",
            "trigger": _interval_trigger(),
            "tools": ["web_search"],
        },
    )
    assert created["tools"] == ["web_search"]
    assert created["tools_explicit"] is True
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again["tools"] == ["web_search"]
    assert again["tools_explicit"] is True


def test_add_and_remove_plugin_tool(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Search recap",
            "instruction": "Search then summarize.",
            "trigger": _interval_trigger(),
            "tools": [TOOL_OPEN_PULL_REQUEST, "web_search", "git_status"],
        },
    )
    assert created["tools"] == [TOOL_OPEN_PULL_REQUEST, "web_search", "git_status"]
    updated = store.update_routine("codey", created["id"], {"tools": [TOOL_OPEN_PULL_REQUEST, "git_status"]})
    assert updated["tools"] == [TOOL_OPEN_PULL_REQUEST, "git_status"]
    assert "web_search" not in updated["tools"]
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again["tools"] == [TOOL_OPEN_PULL_REQUEST, "git_status"]


def test_memories_slug_passes_through_without_implementing_1404(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Notes",
            "instruction": "Remember.",
            "trigger": _interval_trigger(),
            "tools": ["memories", "web_search"],
        },
    )
    assert created["tools"] == ["memories", "web_search"]


def test_rejects_secret_looking_tool_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_routine(
            "codey",
            {
                "name": "Nope",
                "instruction": "x",
                "trigger": _interval_trigger(),
                "tools": ["sk-not-a-real-token"],
            },
        )
    except ValueError as exc:
        assert "secret" in str(exc).lower()
    else:
        raise AssertionError("expected ValueError")


def test_picker_catalog_reuses_plugin_ids_and_flags_disabled_auth(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    items = compose_routine_picker_catalog({})
    by_id = {row["id"]: row for row in items}
    assert "open_pull_request" in by_id
    assert by_id["open_pull_request"]["kind"] == "builtin"
    assert "web_search" in by_id
    assert by_id["web_search"]["available"] is True
    brave = by_id.get("brave_search")
    assert brave is not None
    assert brave["available"] is False
    assert "BRAVE_API_KEY" in brave["reason"]
    assert "Tokens stay out of this builder" in brave["reason"]
    assert "sk-" not in brave["reason"]
    blob = str(items)
    assert "ghp_" not in blob
    assert "github_pat_" not in blob


def test_picker_catalog_installed_server_missing_env_is_disabled():
    items = compose_routine_picker_catalog(
        {
            "mcpServers": {
                "acme": {
                    "command": "uvx",
                    "args": ["acme-mcp"],
                    "enabled": True,
                    "env": {"ACME_TOKEN": "${ACME_TOKEN}"},
                    "discovered_tools": [{"name": "acme_search", "description": "Search Acme"}],
                }
            }
        }
    )
    by_id = {row["id"]: row for row in items}
    row = by_id["acme_search"]
    assert row["available"] is False
    assert "ACME_TOKEN" in row["reason"]
    assert "${ACME_TOKEN}" not in row["reason"]
    assert "Tokens stay out of this builder" in row["reason"]


def test_discovered_tool_ids_keep_runtime_names():
    """Allowlist match is exact. ``web-search`` must not be stored as ``web_search``."""
    from swarm.core.routine_tools import normalize_routine_tools

    items = compose_routine_picker_catalog(
        {
            "mcpServers": {
                "custom": {
                    "command": "uvx",
                    "args": ["custom-mcp"],
                    "enabled": True,
                    "discovered_tools": [
                        {"name": "web-search", "description": "key ghp_notarealtokenhere"},
                    ],
                }
            }
        }
    )
    by_id = {row["id"]: row for row in items}
    assert "web-search" in by_id
    assert by_id["web-search"]["available"] is True
    assert "ghp_" not in by_id["web-search"]["description"]
    assert "ghp_" not in str(by_id["web-search"])
    assert normalize_routine_tools(["web-search", "Open-Pull-Request"]) == [
        "web-search",
        TOOL_OPEN_PULL_REQUEST,
    ]


def test_plugin_ids_exclude_builtins():
    assert plugin_ids_from_routine_tools(
        [TOOL_OPEN_PULL_REQUEST, "memories", "web_search"]
    ) == ["web_search"]


def test_run_path_attaches_plugin_tools(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    seen: list[list[str]] = []

    def _applier(blueprint, plugin_ids):
        del blueprint
        seen.append(list(plugin_ids))

    set_plugin_runtime_applier(_applier)

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            del messages, kwargs
            yield "ok"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del agent_id, params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    reply = asyncio.run(
        store.run_routine_agent_job(
            "codey",
            "Search then recap.",
            conversation_id="conv-1406-tools",
            tools=["web_search"],
        )
    )
    assert reply == "ok"
    assert seen == [["web_search"]]


def test_run_path_skips_plugin_attach_when_only_builtins(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    seen: list[list[str]] = []
    set_plugin_runtime_applier(lambda blueprint, ids: seen.append(list(ids)))

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            del messages, kwargs
            yield "ok"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del agent_id, params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    reply = asyncio.run(
        store.run_routine_agent_job(
            "codey",
            "Just recap.",
            conversation_id="conv-1406-none",
            tools=[TOOL_OPEN_PULL_REQUEST],
        )
    )
    assert reply.startswith("ok")
    assert seen == []

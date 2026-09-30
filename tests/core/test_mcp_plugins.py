"""#502 Plugins MCP manage — local/remote normalize, discover mocks, runtime."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core.mcp_plugins import (
    McpPluginError,
    OPENAPI_PROXY_ARGS,
    OPENAPI_PROXY_COMMAND,
    OPENAPI_SPEC_ENV,
    apply_plugin_mcp_runtime,
    attach_plugin_mcp_tools,
    enabled_mcp_servers,
    list_tools_for_spec,
    normalize_plugin_spec,
    plugin_catalog_ids,
    public_server,
)

MOCK_OPENAPI = {
    "openapi": "3.0.0",
    "info": {"title": "Pets", "version": "1.0.0"},
    "paths": {
        "/pets": {
            "get": {
                "operationId": "list_pets",
                "summary": "List pets",
            }
        },
        "/pets/{id}": {
            "get": {
                "operationId": "get_pet",
                "summary": "Get a pet",
            }
        },
    },
}


def _tools_from_mock_openapi(doc):
    """Fixture mapper: OpenAPI operations → MCP tool rows (no live proxy)."""
    rows = []
    for path, methods in (doc.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        for method, op in methods.items():
            if not isinstance(op, dict):
                continue
            name = str(op.get("operationId") or f"{method}_{path.strip('/').replace('/', '_')}")
            rows.append({"name": name, "description": str(op.get("summary") or "")})
    return rows


def _fn(name: str):
    return SimpleNamespace(name=name, __name__=name)


def test_normalize_local_and_remote():
    local = normalize_plugin_spec(
        {"name": "Fetch", "kind": "local", "command": "uvx", "args": ["mcp-server-fetch"]},
        name="Fetch",
    )
    assert local["kind"] == "local"
    assert local["command"] == "uvx"
    assert local["args"] == ["mcp-server-fetch"]
    assert local["enabled"] is True

    remote = normalize_plugin_spec(
        {
            "name": "proxy",
            "kind": "remote",
            "url": "https://example.invalid/mcp",
            "headers": {"Authorization": "${MCP_TOKEN}"},
        },
        name="proxy",
    )
    assert remote["kind"] == "remote"
    assert remote["url"] == "https://example.invalid/mcp"
    assert remote["headers"]["Authorization"] == "${MCP_TOKEN}"


def test_refuse_plaintext_env_and_url_userinfo():
    with pytest.raises(McpPluginError) as env_err:
        normalize_plugin_spec(
            {"name": "bad", "command": "uvx", "env": {"API_KEY": "sk-live"}},
            name="bad",
        )
    assert env_err.value.code == "plaintext_secret"

    with pytest.raises(McpPluginError) as url_err:
        normalize_plugin_spec(
            {"name": "bad", "kind": "remote", "url": "https://user:token@example.invalid/mcp"},
            name="bad",
        )
    assert url_err.value.code == "plaintext_secret"


def test_list_tools_local_and_remote_mocks():
    def local_fn(spec):
        assert spec["kind"] == "local"
        assert spec["command"] == "uvx"
        return [{"name": "fetch", "description": "Fetch a URL"}]

    tools = list_tools_for_spec(
        {"name": "fetch", "kind": "local", "command": "uvx", "args": ["mcp-server-fetch"]},
        list_tools_fn=local_fn,
    )
    assert tools == [{"name": "fetch", "description": "Fetch a URL"}]

    def remote_fn(spec):
        assert spec["kind"] == "remote"
        assert spec["url"] == "https://example.invalid/mcp"
        return [{"name": "search", "description": "Search docs"}]

    tools = list_tools_for_spec(
        {"name": "proxy", "kind": "remote", "url": "https://example.invalid/mcp"},
        list_tools_fn=remote_fn,
    )
    assert tools[0]["name"] == "search"


def test_list_tools_disabled_refuses():
    with pytest.raises(McpPluginError) as exc:
        list_tools_for_spec(
            {"name": "fetch", "command": "uvx", "enabled": False},
            list_tools_fn=lambda _spec: [{"name": "fetch"}],
        )
    assert exc.value.code == "disabled"
    with pytest.raises(McpPluginError) as text_exc:
        list_tools_for_spec(
            {"name": "fetch", "command": "uvx", "enabled": "false"},
            list_tools_fn=lambda _spec: [{"name": "fetch"}],
        )
    assert text_exc.value.code == "disabled"


def test_public_server_string_false_is_disabled():
    row = public_server("fetch", {"command": "uvx", "enabled": "False"})
    assert row["enabled"] is False


def test_public_server_redacts_and_lists_tools():
    row = public_server(
        "brave",
        {
            "command": "npx",
            "env": {"BRAVE_API_KEY": "${BRAVE_API_KEY}"},
            "discovered_tools": [{"name": "brave_web_search", "description": "Search the web"}],
        },
    )
    blob = str(row)
    assert "sk-" not in blob
    assert row["tools"][0]["name"] == "brave_web_search"
    assert row["env"]["BRAVE_API_KEY"] == "${BRAVE_API_KEY}"


def test_disable_removes_tools_from_agent():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [{"name": "web_fetch", "description": "Fetch a URL"}],
            },
            "time": {
                "command": "uvx",
                "args": ["mcp-server-time"],
                "enabled": False,
                "discovered_tools": [{"name": "get_current_time", "description": "Now"}],
            },
        }
    }
    agent = SimpleNamespace(functions=[_fn("chat")], tools=[], mcp_servers=[])
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    attach_plugin_mcp_tools(blueprint, config)
    names = [getattr(fn, "name", "") for fn in agent.functions]
    assert "web_fetch" in names
    assert "get_current_time" not in names
    assert "time" not in enabled_mcp_servers(config)

    apply_plugin_mcp_runtime(blueprint, config, [])
    names = [getattr(fn, "name", "") for fn in agent.functions]
    assert "web_fetch" not in names
    assert "chat" in names


def test_normalize_openapi_local_defaults_proxy_and_spec_env():
    spec = normalize_plugin_spec(
        {
            "name": "Pets",
            "source": "openapi",
            "kind": "local",
            "openapi_spec_url": "https://example.invalid/openapi.json",
            "env": {"API_KEY": "${API_KEY}"},
        },
        name="Pets",
    )
    assert spec["source"] == "openapi"
    assert spec["kind"] == "local"
    assert spec["command"] == OPENAPI_PROXY_COMMAND
    assert spec["args"] == list(OPENAPI_PROXY_ARGS)
    assert spec["openapi_spec_url"] == "https://example.invalid/openapi.json"
    assert spec["env"][OPENAPI_SPEC_ENV] == "https://example.invalid/openapi.json"
    assert spec["env"]["API_KEY"] == "${API_KEY}"


def test_normalize_openapi_local_file_path(tmp_path):
    spec_file = tmp_path / "pets.json"
    spec_file.write_text("{}", encoding="utf-8")
    spec = normalize_plugin_spec(
        {
            "name": "local-pets",
            "source": "openapi",
            "kind": "local",
            "openapi_spec_url": str(spec_file),
        },
        name="local-pets",
    )
    assert spec["openapi_spec_url"].startswith("file://")
    assert spec["env"][OPENAPI_SPEC_ENV].startswith("file://")


def test_normalize_openapi_remote_needs_proxy_url():
    remote = normalize_plugin_spec(
        {
            "name": "pets-remote",
            "source": "openapi",
            "kind": "remote",
            "url": "https://example.invalid/mcp",
            "openapi_spec_url": "https://example.invalid/openapi.json",
        },
        name="pets-remote",
    )
    assert remote["kind"] == "remote"
    assert remote["source"] == "openapi"
    assert remote["url"] == "https://example.invalid/mcp"
    assert remote["openapi_spec_url"] == "https://example.invalid/openapi.json"

    with pytest.raises(McpPluginError) as missing_url:
        normalize_plugin_spec(
            {
                "name": "pets-remote",
                "source": "openapi",
                "kind": "remote",
                "openapi_spec_url": "https://example.invalid/openapi.json",
            },
            name="pets-remote",
        )
    assert missing_url.value.code == "bad_payload"
    assert "proxy MCP URL" in str(missing_url.value)


def test_normalize_openapi_local_requires_spec():
    with pytest.raises(McpPluginError) as exc:
        normalize_plugin_spec(
            {"name": "pets", "source": "openapi", "kind": "local"},
            name="pets",
        )
    assert exc.value.code == "bad_payload"
    assert "spec" in str(exc.value).lower()


def test_normalize_openapi_refuses_spec_userinfo():
    with pytest.raises(McpPluginError) as exc:
        normalize_plugin_spec(
            {
                "name": "pets",
                "source": "openapi",
                "kind": "local",
                "openapi_spec_url": "https://user:token@example.invalid/openapi.json",
            },
            name="pets",
        )
    assert exc.value.code == "plaintext_secret"


def test_list_tools_openapi_mock_from_spec_operations():
    expected = _tools_from_mock_openapi(MOCK_OPENAPI)

    def openapi_fn(spec):
        assert spec["source"] == "openapi"
        assert spec["env"][OPENAPI_SPEC_ENV] == "https://example.invalid/openapi.json"
        return expected

    tools = list_tools_for_spec(
        {
            "name": "pets",
            "source": "openapi",
            "kind": "local",
            "openapi_spec_url": "https://example.invalid/openapi.json",
        },
        list_tools_fn=openapi_fn,
    )
    assert tools == [
        {"name": "list_pets", "description": "List pets"},
        {"name": "get_pet", "description": "Get a pet"},
    ]


def test_disable_openapi_server_removes_tools():
    config = {
        "mcpServers": {
            "pets": {
                "source": "openapi",
                "kind": "local",
                "command": "uvx",
                "args": ["mcp-openapi-proxy"],
                "openapi_spec_url": "https://example.invalid/openapi.json",
                "discovered_tools": _tools_from_mock_openapi(MOCK_OPENAPI),
            },
            "pets-off": {
                "source": "openapi",
                "kind": "local",
                "command": "uvx",
                "args": ["mcp-openapi-proxy"],
                "enabled": False,
                "discovered_tools": [{"name": "hidden_op", "description": "Hidden"}],
            },
        }
    }
    agent = SimpleNamespace(functions=[_fn("chat")], tools=[], mcp_servers=[])
    blueprint = SimpleNamespace(agents={"worker": agent}, starting_agent=agent)
    attach_plugin_mcp_tools(blueprint, config)
    names = [getattr(fn, "name", "") for fn in agent.functions]
    assert "list_pets" in names
    assert "get_pet" in names
    assert "hidden_op" not in names
    assert "pets-off" not in enabled_mcp_servers(config)

    apply_plugin_mcp_runtime(blueprint, config, [])
    names = [getattr(fn, "name", "") for fn in agent.functions]
    assert "list_pets" not in names
    assert "chat" in names


def test_public_server_exposes_openapi_source_without_secrets():
    row = public_server(
        "pets",
        {
            "source": "openapi",
            "command": "uvx",
            "args": ["mcp-openapi-proxy"],
            "openapi_spec_url": "https://example.invalid/openapi.json",
            "env": {"API_KEY": "${API_KEY}", "OPENAPI_SPEC_URL": "https://example.invalid/openapi.json"},
            "discovered_tools": [{"name": "list_pets", "description": "List pets"}],
        },
    )
    assert row["source"] == "openapi"
    assert row["openapi_spec_url"] == "https://example.invalid/openapi.json"
    assert row["tools"][0]["name"] == "list_pets"
    assert "sk-" not in str(row)
    assert row["env"]["API_KEY"] == "${API_KEY}"


def test_openapi_discover_honest_missing_proxy(monkeypatch):
    async def boom(*_args, **_kwargs):
        raise FileNotFoundError("uvx")

    monkeypatch.setattr("swarm.core.mcp_plugins._discover_live", boom)
    with pytest.raises(McpPluginError) as exc:
        list_tools_for_spec(
            {
                "name": "pets",
                "source": "openapi",
                "kind": "local",
                "openapi_spec_url": "https://example.invalid/openapi.json",
            }
        )
    assert exc.value.code == "mcp_discover_failed"
    assert "not installed" in str(exc.value)


def test_plugin_catalog_ids_include_discovered():
    ids = plugin_catalog_ids(
        {
            "mcpServers": {
                "custom": {
                    "command": "uvx",
                    "discovered_tools": [{"name": "acme_lookup", "description": "Lookup"}],
                },
                "off": {
                    "command": "uvx",
                    "enabled": "false",
                    "discovered_tools": [{"name": "should_stay_off", "description": "Off"}],
                },
            }
        }
    )
    assert "acme_lookup" in ids
    assert "web_search" in ids
    assert "should_stay_off" not in ids


def test_1263_attach_reaches_starting_agent_factory():
    """#1263 — a fresh chat blueprint exposes `create_starting_agent` as a
    *method* (agents not built yet). Attach must wrap the factory so the
    enabled plugin tools land on the graph the moment it is constructed,
    instead of silently attaching to nothing."""
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [{"name": "web_fetch", "description": "Fetch a URL"}],
            },
        }
    }

    class FreshApiBlueprint:
        """No `agents`, no `starting_agent` — the pre-run chat state."""

        def __init__(self) -> None:
            self.built = None

        def create_starting_agent(self, mcp_servers):  # noqa: ARG002
            agent = SimpleNamespace(functions=[_fn("chat")], tools=[], mcp_servers=[])
            self.built = agent
            return agent

    bp = FreshApiBlueprint()
    attached = attach_plugin_mcp_tools(bp, config)
    assert attached == ["web_fetch"]

    built = bp.create_starting_agent([])
    names = [getattr(fn, "name", "") for fn in built.functions]
    assert "web_fetch" in names
    assert "chat" in names
    assert built.mcp_servers == ["fetch"]


def test_1263_allowlist_applies_to_factory_agents():
    """#1263 — the per-chat allowlist must also see factory-built agents:
    after attach wraps `create_starting_agent`, running the allowlist with an
    empty `enabled_tools` strips the plugin tool from the next built graph."""
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [{"name": "web_fetch", "description": "Fetch a URL"}],
            },
        }
    }

    class FreshApiBlueprint:
        def create_starting_agent(self, mcp_servers):  # noqa: ARG002
            return SimpleNamespace(functions=[_fn("chat")], tools=[], mcp_servers=[])

    bp = FreshApiBlueprint()
    attach_plugin_mcp_tools(bp, config)
    # Plugin toggled OFF for this chat -> allowlist drops the tool from the factory path.
    apply_plugin_mcp_runtime(bp, config, [])
    built = bp.create_starting_agent([])
    names = [getattr(fn, "name", "") for fn in built.functions]
    assert "web_fetch" not in names
    assert "chat" in names


def test_1263_factory_still_receives_mcp_server_names():
    """#1263 — the wrap is additive: the original factory signature is
    preserved and `mcp_servers` names still flow to the built agent."""
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "discovered_tools": [{"name": "web_fetch", "description": "Fetch a URL"}],
            },
        }
    }

    seen = {}

    class FreshApiBlueprint:
        def create_starting_agent(self, mcp_servers):
            seen["mcp"] = list(mcp_servers or [])
            return SimpleNamespace(functions=[], tools=[], mcp_servers=list(mcp_servers or []))

    bp = FreshApiBlueprint()
    attach_plugin_mcp_tools(bp, config)
    built = bp.create_starting_agent(["preexisting"])
    assert seen["mcp"] == ["preexisting"]
    assert built.mcp_servers == ["preexisting", "fetch"]

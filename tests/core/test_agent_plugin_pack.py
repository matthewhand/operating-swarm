"""Plugin-id pack + import status without tokens (#1396)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import agent_mcp as mcp
from swarm.core import agent_memory, agent_settings
from swarm.core import agent_plugin_pack as pack
from swarm.core.agent_lifecycle import LifecycleContext, LifecycleStores
from swarm.core.agent_memory import KIND_LOG, list_memories
from swarm.core.agent_plugin_pack import (
    KEY_PLUGIN_ID,
    PACK_OBJECT,
    PluginPackError,
    export_pack,
    host_status,
    import_pack,
    plugins_section_for_pack,
    public_plugin_row,
    validate_pack,
)
from swarm.core.marketplace_catalog import MarketplaceCatalogError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_plugin_pack.json"

HOST_CONFIG = {
    "mcpServers": {
        "fetch": {
            "command": "uvx",
            "args": ["mcp-server-fetch"],
            "label": "fetch",
            "note": "Fetch a URL",
            "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"},
            "headers": {"Authorization": "${GITHUB_TOKEN}"},
            "registry_name": "io.github.example/fetch",
        }
    }
}


def _marketplace_missing(_kind, _item_id, **_kwargs):
    raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))
    monkeypatch.setenv("SWARM_AGENT_MCP_PATH", str(tmp_path / "agent_mcp.json"))
    monkeypatch.setenv("SWARM_AGENT_MEMORIES_PATH", str(tmp_path / "agent_memories.json"))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(tmp_path / "router_designs.json"))
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    pack.reset_agent_plugin_pack_cache()
    mcp.reset_agent_mcp_cache()
    agent_memory.reset_memories_cache()
    agent_settings.reset_agent_settings_cache()
    monkeypatch.setattr("swarm.core.mcp_plugins.swarm_config", lambda: HOST_CONFIG)
    monkeypatch.setattr("swarm.core.marketplace_catalog.install_item", _marketplace_missing)
    yield
    pack.reset_agent_plugin_pack_cache()
    mcp.reset_agent_mcp_cache()
    agent_memory.reset_memories_cache()
    agent_settings.reset_agent_settings_cache()


def _dumped(payload) -> str:
    return json.dumps(payload, default=str)


def test_fixture_is_secret_free():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    text = json.dumps(raw)
    for needle in ("token", "api_key", "password", "Authorization", "sk-", "command", "url"):
        assert needle not in text
    validated = validate_pack(raw)
    assert validated["object"] == PACK_OBJECT
    assert {row[KEY_PLUGIN_ID] for row in validated["plugins"]} == {
        "mcp:io.github.example/fetch",
        "web_search",
    }


def test_public_row_refuses_camel_case_connection_and_pem():
    with pytest.raises(PluginPackError) as spec_exc:
        import_pack(
            "target",
            {
                "plugins": [
                    {
                        "pluginId": "fetch",
                        "openapiSpecUrl": "https://example.invalid/openapi.json",
                    }
                ]
            },
            config=HOST_CONFIG,
        )
    assert spec_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError) as pem_exc:
        import_pack(
            "target",
            {
                "plugins": [
                    {
                        "pluginId": "fetch",
                        "description": "-----BEGIN PRIVATE KEY-----\nMIIBnotarealkey",
                    }
                ]
            },
            config=HOST_CONFIG,
        )
    assert pem_exc.value.code == "plugin_pack_secrets"
    assert export_pack("target")["plugins"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_public_row_refuses_camel_case_credential_keys():
    with pytest.raises(PluginPackError) as api_key_exc:
        public_plugin_row({"pluginId": "fetch", "apiKey": "not-a-regex-secret"})
    assert api_key_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError) as private_key_exc:
        public_plugin_row({"pluginId": "fetch", "private_key": "not-a-regex-secret"})
    assert private_key_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError):
        import_pack(
            "target",
            {"plugins": [{"pluginId": "fetch", "api-key": "not-a-regex-secret"}]},
            config=HOST_CONFIG,
        )
    assert export_pack("target")["plugins"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_public_row_refuses_url_command_and_tokens():
    with pytest.raises(PluginPackError) as url_exc:
        public_plugin_row({"pluginId": "fetch", "url": "https://example.invalid/mcp"})
    assert url_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError) as cmd_exc:
        public_plugin_row({"pluginId": "fetch", "command": "uvx", "args": ["mcp-server-fetch"]})
    assert cmd_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError) as tok_exc:
        public_plugin_row({"pluginId": "fetch", "headers": {"Authorization": "${GITHUB_TOKEN}"}})
    assert tok_exc.value.code == "plugin_pack_secrets"

    with pytest.raises(PluginPackError) as cred_exc:
        public_plugin_row({"pluginId": "sk-notarealkeyABCDEFGH"})
    assert cred_exc.value.code == "plugin_pack_secrets"


def test_pack_from_mcp_servers_is_ids_only():
    mcp.update_mcp("worker", {"mode": "all", "mcp_servers": ["fetch"]})
    section = plugins_section_for_pack("worker", config=HOST_CONFIG)
    assert section == [
        {
            KEY_PLUGIN_ID: "mcp:io.github.example/fetch",
            "name": "fetch",
            "description": "Fetch a URL",
        }
    ]
    exported = export_pack("worker", config=HOST_CONFIG)
    dumped = _dumped(exported)
    assert "GITHUB_TOKEN" not in dumped
    assert "${" not in dumped
    assert "uvx" not in dumped
    assert "mcp-server-fetch" not in dumped
    assert "Authorization" not in dumped
    assert exported["plugins"][0][KEY_PLUGIN_ID] == "mcp:io.github.example/fetch"


def test_custom_mcp_is_memory_log_not_a_fake_plugin():
    config = {
        "mcpServers": {
            **HOST_CONFIG["mcpServers"],
            "local_notes": {
                "command": "uvx",
                "args": ["secret-server"],
                "label": "Local notes",
                "note": "scratch pad",
            },
        }
    }
    mcp.update_mcp("worker", {"mode": "all", "mcp_servers": ["local_notes", "fetch"]})
    exported = export_pack("worker", config=config)
    ids = [row[KEY_PLUGIN_ID] for row in exported["plugins"]]
    assert ids == ["mcp:io.github.example/fetch"]
    assert "local_notes" not in ids
    memories = list_memories("worker", kind=KIND_LOG)
    assert len(memories) == 1
    assert memories[0]["title"] == "custom MCP: Local notes"
    assert memories[0]["body"] == "scratch pad"
    dumped = _dumped({"pack": exported, "memories": memories})
    assert "uvx" not in dumped
    assert "secret-server" not in dumped
    assert "sk-" not in dumped
    export_pack("worker", config=config)
    assert len(list_memories("worker", kind=KIND_LOG)) == 1


def test_custom_mcp_memory_scrubs_credentials():
    config = {
        "mcpServers": {
            "local_notes": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "Local notes",
                "note": "see sk-notarealkeyABCDEFGH",
            }
        }
    }
    mcp.update_mcp("worker", {"mode": "all", "mcp_servers": ["local_notes"]})
    exported = export_pack("worker", config=config)
    assert exported["plugins"] == []
    memories = list_memories("worker", kind=KIND_LOG)
    assert memories
    dumped = _dumped(memories)
    assert "sk-notarealkeyABCDEFGH" not in dumped
    assert "sk-" not in dumped
    assert "uvx" not in dumped
    assert "mcp-server-fetch" not in dumped


def test_import_enables_installed_and_reports_missing_without_tokens(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    result = import_pack(
        "target",
        {
            "plugins": [
                {"pluginId": "mcp:io.github.example/fetch", "name": "fetch"},
                {"pluginId": "not-installed-anywhere"},
                "web_search",
            ]
        },
        config=HOST_CONFIG,
    )
    dumped = _dumped(result)
    assert "sk-" not in dumped
    assert "${GITHUB_TOKEN}" not in dumped
    assert "uvx" not in dumped
    assert result["object"] == "agent_plugin_pack_import"
    assert "mcp:io.github.example/fetch" in result["enabled"]
    assert "web_search" in result["enabled"]
    assert result["missing"] == ["not-installed-anywhere"]
    by_id = {row[KEY_PLUGIN_ID]: row for row in result["plugins"]}
    assert by_id["mcp:io.github.example/fetch"]["status"] == "enabled"
    assert by_id["mcp:io.github.example/fetch"]["install_attempted"] is True
    assert by_id["not-installed-anywhere"]["status"] == "missing-plugin"
    assert result["missing_plugin"] == ["not-installed-anywhere"]
    assert result["missing_auth"] == []
    assert "token" not in by_id["not-installed-anywhere"]
    assert "url" not in by_id["mcp:io.github.example/fetch"]
    assert "present-for-test" not in dumped
    assigned = mcp.get_mcp("target")
    assert assigned["mode"] == "all"
    assert "fetch" in assigned["mcp_servers"]


def test_import_reports_missing_auth_when_required_env_unset():
    result = import_pack(
        "target",
        {"plugins": [{"pluginId": "mcp:io.github.example/fetch", "name": "fetch"}]},
        config=HOST_CONFIG,
    )
    dumped = _dumped(result)
    row = result["plugins"][0]
    assert row["status"] == "missing-auth"
    assert row["connect_needed"] is True
    assert row["required_env"] == ["GITHUB_TOKEN"]
    assert result["enabled"] == []
    assert result["missing_auth"] == ["mcp:io.github.example/fetch"]
    assert result["missing_plugin"] == []
    assert "${GITHUB_TOKEN}" not in dumped
    assert "uvx" not in dumped
    assert "sk-" not in dumped
    assert "fetch" in mcp.get_mcp("target")["mcp_servers"]


def test_import_attempts_marketplace_install(monkeypatch):
    calls: list[tuple[str, str]] = []

    def _record(kind, item_id, **_kwargs):
        calls.append((kind, item_id))
        if item_id == "notes":
            return {
                "installed": True,
                "already_installed": False,
                "name": "notes",
                "required_env": [],
            }
        raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)

    monkeypatch.setattr("swarm.core.marketplace_catalog.install_item", _record)
    result = import_pack(
        "target",
        {"plugins": ["notes", "not-a-plugin"]},
        config=HOST_CONFIG,
    )
    assert ("plugins", "notes") in calls
    assert ("plugins", "not-a-plugin") in calls
    by_id = {row[KEY_PLUGIN_ID]: row for row in result["plugins"]}
    assert by_id["notes"]["status"] == "enabled"
    assert by_id["not-a-plugin"]["status"] == "missing-plugin"
    assert "notes" in mcp.get_mcp("target")["mcp_servers"]
    assert "uvx" not in _dumped(result)


def test_round_trip_pack_fragment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    import_pack(
        "source",
        {"plugins": [{"pluginId": "fetch", "name": "fetch", "description": "Fetch a URL"}]},
        config=HOST_CONFIG,
    )
    exported = export_pack("source", config=HOST_CONFIG)
    imported = import_pack("copy", exported, config=HOST_CONFIG)
    assert imported["enabled"] == ["fetch"]
    assert imported["missing"] == []
    assert export_pack("copy", config=HOST_CONFIG)["plugins"] == exported["plugins"]


def test_import_rejects_connection_block_and_does_not_persist():
    with pytest.raises(PluginPackError) as exc:
        import_pack(
            "target",
            {
                "plugins": [
                    {
                        "pluginId": "leaky",
                        "command": "npx",
                        "env": {"TOKEN": "sk-notarealkeyABCDEFGH"},
                    }
                ]
            },
            config=HOST_CONFIG,
        )
    assert exc.value.code == "plugin_pack_secrets"
    assert export_pack("target")["plugins"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_import_prefers_exact_server_over_colliding_label():
    config = {
        "mcpServers": {
            "decoy": {
                "command": "uvx",
                "args": ["mcp-server-decoy"],
                "label": "fetch",
            },
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "Fetch MCP",
                "registry_name": "io.github.example/fetch",
            },
        }
    }
    result = import_pack("target", {"plugins": ["fetch"]}, config=config)
    assert result["enabled"] == ["fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["fetch"]


def test_import_prefers_registry_id_over_unrelated_server_name():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "local fetch",
            },
            "registry-fetch": {
                "command": "uvx",
                "args": ["mcp-server-registry"],
                "label": "registry fetch",
                "registry_name": "io.github.example/fetch",
            },
        }
    }
    result = import_pack(
        "target",
        {"plugins": ["mcp:io.github.example/fetch"]},
        config=config,
    )
    assert result["enabled"] == ["mcp:io.github.example/fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["registry-fetch"]


def test_ambiguous_label_is_missing_and_not_attached():
    config = {
        "mcpServers": {
            "alpha": {"command": "uvx", "args": ["a"], "label": "shared"},
            "beta": {"command": "uvx", "args": ["b"], "label": "shared"},
        }
    }
    result = import_pack("target", {"plugins": ["shared"]}, config=config)
    assert result["missing"] == ["shared"]
    assert result["enabled"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_namespaced_id_does_not_attach_a_different_owner():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "Local fetch",
                "registry_name": "io.github.example/fetch",
            }
        }
    }
    result = import_pack("target", {"plugins": ["io.github.evil/fetch"]}, config=config)
    assert result["missing"] == ["io.github.evil/fetch"]
    assert result["enabled"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_github_prefix_registry_beats_local_tail():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "Local fetch",
            },
            "reg": {
                "command": "uvx",
                "args": ["mcp-server-registry"],
                "label": "Registry",
                "registry_name": "github:owner/fetch",
            },
        }
    }
    result = import_pack("target", {"plugins": ["owner/fetch"]}, config=config)
    assert result["enabled"] == ["owner/fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["reg"]


def test_namespaced_id_matches_exact_label_without_registry_name():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "io.github.example/fetch",
            }
        }
    }
    result = import_pack(
        "target",
        {"plugins": ["mcp:io.github.example/fetch"]},
        config=config,
    )
    assert result["enabled"] == ["mcp:io.github.example/fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["fetch"]


def test_bare_id_matches_unique_registry_tail():
    config = {
        "mcpServers": {
            "registry-fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "label": "Registry fetch",
                "registry_name": "io.github.example/fetch",
            }
        }
    }
    result = import_pack("target", {"plugins": ["fetch"]}, config=config)
    assert result["enabled"] == ["fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["registry-fetch"]


def test_disabled_server_id_is_not_taken_by_a_label():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "enabled": False,
            },
            "decoy": {
                "command": "uvx",
                "args": ["mcp-server-decoy"],
                "label": "fetch",
            },
        }
    }
    result = import_pack("target", {"plugins": ["fetch"]}, config=config)
    assert result["missing"] == ["fetch"]
    assert result["enabled"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_underscore_id_matches_only_hyphen_server():
    config = {"mcpServers": {"my-server": {"command": "uvx", "args": ["a"]}}}
    result = import_pack("target", {"plugins": ["my_server"]}, config=config)
    assert result["enabled"] == ["my_server"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["my-server"]


def test_underscore_tail_matches_hyphen_tail_for_the_same_owner():
    config = {
        "mcpServers": {
            "reg": {
                "command": "uvx",
                "args": ["a"],
                "registry_name": "io.github.example/my-tool",
            }
        }
    }
    result = import_pack("target", {"plugins": ["io.github.example/my_tool"]}, config=config)
    assert result["enabled"] == ["io.github.example/my_tool"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["reg"]


def test_underscore_in_the_owner_does_not_match_a_hyphen_owner():
    config = {
        "mcpServers": {
            "reg": {
                "command": "uvx",
                "args": ["a"],
                "registry_name": "io.github.evil-org/fetch",
            }
        }
    }
    result = import_pack("target", {"plugins": ["io.github.evil_org/fetch"]}, config=config)
    assert result["missing"] == ["io.github.evil_org/fetch"]
    assert result["enabled"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_two_registry_tails_do_not_attach_a_bare_id():
    config = {
        "mcpServers": {
            "a": {"command": "uvx", "args": ["a"], "registry_name": "io.github.a/fetch"},
            "b": {"command": "uvx", "args": ["b"], "registry_name": "io.github.b/fetch"},
        }
    }
    result = import_pack("target", {"plugins": ["fetch"]}, config=config)
    assert result["missing"] == ["fetch"]
    assert result["enabled"] == []
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_stacked_prefixes_match_the_registry_id():
    config = {
        "mcpServers": {
            "reg": {
                "command": "uvx",
                "args": ["mcp-server-registry"],
                "registry_name": "owner/fetch",
            }
        }
    }
    result = import_pack("target", {"plugins": ["github:mcp:owner/fetch"]}, config=config)
    assert result["enabled"] == ["github:mcp:owner/fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == ["reg"]


def test_namespaced_catalog_tail_does_not_enable_builtin():
    agent_settings.update_settings("target", {"mcp_tool_grants": ["read_file"]})
    result = import_pack("target", {"plugins": ["io.github.evil/web_search"]}, config=HOST_CONFIG)
    assert result["missing"] == ["io.github.evil/web_search"]
    assert result["enabled"] == []
    assert agent_settings.get_settings("target")["mcp_tool_grants"] == ["read_file"]
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_string_disabled_assigned_server_is_not_packed():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "enabled": " false ",
                "registry_name": "io.github.example/fetch",
            }
        }
    }
    mcp.update_mcp("worker", {"mode": "all", "mcp_servers": ["fetch"]})
    assert plugins_section_for_pack("worker", config=config) == []


def test_disabled_server_string_is_not_enabled():
    config = {
        "mcpServers": {
            "fetch": {
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "enabled": "false",
                "registry_name": "io.github.example/fetch",
            }
        }
    }
    result = import_pack("target", {"plugins": ["fetch"]}, config=config)
    assert result["missing"] == ["fetch"]
    assert mcp.get_mcp("target")["mcp_servers"] == []


def test_host_status_empty_agent():
    payload = host_status("empty", config=HOST_CONFIG)
    assert payload["object"] == "agent_plugins"
    assert payload["plugins"] == []
    assert payload["enabled"] == []
    assert payload["missing"] == []
    assert payload["missing_plugin"] == []
    assert payload["missing_auth"] == []


def _lifecycle() -> LifecycleContext:
    stores = LifecycleStores(
        companies={
            "acme": {
                "id": "acme",
                "slug": "acme",
                "name": "Acme",
                "model_policy": {
                    "mode": "allow_all",
                    "allowed_models": [],
                    "denied_models": [],
                    "default_model": "",
                },
            }
        }
    )
    return LifecycleContext(caller_id="support", caller_role="support", stores=stores)


def test_partial_plugin_failure_does_not_abort_agent_create(monkeypatch):
    def _boom(_kind, item_id, **_kwargs):
        if item_id == "explode":
            raise RuntimeError("install blew up")
        raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)

    monkeypatch.setattr("swarm.core.marketplace_catalog.install_item", _boom)
    ctx = _lifecycle()
    result = ctx.create_agent(
        "Partial Bot",
        "api",
        plugins={"plugins": ["explode", "web_search"]},
    )
    assert result["ok"] is True
    assert result["agent"]["id"] == "partial_bot"
    assert any(row.get("id") == "partial_bot" for row in (ctx.stores.library.get("custom") or []))
    by_id = {row[KEY_PLUGIN_ID]: row["status"] for row in result["plugins"]["plugins"]}
    assert by_id["explode"] == "missing-plugin"
    assert by_id["web_search"] == "enabled"
    assert result["plugins"]["ok"] is True
    assert "install blew up" not in _dumped(result)


def test_plugin_secret_refusal_does_not_abort_agent_create():
    ctx = _lifecycle()
    result = ctx.create_agent(
        "Safe Bot",
        "api",
        plugins={
            "plugins": [
                {
                    "pluginId": "leaky",
                    "command": "npx",
                    "env": {"TOKEN": "sk-notarealkeyABCDEFGH"},
                }
            ]
        },
    )
    dumped = _dumped(result)
    assert result["ok"] is True
    assert result["agent"]["id"] == "safe_bot"
    assert result["plugins"]["ok"] is False
    assert result["plugins"]["code"] == "plugin_pack_secrets"
    assert "sk-notarealkeyABCDEFGH" not in dumped
    assert export_pack("safe_bot")["plugins"] == []


def test_attach_failure_does_not_abort_agent_create(monkeypatch):
    def _boom(*_args, **_kwargs):
        raise RuntimeError("mcp update failed")

    monkeypatch.setattr(mcp, "update_mcp", _boom)
    monkeypatch.setenv("GITHUB_TOKEN", "present-for-test")
    ctx = _lifecycle()
    result = ctx.create_agent(
        "Attach Bot",
        "api",
        plugins={"plugins": ["mcp:io.github.example/fetch", "web_search"]},
    )
    assert result["ok"] is True
    assert result["agent"]["id"] == "attach_bot"
    by_id = {row[KEY_PLUGIN_ID]: row["status"] for row in result["plugins"]["plugins"]}
    assert by_id["mcp:io.github.example/fetch"] == "enabled"
    assert by_id["web_search"] == "enabled"
    assert "present-for-test" not in _dumped(result)
    assert "mcp update failed" not in _dumped(result)


def test_catalog_enable_extends_active_grant_policy_only():
    agent_settings.update_settings("target", {"mcp_tool_grants": ["read_file"]})
    granted = import_pack("target", {"plugins": ["web_search"]}, config=HOST_CONFIG)
    assert granted["plugins"][0]["status"] == "enabled"
    assert granted["plugins"][0]["install_attempted"] is True
    assert agent_settings.get_settings("target")["mcp_tool_grants"] == ["read_file", "web_search"]

    opened = import_pack("open", {"plugins": ["web_search"]}, config=HOST_CONFIG)
    assert opened["plugins"][0]["status"] == "enabled"
    assert agent_settings.get_settings("open")["mcp_tool_grants"] == []

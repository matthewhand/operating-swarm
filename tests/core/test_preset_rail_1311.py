"""#1311 — one-action preset bot lands on the rail with provider/model/plugins."""

from __future__ import annotations

import pytest

from swarm.core.agent_lifecycle import (
    LifecycleContext,
    LifecycleStores,
    materialize_preset_bot,
)
from swarm.core.agent_plugin_pack import list_plugin_rows, reset_agent_plugin_pack_cache
from swarm.core.blueprint_spec import get_preset_bot
from swarm.core.marketplace_catalog import MarketplaceCatalogError
from swarm.core.rail_seats import custom_library_to_blueprint_rows


@pytest.fixture(autouse=True)
def isolated_plugins(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_PLUGINS_PATH", str(tmp_path / "agent_plugins.json"))

    def _missing(_plugin_id):
        raise MarketplaceCatalogError("Marketplace item not found.", code="not_found", status=404)

    monkeypatch.setattr("swarm.core.agent_plugin_pack.install_marketplace_plugin", _missing)
    reset_agent_plugin_pack_cache()
    yield
    reset_agent_plugin_pack_cache()


def _support_ctx(stores: LifecycleStores) -> LifecycleContext:
    if not stores.companies:
        stores.companies["acme"] = {
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
    return LifecycleContext(
        caller_id="support",
        caller_kind="api",
        caller_role="support",
        stores=stores,
    )


def test_create_agent_preset_id_resolves_rail_seat():
    preset = get_preset_bot("preset-researcher")
    assert preset is not None
    stores = LifecycleStores(library={"installed": [], "custom": []}, persist_library=False)
    result = _support_ctx(stores).create_agent("", "", preset_id="preset-researcher")
    assert result["ok"] is True, result
    agent = result["agent"]
    assert agent["id"] == "preset-researcher"
    assert agent["rail"] is True
    assert agent["provider"] == preset["provider"]
    assert agent["model"] == preset["model"]
    assert agent["plugins"] == preset["plugins"]
    assert agent["role"] == preset["role"]
    assert result["plugins"]["ok"] is True
    stored = list_plugin_rows(agent["id"])
    assert [row["pluginId"] for row in stored] == preset["plugins"]
    rows = custom_library_to_blueprint_rows(stores.library["custom"])
    assert len(rows) == 1
    assert rows[0]["rail"] is True
    assert rows[0]["provider"] == preset["provider"]
    assert rows[0]["model"] == preset["model"]
    assert rows[0]["role"] == preset["role"]
    assert rows[0]["required_mcp_servers"] == preset["plugins"]
    assert rows[0]["plugins"] == preset["plugins"]


def test_preset_copy_does_not_mutate_the_catalog():
    preset = get_preset_bot("preset-support")
    assert preset is not None
    preset["plugins"].append("not-a-real-plugin")
    again = get_preset_bot("preset-support")
    assert again is not None
    assert "not-a-real-plugin" not in again["plugins"]
    assert again["plugins"] == ["support-tools"]


def test_materialize_preset_bot_is_one_action():
    stores = LifecycleStores(library={"installed": [], "custom": []}, persist_library=False)
    _support_ctx(stores)
    result = materialize_preset_bot("preset-reviewer", stores=stores)
    assert result["ok"] is True, result
    assert result["agent"]["preset_id"] == "preset-reviewer"
    assert result["agent"]["role"] == "skeptic"
    assert result["agent"]["plugins"] == ["repo-reader"]
    assert [row["pluginId"] for row in result["plugins"]["plugins"]] == ["repo-reader"]
    seat = custom_library_to_blueprint_rows(stores.library["custom"])[0]
    assert seat["id"] == "preset-reviewer"
    assert seat["role"] == "skeptic"
    assert seat["plugins"] == ["repo-reader"]


def test_support_preset_keeps_support_role():
    stores = LifecycleStores(library={"installed": [], "custom": []}, persist_library=False)
    _support_ctx(stores)
    result = materialize_preset_bot("preset-support", stores=stores)
    assert result["ok"] is True, result
    assert result["agent"]["role"] == "support"
    assert result["agent"]["provider"] == "openai"
    assert result["agent"]["model"] == "gpt-4o-mini"
    assert [row["pluginId"] for row in list_plugin_rows("preset-support")] == ["support-tools"]

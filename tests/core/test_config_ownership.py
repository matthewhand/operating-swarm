"""#776 config ownership — Full coverage, refuse secrets, force-env, write paths."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from swarm.core import config_ownership as own
from swarm.core import remotes as remotes_core
from swarm.core.llm_task_routing import persist_llm_settings, settings_public_payload


def _cfg(tmp_path: Path, blob: dict) -> Path:
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps(blob), encoding="utf-8")
    return path


def test_example_config_has_no_plaintext_secrets():
    root = Path(__file__).resolve().parents[2]
    example = (root / "swarm_config.example.json").read_text(encoding="utf-8")
    data = json.loads(example)
    blob = json.dumps(data)
    assert "sk-" not in blob
    assert "${OPENAI_API_KEY}" in example
    assert "10.0.0." not in example


def test_decision_is_full_and_inventory_has_no_silent_gaps():
    payload = own.ownership_payload({"llm": {}, "settings": {}})
    assert payload["decision"] == "Full"
    keys = {row["key"] for row in payload["inventory"]}
    for required in (
        "llm",
        "settings.default_llm_profile",
        "mcpServers",
        "remotes",
        "cli_agents",
        "agent_team",
        "cli_fusion",
        "moa",
        "slashCommands",
        "blueprints",
        "memory",
        "speech",
        "secrets.*",
        "deploy.HOST",
        "deploy.PORT",
    ):
        assert required in keys
    assert "webui" in {row["partition"] for row in payload["inventory"]}
    assert "env_only" in {row["partition"] for row in payload["inventory"]}
    blob = json.dumps(payload)
    assert "sk-" not in blob
    assert "api_key_set" not in blob or "Secret" in blob


def test_refuse_out_of_partition_and_plaintext_secret(tmp_path: Path):
    path = _cfg(tmp_path, {"llm": {}})
    with pytest.raises(own.ConfigOwnershipError) as exc:
        own.persist_webui_section("DJANGO_SECRET_KEY", entries={}, config_path=path)
    assert exc.value.status == 403
    assert exc.value.code == "out_of_partition"

    with pytest.raises(own.ConfigOwnershipError) as exc:
        own.persist_webui_section(
            "llm",
            upsert={"lab": {"provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-live-token"}},
            config_path=path,
        )
    assert exc.value.code == "plaintext_secret"
    assert "sk-live" not in path.read_text(encoding="utf-8")


def test_write_paths_for_webui_sections(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("SWARM_CONFIG_FORCE_ENV", raising=False)
    path = _cfg(tmp_path, {"llm": {}})

    own.persist_webui_section(
        "llm",
        upsert={"local": {"provider": "openai", "model": "llama3", "api_key": "${OPENAI_API_KEY}"}},
        config_path=path,
    )
    persist_llm_settings(
        default_llm_profile="local",
        override_per_task=False,
        task_llm_profiles={},
        config_path=path,
    )
    own.persist_webui_section(
        "mcpServers",
        upsert={"filesystem": {"command": "npx", "args": ["-y", "mcp"], "env": {"TOKEN": "${MCP_TOKEN}"}}},
        config_path=path,
    )
    remotes_core.persist_remote(
        "hermes",
        base_url="http://127.0.0.1:9",
        api_key_env="HERMES_API_KEY",
        config_path=path,
    )
    own.persist_webui_section(
        "cli_agents",
        upsert={"grok": {"cmd": ["grok"]}},
        config_path=path,
    )
    remotes_core.persist_agent_team([], config_path=path)
    own.persist_webui_section("slashCommands", upsert={"brief": {"prompt": "summarise"}}, config_path=path)
    own.persist_webui_section("moa", upsert={"seats": 3}, config_path=path)
    own.persist_webui_section("blueprints", upsert={"support": {"default_model": "local"}}, config_path=path)
    own.persist_webui_section("memory", upsert={"backend": "mem0"}, config_path=path)

    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["llm"]["local"]["api_key"] == "${OPENAI_API_KEY}"
    assert data["settings"]["default_llm_profile"] == "local"
    assert data["mcpServers"]["filesystem"]["env"]["TOKEN"] == "${MCP_TOKEN}"
    assert data["remotes"]["hermes"]["api_key"] == "${HERMES_API_KEY}"
    assert data["cli_agents"]["grok"]["cmd"] == ["grok"]
    assert data["agent_team"]["members"] == []
    assert data["slashCommands"]["brief"]["prompt"] == "summarise"
    assert data["moa"]["seats"] == 3
    assert "sk-" not in path.read_text(encoding="utf-8")


def test_rate_limit_token_fields_are_not_treated_as_secrets(tmp_path):
    path = _cfg(tmp_path, {"llm": {}, "cli_agents": {"stub": {"cmd": ["echo"]}}})
    own.persist_webui_section(
        "cli_agents",
        upsert={
            "stub": {
                "cmd": ["echo"],
                "rate_limits": {"tokens_per_minute": 100, "messages_per_minute": 1},
            }
        },
        config_path=path,
    )
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["cli_agents"]["stub"]["rate_limits"]["tokens_per_minute"] == 100
    assert data["cli_agents"]["stub"]["cmd"] == ["echo"]
    assert own.is_secret_key("tokens_per_minute") is False
    assert own.is_secret_key("api_key") is True


def test_badges_and_force_env(monkeypatch):
    monkeypatch.delenv("SWARM_CONFIG_FORCE_ENV", raising=False)
    monkeypatch.setenv("DEFAULT_LLM", "from-env")
    from_env = own.badge_for(env_var="DEFAULT_LLM", persisted=None)
    assert from_env["kind"] == "from_env"
    assert "DEFAULT_LLM" in from_env["label"]

    overrides = own.badge_for(env_var="DEFAULT_LLM", persisted="saved")
    assert overrides["kind"] == "overrides_env"

    monkeypatch.setenv("SWARM_CONFIG_FORCE_ENV", "1")
    forced = own.badge_for(env_var="DEFAULT_LLM", persisted="saved")
    assert forced["kind"] == "forced"
    assert forced["editable"] is False

    secret = own.badge_for(env_var="OPENAI_API_KEY", persisted="${OPENAI_API_KEY}", secret=True)
    assert secret["kind"] == "secret"
    assert "Secret" in secret["label"]


def test_hybrid_remote_url_file_wins_unless_force(monkeypatch):
    monkeypatch.delenv("SWARM_CONFIG_FORCE_ENV", raising=False)
    monkeypatch.setenv("OMB_BASE_URL", "http://10.9.9.9:8802")
    cfg = {"remotes": {"omb": {"base_url": "http://198.51.100.32:8802"}}}
    spec = remotes_core.load_remote("omb", cfg)
    assert spec.base_url == "http://198.51.100.32:8802"
    assert spec.source == "config"
    assert spec.provenance["base_url"]["kind"] == "overrides_env"

    monkeypatch.setenv("SWARM_CONFIG_FORCE_ENV", "1")
    forced = remotes_core.load_remote("omb", cfg)
    assert forced.base_url == "http://10.9.9.9:8802"
    assert forced.source == "env"
    assert forced.provenance["base_url"]["kind"] == "forced"


def test_persist_remote_refuses_plaintext_key(tmp_path: Path):
    path = _cfg(tmp_path, {"llm": {}})
    with pytest.raises(remotes_core.RemoteError, match="plaintext"):
        remotes_core.persist_remote("hermes", api_key="sk-live-token", config_path=path)
    assert "sk-live" not in path.read_text(encoding="utf-8")


def test_llm_payload_includes_provenance(monkeypatch):
    monkeypatch.delenv("SWARM_CONFIG_FORCE_ENV", raising=False)
    monkeypatch.setenv("DEFAULT_LLM", "env-default")
    payload = settings_public_payload(
        {
            "llm": {"saved": {"provider": "openai", "model": "gpt-4o-mini"}},
            "settings": {"default_llm_profile": "saved"},
        }
    )
    assert payload["provenance"]["default_llm_profile"]["kind"] == "overrides_env"
    assert "api_key" not in json.dumps(payload)

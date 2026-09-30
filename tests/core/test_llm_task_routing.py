"""REQ-43 / #358: default LLM + per-task override + auto-pick."""

from __future__ import annotations

import json
from pathlib import Path

from swarm.core.llm_task_routing import (
    BUILTIN_FALLBACK,
    TASK_CLASS_AUXILIARY,
    TASK_CLASS_DELEGATION,
    TASK_CLASS_ORCHESTRATION,
    auto_pick_task_models,
    effective_default_profile,
    infer_vendor,
    persist_llm_settings,
    persist_named_llm_profile,
    resolve_design_model,
    resolve_for_task,
    resolve_summary_model,
    settings_public_payload,
)


# Mixed boring gateway ids — no secrets.
BORING_FIXTURE = ("gpt-4o-mini", "gpt-5.6-terra", "o3")


def test_infer_vendor_recognizes_mistral_without_stealing_mixtral():
    assert infer_vendor("mistral-large-latest", {"provider": "mistral"}) == "mistral"
    assert infer_vendor("chat", {"provider": "mistralai", "base_url": "https://api.mistral.ai/v1"}) == "mistral"
    assert infer_vendor("mixtral-8x7b", {"provider": "groq"}) == "groq"


def test_mixed_boring_ids_map_to_three_distinct_classes():
    result = auto_pick_task_models(BORING_FIXTURE)
    assert result.picks[TASK_CLASS_AUXILIARY] == "gpt-4o-mini"
    assert result.picks[TASK_CLASS_ORCHESTRATION] == "gpt-5.6-terra"
    assert result.picks[TASK_CLASS_DELEGATION] == "o3"
    assert len(set(result.picks.values())) == 3
    assert result.default == "gpt-5.6-terra"
    assert result.aliases_used == []


def test_auto_pick_delegation_prefers_latest_opus():
    # #1326: design/coding (delegation) auto-pick must steer to the newest Opus
    # when the connected catalog exposes it, even with the 4.x delegate present.
    result = auto_pick_task_models(
        ("claude-opus-5-5", "claude-sonnet-4-6", "claude-haiku-4-5")
    )
    assert result.picks[TASK_CLASS_DELEGATION] == "claude-opus-5-5"
    assert result.picks[TASK_CLASS_AUXILIARY] == "claude-haiku-4-5"
    assert result.picks[TASK_CLASS_ORCHESTRATION] == "claude-sonnet-4-6"


def test_auto_pick_delegation_falls_back_to_older_opus():
    # With no 5.5 in the catalog, the previous Opus still wins delegation.
    result = auto_pick_task_models(
        ("claude-opus-4-8", "claude-sonnet-4-6", "claude-haiku-4-5")
    )
    assert result.picks[TASK_CLASS_DELEGATION] == "claude-opus-4-8"


def test_alias_profiles_win_when_present():
    result = auto_pick_task_models(
        ("orchestration", "auxiliary", "delegation", "gpt-5.6-terra"),
        aliases=("orchestration", "auxiliary", "delegation"),
    )
    assert result.picks[TASK_CLASS_ORCHESTRATION] == "orchestration"
    assert result.picks[TASK_CLASS_AUXILIARY] == "auxiliary"
    assert result.picks[TASK_CLASS_DELEGATION] == "delegation"
    assert set(result.aliases_used) == {
        "orchestration",
        "auxiliary",
        "delegation",
    }


def test_empty_catalog_warns_and_does_not_crash():
    result = auto_pick_task_models([])
    assert result.picks == {
        TASK_CLASS_ORCHESTRATION: BUILTIN_FALLBACK,
        TASK_CLASS_AUXILIARY: BUILTIN_FALLBACK,
        TASK_CLASS_DELEGATION: BUILTIN_FALLBACK,
    }
    assert result.default == BUILTIN_FALLBACK
    assert result.warnings
    assert "default" in result.warnings[0]


def test_override_off_ignores_the_map():
    config = {
        "llm": {
            "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
            "gpt-5.6-terra": {"provider": "openai", "model": "gpt-5.6-terra"},
            "o3": {"provider": "openai", "model": "o3"},
        },
        "settings": {
            "default_llm_profile": "gpt-5.6-terra",
            "override_per_task": False,
            "task_llm_profiles": {
                "auxiliary": "gpt-4o-mini",
                "delegation": "o3",
                "orchestration": "gpt-5.6-terra",
            },
        },
    }
    summary = resolve_summary_model(config)
    design = resolve_design_model(config)
    assert summary.profile == "gpt-5.6-terra"
    assert design.profile == "gpt-5.6-terra"
    assert summary.override_on is False
    assert design.override_on is False
    assert summary.source == "default"


def test_override_on_routes_stub_summary_to_auxiliary_and_design_to_delegation():
    config = {
        "llm": {
            "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
            "gpt-5.6-terra": {"provider": "openai", "model": "gpt-5.6-terra"},
            "o3": {"provider": "openai", "model": "o3"},
        },
        "settings": {
            "default_llm_profile": "gpt-5.6-terra",
            "override_per_task": True,
            "task_llm_profiles": {
                "auxiliary": "gpt-4o-mini",
                "delegation": "o3",
                "orchestration": "gpt-5.6-terra",
            },
        },
    }
    # #356 hook: code summary must honour the auxiliary mapping.
    summary = resolve_summary_model(config)
    design = resolve_design_model(config)
    chat = resolve_for_task(TASK_CLASS_ORCHESTRATION, config)
    assert summary.profile == "gpt-4o-mini"
    assert summary.task_class == TASK_CLASS_AUXILIARY
    assert summary.used_fallback is False
    assert design.profile == "o3"
    assert design.task_class == TASK_CLASS_DELEGATION
    assert chat.profile == "gpt-5.6-terra"


def test_missing_slug_warns_and_uses_default():
    config = {
        "llm": {
            "gpt-5.6-terra": {"provider": "openai", "model": "gpt-5.6-terra"},
        },
        "settings": {
            "default_llm_profile": "gpt-5.6-terra",
            "override_per_task": True,
            "task_llm_profiles": {"auxiliary": "missing-slug"},
        },
    }
    route = resolve_summary_model(config)
    assert route.profile == "gpt-5.6-terra"
    assert route.used_fallback is True
    assert route.warning
    assert "missing-slug" in route.warning
    assert "gpt-5.6-terra" in route.warning


def test_unsaved_auto_picks_are_the_defaults():
    config = {
        "llm": {
            "gpt-4o-mini": {"provider": "openai", "model": "gpt-4o-mini"},
            "gpt-5.6-terra": {"provider": "openai", "model": "gpt-5.6-terra"},
            "o3": {"provider": "openai", "model": "o3"},
        },
        "settings": {},
    }
    payload = settings_public_payload(config)
    assert payload["default_is_auto"] is True
    assert payload["default_llm_profile"] == "gpt-5.6-terra"
    assert payload["auto_picks"]["auxiliary"] == "gpt-4o-mini"
    assert payload["auto_picks"]["delegation"] == "o3"
    assert "api_key" not in json.dumps(payload)


def test_public_payload_redacts_secrets():
    config = {
        "llm": {
            "gpt-5.6-terra": {
                "provider": "openai",
                "model": "gpt-5.6-terra",
                "api_key": "sk-secret-must-not-leak",
                "intelligence": 0.7,
            },
        },
    }
    payload = settings_public_payload(config)
    blob = json.dumps(payload)
    assert "sk-secret" not in blob
    assert "api_key" not in blob
    assert any(item["id"] == "gpt-5.6-terra" for item in payload["profiles"])


def test_persist_default_picker_writes_existing_settings_key(tmp_path: Path):
    path = tmp_path / "swarm_config.json"
    path.write_text(json.dumps({"llm": {"default": {"provider": "openai"}}}), encoding="utf-8")
    cfg, written = persist_llm_settings(
        default_llm_profile="gpt-5.6-terra",
        override_per_task=True,
        task_llm_profiles={
            "auxiliary": "gpt-4o-mini",
            "delegation": "o3",
            "orchestration": "gpt-5.6-terra",
        },
        config_path=path,
    )
    assert written == path
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["settings"]["default_llm_profile"] == "gpt-5.6-terra"
    assert raw["settings"]["override_per_task"] is True
    assert raw["settings"]["task_llm_profiles"]["auxiliary"] == "gpt-4o-mini"
    assert cfg["settings"]["default_llm_profile"] == "gpt-5.6-terra"
    assert "sk-" not in path.read_text(encoding="utf-8")


# ------------------------------------------------- REQ-853 / #207 default readiness


def _llm_config(profile: dict) -> dict:
    return {"settings": {}, "llm": {"default": profile}}


def test_default_llm_ready_true_for_literal_profile(monkeypatch):
    monkeypatch.setenv("TEST_LLM_KEY_207", "sk-test")
    config = _llm_config(
        {"provider": "openai", "model": "gpt-4o-mini", "api_key": "${TEST_LLM_KEY_207}"}
    )
    payload = settings_public_payload(config)
    assert payload["default_llm_ready"] is True
    # No secret values leak through the new flag.
    assert "sk-test" not in json.dumps(payload)


def test_default_llm_ready_false_when_key_env_missing(monkeypatch):
    monkeypatch.delenv("TEST_LLM_KEY_207_ABSENT", raising=False)
    config = _llm_config(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "${TEST_LLM_KEY_207_ABSENT}",
        }
    )
    payload = settings_public_payload(config)
    assert payload["default_llm_ready"] is False


def test_default_llm_ready_false_when_no_key_and_no_base_url():
    config = _llm_config({"provider": "openai", "model": "gpt-4o-mini"})
    assert settings_public_payload(config)["default_llm_ready"] is False


def test_default_llm_ready_true_with_custom_base_url_only():
    config = _llm_config(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "http://litellm.internal:8000",
        }
    )
    assert settings_public_payload(config)["default_llm_ready"] is True


def test_default_llm_ready_false_when_base_url_env_unresolvable(monkeypatch):
    monkeypatch.delenv("TEST_LLM_URL_207_ABSENT", raising=False)
    config = _llm_config(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "base_url": "${TEST_LLM_URL_207_ABSENT}",
        }
    )
    assert settings_public_payload(config)["default_llm_ready"] is False


def test_default_llm_ready_true_with_resolvable_model_template(monkeypatch):
    monkeypatch.setenv("TEST_LLM_MODEL_207", "gpt-4o-mini")
    config = _llm_config(
        {"provider": "openai", "model": "${TEST_LLM_MODEL_207}", "api_key": "sk-literal"}
    )
    assert settings_public_payload(config)["default_llm_ready"] is True


def test_default_llm_ready_unresolved_default_profile_stays_true():
    """Unknown default id mirrors runtime: literal-id fallback, different error path."""
    config = {"settings": {"default_llm_profile": "does-not-exist"}, "llm": {}}
    assert settings_public_payload(config)["default_llm_ready"] is True


def test_default_llm_ready_env_template_default_fallback(monkeypatch):
    monkeypatch.delenv("TEST_LLM_KEY_207_ABSENT", raising=False)
    config = _llm_config(
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": "${TEST_LLM_KEY_207_ABSENT:-sk-fallback}",
        }
    )
    assert settings_public_payload(config)["default_llm_ready"] is True


def test_catalog_marks_namespace_and_api_picker_excludes_foreign_ids():
    """An API seat may only be offered API-namespace LLM profiles.

    The ``/v1/llm-profiles/`` payload is one mixed catalog (API profiles +
    connected CLI agents + live CLI model ids + remotes). Each row carries a
    ``namespace`` so the API Model control filters to ``api`` only.
    """
    from swarm.core.llm_task_routing import collect_catalog, namespace_for_source

    config = {
        "llm": {"auxiliary": {"provider": "openai", "model": "gpt-4o-mini"}},
        "cli_agents": {"agy": {"cmd": ["agy"]}},
        "remotes": {
            "hermes": {"base_url": "http://127.0.0.1:8802", "models": ["hermes-fast"]}
        },
    }
    entries = collect_catalog(
        config,
        discovery_payloads=[{"cli": "opencode", "models": ["opencode-go/deepseek-v4.1-flash"]}],
    )
    by_id = {entry.id: entry for entry in entries}
    assert by_id["auxiliary"].namespace == "api"
    assert by_id["gpt-4o-mini"].namespace == "api"
    assert by_id["agy"].namespace == "cli"
    assert by_id["hermes"].namespace == "remote"
    assert by_id["hermes-fast"].namespace == "remote"
    assert by_id["opencode-go/deepseek-v4.1-flash"].namespace == "cli"

    profiles = [entry.public_dict() for entry in entries]
    api_ids = {row["id"] for row in profiles if row["namespace"] == "api"}
    assert api_ids == {"auxiliary", "gpt-4o-mini"}
    # The foreign namespaces are exactly CLI agents / live CLI models / remotes.
    assert namespace_for_source("config") == "api"
    assert namespace_for_source("cli") == "cli"
    assert namespace_for_source("list_models") == "cli"
    assert namespace_for_source("remote") == "remote"


def test_mistral_profile_is_api_namespace_in_catalog():
    # #1325: a hand-written mistral profile must surface in /v1/llm-profiles/
    # as an API-namespace row (never a CLI id) and never echo a key.
    from swarm.core.llm_task_routing import collect_catalog

    config = {
        "llm": {
            "mistral": {
                "provider": "mistral",
                "model": "mistral-large-latest",
                "base_url": "https://api.mistral.ai/v1",
                "api_key": "sk-secret-must-not-leak",
            }
        }
    }
    entries = collect_catalog(config)
    by_id = {entry.id: entry for entry in entries}
    assert by_id["mistral"].namespace == "api"
    assert by_id["mistral"].base_url == "https://api.mistral.ai/v1"
    assert "api_key" not in by_id["mistral"].public_dict()
    assert "sk-secret" not in json.dumps(
        [entry.public_dict() for entry in entries]
    )


# --- #1745 — System1 is a first-class model type, never a chat pick ---


def _system1_config() -> dict:
    """A chat model + a System1 gate. Env placeholders only, no credentials."""
    return {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "${OPENAI_API_KEY}",
            },
            "system1-filter": {
                "provider": "system1",
                "model": "system1-categorizer",
                "model_type": "categorizer",
                "base_url": "${SYSTEM1_BASE_URL}",
                "api_key": "${SYSTEM1_API_KEY}",
            },
        },
        "settings": {"default_llm_profile": "default"},
    }


def test_model_type_for_profile_reads_key_legacy_type_and_vendor():
    from swarm.core.llm_task_routing import model_type_for_profile

    assert model_type_for_profile({"provider": "openai"}) == "chat"
    assert model_type_for_profile({"model_type": "categorizer"}) == "categorizer"
    assert model_type_for_profile({"model_type": "System1"}) == "categorizer"
    # The legacy ``type`` spelling is still readable.
    assert model_type_for_profile({"type": "categorizer"}) == "categorizer"
    # A System1 vendor is a categorizer even when the key was never written.
    assert model_type_for_profile({"provider": "system1"}) == "categorizer"
    assert model_type_for_profile({"provider": "system-1"}) == "categorizer"
    # An explicit type outranks the vendor.
    assert model_type_for_profile({"provider": "system1", "model_type": "chat"}) == "chat"
    assert model_type_for_profile(None) == "chat"


def test_catalog_marks_system1_rows_as_categorizer():
    """System1 shows up in the Settings catalog, badged with its type."""
    from swarm.core.llm_task_routing import collect_catalog

    entries = collect_catalog(_system1_config())
    by_id = {entry.id: entry for entry in entries}
    assert by_id["system1-filter"].model_type == "categorizer"
    assert by_id["system1-filter"].is_categorizer is True
    # The model-id row carries the same type — a rename must not lose the badge.
    assert by_id["system1-categorizer"].model_type == "categorizer"
    assert by_id["default"].model_type == "chat"
    assert by_id["gpt-4o-mini"].model_type == "chat"
    assert by_id["default"].is_categorizer is False

    row = by_id["system1-filter"].public_dict()
    assert row["model_type"] == "categorizer"
    assert row["namespace"] == "api"
    # The ${SYSTEM1_API_KEY} placeholder is a credential reference, never a value.
    assert "api_key" not in row


def test_auto_pick_never_selects_a_system1_categorizer():
    from swarm.core.llm_task_routing import collect_catalog, model_type_for_profile

    entries = collect_catalog(_system1_config())
    by_id = {entry.id: entry for entry in entries}
    auto = auto_pick_task_models(entries)
    picked = set(auto.picks.values()) | {auto.default}
    assert "system1-filter" not in picked
    assert "system1-categorizer" not in picked
    # Every pick is a chat model — the type, not the id, is the guarantee.
    for name in picked:
        assert by_id[name].model_type == "chat"
    # The exclusion is visible, not silent.
    assert any("System1" in warning for warning in auto.warnings)


def test_auto_pick_of_only_categorizers_warns_and_falls_back():
    from swarm.core.llm_task_routing import collect_catalog

    config = {
        "llm": {
            "system1-filter": {
                "provider": "system1",
                "model": "system1-categorizer",
            }
        }
    }
    auto = auto_pick_task_models(collect_catalog(config))
    assert auto.default == BUILTIN_FALLBACK
    assert auto.picks[TASK_CLASS_ORCHESTRATION] == BUILTIN_FALLBACK
    assert any("System1" in warning for warning in auto.warnings)


def test_stored_default_system1_falls_back_to_a_chat_model():
    """A gate stored as the default must not leave chat unroutable."""
    config = _system1_config()
    config["settings"]["default_llm_profile"] = "system1-filter"
    default, warnings = effective_default_profile(config)
    assert default != "system1-filter"
    assert any("System1" in warning for warning in warnings)

    payload = settings_public_payload(config)
    assert payload["default_llm_profile"] == default
    assert "system1-filter" not in payload["auto_picks"].values()
    assert payload["routes"][TASK_CLASS_ORCHESTRATION]["model_type"] == "chat"
    by_id = {row["id"]: row for row in payload["profiles"]}
    assert by_id[default]["model_type"] == "chat"


def test_task_map_never_routes_a_chat_class_to_a_categorizer():
    from swarm.core.llm_task_routing import resolve_chat_model

    config = _system1_config()
    config["settings"]["override_per_task"] = True
    config["settings"]["task_llm_profiles"] = {
        "orchestration": "system1-filter",
        "auxiliary": "system1-filter",
        "delegation": "system1-filter",
    }
    for cls in (TASK_CLASS_ORCHESTRATION, TASK_CLASS_AUXILIARY, TASK_CLASS_DELEGATION):
        route = resolve_for_task(cls, config)
        assert route.profile != "system1-filter"
        assert route.model_type == "chat"
        assert route.used_fallback is True
        assert "System1" in (route.warning or "")

    # …and the chat resolver agrees.
    assert resolve_chat_model(config).model_type == "chat"
    assert resolve_chat_model(config).profile != "system1-filter"


def test_persist_named_llm_profile_round_trips_model_type(tmp_path: Path):
    config_path = tmp_path / "swarm_config.json"
    config_path.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")

    cfg, _path = persist_named_llm_profile(
        profile_id="system1-filter",
        spec={
            "provider": "system1",
            "model": "system1-categorizer",
            "model_type": "System1",
            "base_url": "${SYSTEM1_BASE_URL}",
            "api_key": "${SYSTEM1_API_KEY}",
        },
        config_path=config_path,
    )
    stored = cfg["llm"]["system1-filter"]
    assert stored["model_type"] == "categorizer"
    assert stored["api_key"] == "${SYSTEM1_API_KEY}"
    raw = json.loads(config_path.read_text(encoding="utf-8"))
    assert raw["llm"]["system1-filter"]["model_type"] == "categorizer"
    assert "sk-" not in config_path.read_text(encoding="utf-8")

    # The legacy ``type`` key is normalised to ``model_type`` on the way in.
    cfg2, _ = persist_named_llm_profile(
        profile_id="legacy-gate",
        spec={"provider": "openai", "model": "gpt-4o-mini", "type": "categorizer"},
        config_path=config_path,
    )
    assert cfg2["llm"]["legacy-gate"]["model_type"] == "categorizer"
    assert "type" not in cfg2["llm"]["legacy-gate"]

    # A chat profile records chat, so the type is never implied.
    cfg3, _ = persist_named_llm_profile(
        profile_id="chat-only",
        spec={"provider": "openai", "model": "gpt-4o-mini"},
        config_path=config_path,
    )
    assert cfg3["llm"]["chat-only"]["model_type"] == "chat"


def test_system1_provider_without_type_key_is_still_a_categorizer(tmp_path: Path):
    """A hand-written ``provider: system1`` profile needs no hidden type key."""
    from swarm.core.llm_task_routing import collect_catalog

    config_path = tmp_path / "swarm_config.json"
    config_path.write_text(json.dumps({"llm": {}, "settings": {}}), encoding="utf-8")
    cfg, _ = persist_named_llm_profile(
        profile_id="system1-filter",
        spec={"provider": "system1", "model": "system1-categorizer"},
        config_path=config_path,
    )
    assert "model_type" not in cfg["llm"]["system1-filter"] or (
        cfg["llm"]["system1-filter"]["model_type"] == "categorizer"
    )
    entries = collect_catalog(cfg)
    by_id = {entry.id: entry for entry in entries}
    assert by_id["system1-filter"].model_type == "categorizer"


def test_settings_public_payload_exposes_the_model_type_axis():
    payload = settings_public_payload(_system1_config())
    assert payload["model_types"] == ["chat", "categorizer"]
    by_id = {row["id"]: row for row in payload["profiles"]}
    assert by_id["system1-filter"]["model_type"] == "categorizer"
    assert by_id["default"]["model_type"] == "chat"
    # Routes carry the resolved type so the SPA never renders a gate as chat.
    for route in payload["routes"].values():
        assert route["model_type"] in {"chat", "categorizer"}
    assert "api_key" not in json.dumps(payload)
    assert "${SYSTEM1_API_KEY}" not in json.dumps(payload)

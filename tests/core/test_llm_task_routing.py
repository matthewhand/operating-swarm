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
    persist_llm_settings,
    resolve_design_model,
    resolve_for_task,
    resolve_summary_model,
    settings_public_payload,
)


# Mixed boring gateway ids — no secrets.
BORING_FIXTURE = ("gpt-4o-mini", "gpt-5.6-terra", "o3")


def test_mixed_boring_ids_map_to_three_distinct_classes():
    result = auto_pick_task_models(BORING_FIXTURE)
    assert result.picks[TASK_CLASS_AUXILIARY] == "gpt-4o-mini"
    assert result.picks[TASK_CLASS_ORCHESTRATION] == "gpt-5.6-terra"
    assert result.picks[TASK_CLASS_DELEGATION] == "o3"
    assert len(set(result.picks.values())) == 3
    assert result.default == "gpt-5.6-terra"
    assert result.aliases_used == []


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

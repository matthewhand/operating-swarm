"""API and CLI model ids are different namespaces (REQ-171C-3 / #612).

A per-request model pinned onto a CLI adapter must come from that CLI's own
model list (cached live probe or catalog presets). An API / LLM-profile id
such as ``litellm/orchestration`` must never reach ``agy --model`` — the seat
keeps its configured model.
"""

from __future__ import annotations

import pytest

from swarm.blueprints.common import cli_fusion_support as support
from swarm.core import cli_catalog, cli_models
from swarm.core.cli_models import ListModelsResult, _remember, clear_probe_cache


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_probe_cache()
    yield
    clear_probe_cache()


def test_preset_model_is_allowed_for_agy():
    assert support.model_allowed_for_cli("agy", "gemini-3.8-flash-high") is True
    assert support.model_allowed_for_cli("agy", "claude-sonnet-4-6") is True


def test_api_namespace_model_is_foreign_to_agy():
    # litellm/openai are API / LLM-profile namespaces agy never exposes.
    assert support.model_allowed_for_cli("agy", "litellm/orchestration") is False
    assert support.model_allowed_for_cli("agy", "openai/gpt-4o") is False
    # An arbitrary bare id not in agy's known set is foreign too.
    assert support.model_allowed_for_cli("agy", "definitely-not-an-agy-model") is False


def test_configured_model_is_always_allowed():
    assert (
        support.model_allowed_for_cli(
            "agy", "custom-seat-model", configured_model="custom-seat-model"
        )
        is True
    )


def test_blank_and_default_are_never_pinned():
    assert support.model_allowed_for_cli("agy", "") is False
    assert support.model_allowed_for_cli("agy", "default") is False


def test_provider_exposed_by_preset_is_allowed():
    # opencode's presets expose the opencode-go/ and litellm/ namespaces.
    assert support.model_allowed_for_cli("opencode", "litellm/orchestration") is True
    assert support.model_allowed_for_cli("opencode", "opencode-go/anything-new") is True


def test_unknown_cli_namespace_is_permissive():
    # No presets and nothing cached for pi -> the namespace is unknown, so an
    # id cannot be proven foreign (pi uses provider/id ids from its live list).
    assert support.model_allowed_for_cli("pi", "openai/gpt-4o") is True


def test_live_cached_model_is_allowed():
    _remember(ListModelsResult(cli="agy", models=["agy-live-model"]))
    assert support.model_allowed_for_cli("agy", "agy-live-model") is True
    # A cached live list does not make an API id valid.
    assert support.model_allowed_for_cli("agy", "litellm/orchestration") is False


def _agy_config():
    entry = cli_catalog.apply_model(
        cli_catalog.catalog_entry("agy"), "agy", "gemini-3.8-flash-high"
    )
    return {"cli_agents": {"agy": entry}}


def test_apply_overrides_ignores_api_model_for_agy():
    registry = support.apply_overrides(
        support.build_registry(_agy_config()),
        {"cli": "agy", "model": "litellm/orchestration"},
    )
    cmd = registry.get("agy").config.cmd
    assert "litellm/orchestration" not in cmd
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-high"


def test_apply_overrides_applies_valid_agy_preset():
    registry = support.apply_overrides(
        support.build_registry(_agy_config()),
        {"cli": "agy", "model": "claude-sonnet-4-6"},
    )
    cmd = registry.get("agy").config.cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet-4-6"


def test_apply_overrides_applies_live_agy_model():
    _remember(ListModelsResult(cli="agy", models=["agy-live-model"]))
    registry = support.apply_overrides(
        support.build_registry(_agy_config()),
        {"cli": "agy", "model": "agy-live-model"},
    )
    cmd = registry.get("agy").config.cmd
    assert cmd[cmd.index("--model") + 1] == "agy-live-model"


def test_mistral_prefix_accepted_only_when_cli_exposes_it():
    # #1325: mistral/mistralai are API-provider prefixes. A CLI that demonstrably
    # exposes the prefix (live list or preset) may pin it...
    _remember(ListModelsResult(cli="agy", models=["mistral/mistral-large-latest"]))
    assert support.model_allowed_for_cli("agy", "mistral/mistral-large-latest") is True
    # ...but a recognised API provider the CLI never exposed stays foreign.
    assert support.model_allowed_for_cli("agy", "mistralai/mistral-large-latest") is False
    # The alias spelling is honoured when the CLI's own list exposes it.
    _remember(ListModelsResult(cli="opencode", models=["mistralai/mistral-large-latest"]))
    assert support.model_allowed_for_cli("opencode", "mistralai/mistral-large-latest") is True


def test_cached_models_is_keyed_per_cli():
    _remember(ListModelsResult(cli="agy", models=["agy-a"]))
    _remember(ListModelsResult(cli="opencode", models=["opencode-b"]))
    assert cli_models.cached_models("agy") == ["agy-a"]
    assert cli_models.cached_models("opencode") == ["opencode-b"]
    assert cli_models.cached_models("grok") == []

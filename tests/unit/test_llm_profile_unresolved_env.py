"""A ``${NAME}`` that never got substituted must not reach a provider client.

``os.path.expandvars`` leaves an unknown reference untouched, so a profile like
``{"base_url": "${LITELLM_BASE_URL}"}`` used to hand a *literal* placeholder to
``AsyncOpenAI``. That literal is a perfectly valid string, so nothing rejected it
until a request was made — where it surfaced as an opaque URL/auth error that
never named the variable. Observed live: a dev stack whose ``swarm_config.json``
used ``${LITELLM_BASE_URL}`` / ``${LITELLM_API_KEY}`` aborted the chat WebSocket
with ``OpenAIError: The api_key client option must be set``.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

import pytest

from swarm.core.blueprint_base import BlueprintBase
from swarm.core.config_loader import (
    drop_unresolved_env_values,
    get_resolved_llm_profile,
    unresolved_env_placeholders,
)


class _TinyBlueprint(BlueprintBase):
    metadata: ClassVar[dict[str, Any]] = {
        "name": "unresolved_env_stub",
        "title": "Stub",
        "description": "test stub",
        "env_vars": [],
    }

    async def create_agents(self):
        return {}

    async def run(self, messages, **kwargs):
        if False:
            yield {}


def _placeholder_config() -> dict:
    return {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": "${LITELLM_BASE_URL}",
                "api_key": "${LITELLM_API_KEY}",
            }
        },
        "settings": {"default_llm_profile": "default"},
    }


@pytest.fixture
def unset_litellm_env(monkeypatch):
    """Hermetic: the placeholders under test resolve only if these are set."""
    for name in ("LITELLM_BASE_URL", "LITELLM_API_KEY", "OPENAI_BASE_URL", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_unresolved_env_placeholders_walks_strings_lists_and_dicts():
    value = {
        "api_key": "${A_KEY}",
        "nested": {"base_url": "${B_URL}"},
        "list": ["${C_URL}", "plain", 7],
    }
    assert unresolved_env_placeholders(value) == ["A_KEY", "B_URL", "C_URL"]


def test_unresolved_env_placeholders_ignores_unbraced_dollars_in_secrets():
    """Only the braced form is matched, so a literal key cannot false-positive."""
    assert unresolved_env_placeholders("sk-live$abcDEF") == []
    assert unresolved_env_placeholders("sk-live${NOT_A_VAR") == []


def test_drop_unresolved_env_values_reports_names_and_removes_keys():
    cleaned, missing = drop_unresolved_env_values(
        {"model": "gpt-4o-mini", "api_key": "${K}", "base_url": "https://gw/v1"}
    )
    assert missing == ["K"]
    assert "api_key" not in cleaned
    assert cleaned["base_url"] == "https://gw/v1"
    assert cleaned["model"] == "gpt-4o-mini"


def test_drop_unresolved_env_values_catches_a_placeholder_inside_a_url():
    cleaned, missing = drop_unresolved_env_values({"base_url": "${SWARM_HOST}/v1"})
    assert missing == ["SWARM_HOST"]
    assert "base_url" not in cleaned


def test_resolver_drops_placeholders_and_names_the_variables(unset_litellm_env, monkeypatch):
    # ``swarm.config`` has its own handler with propagate off, so capture the
    # call rather than relying on caplog (same idiom as tests/blueprints).
    warned: list[str] = []
    original = logging.Logger.warning

    def _capture(self, msg, *args, **kwargs):
        warned.append(msg % args if args else str(msg))
        return original(self, msg, *args, **kwargs)

    monkeypatch.setattr(logging.Logger, "warning", _capture)
    resolved = get_resolved_llm_profile(_placeholder_config(), "default")

    assert resolved["model"] == "gpt-4o-mini"
    assert "api_key" not in resolved
    assert "base_url" not in resolved

    warnings = "\n".join(warned)
    assert "LITELLM_BASE_URL" in warnings
    assert "LITELLM_API_KEY" in warnings


def test_resolver_substitutes_the_values_when_the_env_is_set(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL", "http://127.0.0.1:4000/v1")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-master")

    resolved = get_resolved_llm_profile(_placeholder_config(), "default")

    assert resolved["base_url"] == "http://127.0.0.1:4000/v1"
    assert resolved["api_key"] == "sk-master"


def test_resolver_leaves_literal_values_untouched():
    config = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
                "api_key": "sk-test",
            }
        }
    }
    resolved = get_resolved_llm_profile(config, "default")
    assert resolved["base_url"] == "https://api.openai.com/v1"
    assert resolved["api_key"] == "sk-test"


def test_resolver_deliberately_keeps_a_placeholder_model():
    """Documented scope: only api_key/base_url are dropped.

    A bad ``model`` fails at request time with the model name quoted back, so it
    already names the offending value — dropping it to ``None`` would replace a
    clear error with a vaguer one.
    """
    config = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "${DEFAULT_LLM}",
                "api_key": "sk-test",
            }
        }
    }
    assert get_resolved_llm_profile(config, "default")["model"] == "${DEFAULT_LLM}"


def test_model_instance_never_hands_a_placeholder_to_the_client(unset_litellm_env, monkeypatch):
    """The end that matters: these values must not become client kwargs."""
    captured: dict[str, Any] = {}

    class _Client:
        def __init__(self, **kwargs):
            captured["kwargs"] = kwargs

    class _Model:
        def __init__(self, model, openai_client):
            captured["model"] = model

    import openai

    monkeypatch.setattr(openai, "AsyncOpenAI", _Client)
    monkeypatch.setattr(
        "agents.models.openai_chatcompletions.OpenAIChatCompletionsModel", _Model
    )

    bp = _TinyBlueprint(blueprint_id="unresolved_env_stub", config=_placeholder_config())
    bp._get_model_instance("default")

    # No bogus URL, and no placeholder masquerading as a key — omitting api_key
    # also lets the SDK's own OPENAI_API_KEY lookup apply.
    assert "base_url" not in captured["kwargs"]
    assert "api_key" not in captured["kwargs"]
    assert captured["model"] == "gpt-4o-mini"

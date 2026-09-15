"""Honor blueprints[].default_model and warn on unknown profile fallback."""
from __future__ import annotations

import logging
from typing import Any, ClassVar

from swarm.core.blueprint_base import BlueprintBase


class _TinyBlueprint(BlueprintBase):
    metadata: ClassVar[dict[str, Any]] = {
        "name": "rue_code",
        "title": "Rue",
        "description": "test stub",
        "env_vars": [],
    }

    async def create_agents(self):
        return {}

    async def run(self, messages, **kwargs):
        if False:
            yield {}


def _bp(config: dict) -> _TinyBlueprint:
    bp = _TinyBlueprint(blueprint_id="rue_code", config=config)
    if hasattr(bp, "_resolved_llm_profile"):
        del bp._resolved_llm_profile
    return bp


def test_blueprint_default_model_selects_named_llm_profile():
    config = {
        "llm": {
            "default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
            "o3-mini": {"provider": "openrouter", "model": "openrouter/o3-mini", "api_key": "k"},
        },
        "settings": {"default_llm_profile": "default"},
        "blueprints": {"rue_code": {"default_model": "o3-mini"}},
    }
    assert _bp(config)._resolve_llm_profile() == "o3-mini"


def test_settings_default_llm_profile_used_when_blueprint_has_no_model():
    config = {
        "llm": {
            "default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
            "gpt-4o": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
        },
        "settings": {"default_llm_profile": "gpt-4o"},
        # Presence of blueprints must not skip settings (former elif bug).
        "blueprints": {"rue_code": {"description": "no model override"}},
    }
    assert _bp(config)._resolve_llm_profile() == "gpt-4o"


def test_unknown_default_model_warns_and_falls_back(monkeypatch):
    config = {
        "llm": {
            "default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
            "gpt-4o": {"provider": "openai", "model": "gpt-4o", "api_key": "k"},
        },
        "settings": {"default_llm_profile": "gpt-4o"},
        "blueprints": {"rue_code": {"default_model": "notarealmodel"}},
    }
    warned: list[str] = []
    original = logging.Logger.warning

    def _capture(self, msg, *args, **kwargs):
        warned.append(msg % args if args else str(msg))
        return original(self, msg, *args, **kwargs)

    monkeypatch.setattr(logging.Logger, "warning", _capture)
    selected = _bp(config)._resolve_llm_profile()
    assert selected == "gpt-4o"
    assert any("notarealmodel" in w and "falling back" in w.lower() for w in warned)


def test_unknown_default_model_falls_back_to_default_when_settings_missing(monkeypatch):
    config = {
        "llm": {"default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"}},
        "blueprints": {"rue_code": {"default_model": "missing-profile"}},
    }
    warned: list[str] = []
    original = logging.Logger.warning

    def _capture(self, msg, *args, **kwargs):
        warned.append(msg % args if args else str(msg))
        return original(self, msg, *args, **kwargs)

    monkeypatch.setattr(logging.Logger, "warning", _capture)
    selected = _bp(config)._resolve_llm_profile()
    assert selected == "default"
    assert any("missing-profile" in w for w in warned)


def test_unspecified_profile_still_defaults_quietly(monkeypatch, tmp_path):
    """No named request → builtin default without a missing-profile warning."""
    # Hermeticity: the resolver's global-file fallback reads cwd and ~/.config,
    # so a developer's real swarm_config.json (default_llm_profile=orchestration)
    # would leak into this test. Pin HOME/cwd to an empty temp dir.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    config = {
        "llm": {"default": {"provider": "openai", "model": "gpt-4o", "api_key": "k"}},
        "blueprints": {},
    }
    warned: list[str] = []
    original = logging.Logger.warning

    def _capture(self, msg, *args, **kwargs):
        warned.append(msg % args if args else str(msg))
        return original(self, msg, *args, **kwargs)

    monkeypatch.setattr(logging.Logger, "warning", _capture)
    monkeypatch.delenv("DEFAULT_LLM", raising=False)
    selected = _bp(config)._resolve_llm_profile()
    assert selected == "default"
    assert not any("not found" in w.lower() and "falling back" in w.lower() for w in warned)

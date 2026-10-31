"""Unit tests for the CliDeliberationBase shared strategy base class."""

from __future__ import annotations

import pytest

from swarm.blueprints.common.cli_deliberation_base import CliDeliberationBase
from swarm.core.cli_adapter import CliAdapterRegistry


class DummyDeliberation(CliDeliberationBase):
    """Concrete subclass for testing deliberation base mechanics."""

    def __init__(self, blueprint_id="dummy_strategy", config=None):
        super().__init__(blueprint_id, config=config)

    async def run(self, messages, **kwargs):
        prompt, registry, workdir, err = self.prepare_deliberation(messages)
        if err:
            yield err
            return
        yield {"role": "assistant", "content": f"Ready: {prompt} in {workdir}"}


def test_cli_deliberation_base_config_accessors():
    config = {
        "cli_fusion": {
            "default_cli": "claude",
            "default_preset": "triad",
            "presets": {
                "triad": {"panel": ["claude", "gemini", "codex"], "judge": "claude"}
            },
        },
        "dummy_strategy": {"max_depth": 5},
    }
    strat = DummyDeliberation("dummy_strategy", config=config)

    assert strat.get_default_cli() == "claude"
    assert strat.get_fusion_config()["default_preset"] == "triad"
    assert strat.get_fusion_preset()["judge"] == "claude"
    assert strat.get_fusion_preset()["panel"] == ["claude", "gemini", "codex"]
    assert strat.get_strategy_config()["max_depth"] == 5
    assert strat.get_strategy_config("dummy_strategy")["max_depth"] == 5


def test_cli_deliberation_base_bounded_int():
    config = {"dummy_strategy": {"max_depth": 7}}
    strat = DummyDeliberation("dummy_strategy", config=config)

    # 1. Fallback to config when params empty
    assert strat.bounded_int({}, "max_depth", default=3, max_val=10) == 7

    # 2. Params override config
    assert strat.bounded_int({"max_depth": 4}, "max_depth", default=3, max_val=10) == 4

    # 3. Clamped by max_val and min_val
    assert strat.bounded_int({"max_depth": 99}, "max_depth", default=3, max_val=10) == 10
    assert strat.bounded_int({"max_depth": -5}, "max_depth", default=3, max_val=10, min_val=2) == 2

    # 4. Invalid values fallback to default
    assert strat.bounded_int({"max_depth": "invalid"}, "max_depth", default=3, max_val=10) == 3
    assert strat.bounded_int({}, "missing_key", default=12, max_val=20) == 12


def test_cli_deliberation_base_prepare_empty_prompt():
    strat = DummyDeliberation("dummy_strategy")
    prompt, reg, wd, err = strat.prepare_deliberation([])
    assert prompt is None
    assert reg is None
    assert wd is None
    assert err is not None
    assert "No prompt provided" in err["messages"][0]["content"]


def test_cli_deliberation_base_prepare_workdir_escape(tmp_path):
    strat = DummyDeliberation("dummy_strategy")
    # Setting an illegal workdir escaping path traversal
    strat.set_params({"workdir": "../../../../etc"})
    messages = [{"role": "user", "content": "hello world"}]
    prompt, reg, wd, err = strat.prepare_deliberation(messages)
    assert prompt is None
    assert err is not None


def test_cli_deliberation_base_prepare_success(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_UNRESTRICTED_WORKDIR", "true")
    strat = DummyDeliberation("dummy_strategy")
    strat.set_params({"workdir": str(tmp_path)})
    messages = [{"role": "user", "content": "analyze this"}]
    prompt, reg, wd, err = strat.prepare_deliberation(messages)
    assert err is None
    assert prompt == "analyze this"
    assert isinstance(reg, CliAdapterRegistry)
    assert wd == str(tmp_path)

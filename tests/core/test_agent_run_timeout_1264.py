"""#1264 — configurable openai-agents LLM run timeout."""

from __future__ import annotations

from swarm.core.agent_run_timeout import DEFAULT_AGENT_RUN_TIMEOUT_S, agent_run_timeout


def test_default_is_lenient(monkeypatch):
    monkeypatch.delenv("SWARM_AGENT_LLM_TIMEOUT", raising=False)
    assert DEFAULT_AGENT_RUN_TIMEOUT_S == 600.0
    assert agent_run_timeout(None) == 600.0


def test_env_var_overrides_config(monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_LLM_TIMEOUT", "300")
    assert agent_run_timeout({"settings": {"agent_llm_timeout_s": 120}}) == 300.0


def test_config_setting_used_when_env_absent(monkeypatch):
    monkeypatch.delenv("SWARM_AGENT_LLM_TIMEOUT", raising=False)
    assert agent_run_timeout({"settings": {"agent_llm_timeout_s": 450}}) == 450.0


def test_invalid_or_nonpositive_falls_back(monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_LLM_TIMEOUT", "-5")
    assert agent_run_timeout(None) == 600.0
    monkeypatch.setenv("SWARM_AGENT_LLM_TIMEOUT", "nope")
    assert agent_run_timeout(None) == 600.0

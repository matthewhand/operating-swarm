"""Tests for BlueprintBase modular mixins: ApprovalMixin, MemoryMixin, and ConfigResolver."""

import pytest
from unittest.mock import MagicMock, patch

from swarm.core.approval_mixin import ApprovalMixin
from swarm.core.blueprint_base import (
    ApprovalMixin as ReexportedApprovalMixin,
    BlueprintBase,
    ConfigResolver as ReexportedConfigResolver,
    MemoryMixin as ReexportedMemoryMixin,
)
from swarm.core.config_resolver import ConfigResolver
from swarm.core.memory_mixin import MemoryMixin
from swarm.core.spinner import CodeySpinner


def test_reexports_match():
    """Verify that blueprint_base re-exports the exact mixin classes."""
    assert ApprovalMixin is ReexportedApprovalMixin
    assert MemoryMixin is ReexportedMemoryMixin
    assert ConfigResolver is ReexportedConfigResolver
    assert issubclass(BlueprintBase, ApprovalMixin)
    assert issubclass(BlueprintBase, MemoryMixin)
    assert issubclass(BlueprintBase, ConfigResolver)


class _ApprovalHost(ApprovalMixin):
    pass


def test_approval_mixin_disabled_by_default():
    host = _ApprovalHost()
    assert host.approval_required is False
    func = MagicMock(return_value="executed")
    result = host.execute_tool_with_approval(func, "action", "summary")
    assert result == "executed"
    func.assert_called_once()


def test_approval_mixin_approved():
    host = _ApprovalHost()
    host.approval_required = True
    func = MagicMock(return_value="done")
    with patch("builtins.input", return_value="yes"):
        result = host.execute_tool_with_approval(func, "test_action", "test_summary")
        assert result == "done"
        func.assert_called_once()


def test_approval_mixin_rejected():
    host = _ApprovalHost()
    host.approval_required = True
    func = MagicMock(return_value="done")
    with patch("builtins.input", return_value="no"):
        result = host.execute_tool_with_approval(func, "test_action", "test_summary")
        assert result is None
        func.assert_not_called()


class _MemoryHost(MemoryMixin):
    def __init__(self, bp_id="test_bp", config=None):
        self.blueprint_id = bp_id
        self._config = config or {}


def test_memory_mixin_no_config():
    host = _MemoryHost()
    assert host.memory_backend is None
    messages = [{"role": "user", "content": "hello"}]
    # Without memory configured, context is unchanged and store is a safe no-op
    assert host.inject_memory_context(messages) == messages
    host.store_run_memory(messages)


def test_memory_mixin_search_and_inject():
    host = _MemoryHost()
    mock_backend = MagicMock()
    mock_backend.search.return_value = ["User likes python", "Prefers dark mode"]
    host._memory_backend = mock_backend

    messages = [{"role": "user", "content": "What is my preference?"}]
    augmented = host.inject_memory_context(messages)
    assert len(augmented) == 2
    assert augmented[0]["role"] == "system"
    assert "User likes python" in augmented[0]["content"]
    assert augmented[1] == messages[0]


class _ConfigHost(ConfigResolver):
    def __init__(self, bp_id="test_bp", config=None):
        self.blueprint_id = bp_id
        self._config = config
        self._load_configuration()


def test_config_resolver_basic():
    cfg = {
        "llm": {
            "default": {
                "provider": "openai",
                "model": "gpt-4o-mini",
                "api_key": "test-key",
            }
        },
        "settings": {"default_llm_profile": "default", "default_markdown_output": True},
    }
    host = _ConfigHost(config=cfg)
    assert host.llm_profile_name == "default"
    assert host.should_output_markdown is True
    profile = host.llm_profile
    assert profile["model"] == "gpt-4o-mini"


def test_codey_spinner_shared_infra():
    """Verify CodeySpinner operates cleanly in core/spinner."""
    spinner = CodeySpinner()
    initial_state = spinner.current_spinner_state()
    assert initial_state in CodeySpinner.SPINNER_STATES
    spinner.start()
    spinner._spin()
    assert spinner.current_spinner_state() in CodeySpinner.SPINNER_STATES

"""#499 — the config-error banner must name the thing to configure.

"Agent configuration error" offered session reshuffles but no route to the
configuration. The backend classifies the failure **target** where it already
classifies the failure, and stamps it next to the persisted flag. A row with
the flag but no target must keep rendering today's banner (no regression).
"""

from __future__ import annotations

from swarm.core.cli_session_error import (
    FATAL_CONFIG_ERROR_KEY,
    fatal_config_error_extra,
)


def test_unconfigured_cli_copy_targets_cli_agents():
    extra = fatal_config_error_extra("No CLI agents are configured. Add a 'cli_agents' block.")
    assert extra == {
        FATAL_CONFIG_ERROR_KEY: True,
        "config_target": {"section": "cli-agents"},
    }


def test_no_cli_backend_copy_targets_cli_agents():
    extra = fatal_config_error_extra("no cli backend is configured")
    assert extra["config_target"] == {"section": "cli-agents"}


def test_unconfigured_harness_copy_targets_remotes():
    extra = fatal_config_error_extra("Remote harness endpoint not configured yet")
    assert extra == {
        FATAL_CONFIG_ERROR_KEY: True,
        "config_target": {"section": "remotes"},
    }


def test_resume_failure_is_fatal_without_target():
    """Resume failures are session problems — session actions ARE the fix."""
    extra = fatal_config_error_extra("[grok] failed: session not found")
    assert extra == {FATAL_CONFIG_ERROR_KEY: True}


def test_explicit_meta_flag_without_target_stays_bare():
    extra = fatal_config_error_extra("generic", {FATAL_CONFIG_ERROR_KEY: True})
    assert extra == {FATAL_CONFIG_ERROR_KEY: True}


def test_persisted_records_carry_the_target_through():
    """chat_store normalisation preserves config_target on rehydrate."""
    from swarm.core.chat_store import _normalize_messages

    record = {
        "role": "assistant",
        "content": "No CLI agents are configured.",
        FATAL_CONFIG_ERROR_KEY: True,
        "config_target": {"section": "cli-agents"},
    }
    [row] = _normalize_messages([record])
    assert row.get("config_target") == {"section": "cli-agents"}

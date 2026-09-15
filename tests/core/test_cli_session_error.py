"""REQ-879 / #274 — fatal CLI/config errors vs transient model faults."""

from __future__ import annotations

from swarm.core.cli_session_error import (
    FATAL_CONFIG_ERROR_KEY,
    fatal_config_error_extra,
    is_fatal_config_error,
    is_fatal_config_turn,
    is_uncontinued_fatal_init,
)


def test_unconfigured_cli_copy_is_fatal():
    text = "No CLI agents are configured. Add a 'cli_agents' block to your swarm config."
    assert is_fatal_config_error(text) is True
    assert fatal_config_error_extra(text) == {FATAL_CONFIG_ERROR_KEY: True}


def test_resume_failure_copy_is_fatal():
    assert is_fatal_config_error("[grok] failed: session not found") is True
    assert is_fatal_config_error("Cannot resume expired session") is True


def test_unconfigured_harness_copy_is_fatal():
    assert is_fatal_config_error("Remote harness endpoint not configured yet") is True
    assert is_fatal_config_error("ssh harness not configured") is True


def test_transient_model_errors_are_not_fatal_config():
    assert is_fatal_config_error("Error: the model returned no usable text") is False
    assert is_fatal_config_error("rate limit exceeded, retry later") is False
    assert fatal_config_error_extra("hello") == {}


def test_explicit_meta_flag_wins():
    assert is_fatal_config_error("generic", {FATAL_CONFIG_ERROR_KEY: True}) is True
    assert is_fatal_config_turn(
        {"role": "assistant", "content": "generic", FATAL_CONFIG_ERROR_KEY: True}
    )


def test_uncontinued_fatal_init_skips_history():
    poison = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "No CLI agents are configured.",
            FATAL_CONFIG_ERROR_KEY: True,
        },
    ]
    assert is_uncontinued_fatal_init(poison) is True


def test_user_continue_keeps_the_thread():
    continued = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "No CLI agents are configured.", FATAL_CONFIG_ERROR_KEY: True},
        {"role": "user", "content": "try again"},
    ]
    assert is_uncontinued_fatal_init(continued) is False


def test_successful_assistant_reply_is_history():
    ok = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert is_uncontinued_fatal_init(ok) is False
    assert is_uncontinued_fatal_init([]) is False

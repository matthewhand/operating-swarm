"""REQ-92 — CLI session notice sits immediately before the assistant turn."""

from __future__ import annotations

from swarm.core.chat_transcript import (
    insert_status_before_turn_assistant,
    is_cli_session_notice,
    is_new_cli_session_notice,
    new_cli_session_notice_if_needed,
    transcript_already_has_notice,
)


def test_notice_helpers_match_honest_copy():
    assert is_new_cli_session_notice("Started a new grok session.")
    assert is_cli_session_notice("Resumed opencode session.")
    assert is_cli_session_notice("Started a new opencode session on dev-gpu.lan:4096.")
    assert is_new_cli_session_notice("Started a new opencode session on dev-gpu.lan:4096.")
    assert not is_new_cli_session_notice("Resumed grok session.")
    assert not is_cli_session_notice("CLI: antigravity → grok")


def test_insert_puts_new_session_before_assistant():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out = insert_status_before_turn_assistant(
        messages,
        {"role": "status", "content": "Started a new grok session."},
    )
    assert [m["role"] for m in out] == ["user", "status", "assistant"]
    assert out[1]["content"] == "Started a new grok session."


def test_insert_skips_duplicate_new_session_line():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "status", "content": "Started a new grok session."},
    ]
    out = insert_status_before_turn_assistant(
        messages,
        {"role": "status", "content": "Started a new grok session."},
    )
    assert out == messages
    assert transcript_already_has_notice(messages, "Started a new grok session.")


def test_hop_notice_covers_prompt_time_new_session_line():
    """REQ-866: dropdown hop notice suppresses the short prompt-time line."""
    hop = (
        "Started a new grok session (antigravity → grok). "
        "No prior context to carry from antigravity."
    )
    before_send = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "status", "content": hop},
    ]
    after_send = [
        *before_send,
        {"role": "user", "content": "next"},
    ]
    assert transcript_already_has_notice(before_send, "Started a new grok session.")
    assert transcript_already_has_notice(after_send, "Started a new grok session.")
    assert not transcript_already_has_notice(after_send, "Started a new omp session.")
    carried = (
        "Started a new omp session (qwen → omp). Carried summary context (12 tokens)."
    )
    assert transcript_already_has_notice(
        [{"role": "status", "content": carried}, {"role": "user", "content": "hi"}],
        "Started a new omp session.",
    )


def test_dropdown_status_still_appends():
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    out = insert_status_before_turn_assistant(
        messages,
        {"role": "status", "content": "CLI: antigravity → grok"},
    )
    assert [m["role"] for m in out] == ["user", "assistant", "status"]


def test_new_session_notice_if_needed_skips_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    from swarm.core.cli_sessions import put_cli_session

    put_cli_session("u1", "cli_agent", "grok", "sid-1")
    assert (
        new_cli_session_notice_if_needed(
            blueprint_id="cli_agent",
            params={"cli": "grok", "agent": "cli_agent"},
            user_key="u1",
        )
        is None
    )


def test_new_session_notice_if_needed_announces_first_turn(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    assert (
        new_cli_session_notice_if_needed(
            blueprint_id="cli_agent",
            params={"cli": "grok", "agent": "cli_agent"},
            user_key="u1",
        )
        == "Started a new grok session."
    )
    assert (
        new_cli_session_notice_if_needed(
            blueprint_id="jeeves",
            params={},
            user_key="u1",
        )
        is None
    )

"""CLI session id capture, sanitization, and per-thread persistence (REQ-52)."""

from __future__ import annotations

from swarm.core import chat_store
from swarm.core.cli_adapter import CliResult
from swarm.core.cli_sessions import (
    extract_session_id,
    get_cli_session,
    is_resume_failure,
    is_resume_failure_text,
    put_cli_session,
    resolve_thread,
    sanitize_cli_session_id,
    session_notice_text,
)


def test_sanitize_keeps_id_shaped_tokens():
    assert sanitize_cli_session_id("8075bc20-afc5-439f-b281-1376e5785784")
    assert sanitize_cli_session_id("ses_2132323b6ffeuRlYHhPcU8DaZ6")
    assert sanitize_cli_session_id("thread.started-1")


def test_sanitize_rejects_secrets_and_assignments():
    assert sanitize_cli_session_id("sk-live-secret-key") is None
    assert sanitize_cli_session_id("gsk_abc123") is None
    assert sanitize_cli_session_id("ANTHROPIC_API_KEY=secret") is None
    assert sanitize_cli_session_id("Bearer tok") is None
    assert sanitize_cli_session_id({"token": "x"}) is None
    assert sanitize_cli_session_id("id with spaces") is None
    assert sanitize_cli_session_id("../etc/passwd") is None
    assert sanitize_cli_session_id("--help") is None
    assert sanitize_cli_session_id(".") is None
    assert sanitize_cli_session_id("..") is None


def test_extract_session_id_from_claude_shaped_json():
    raw = '{"type":"result","result":"hello","session_id":"aaa-bbb-ccc"}'
    assert extract_session_id(raw, [".session_id"]) == "aaa-bbb-ccc"


def test_extract_session_id_from_jsonl_last_wins():
    raw = (
        '{"type":"thread.started","thread_id":"old-id"}\n'
        '{"type":"result","session_id":"new-id"}\n'
    )
    assert extract_session_id(raw) == "new-id"


def test_extract_ignores_secret_looking_json():
    raw = '{"session_id":"sk-please-do-not-store"}'
    assert extract_session_id(raw) is None


def test_put_and_get_are_per_thread_and_cli(tmp_path):
    put_cli_session("u1", "cli_agent", "claude", "sid-claude", base_dir=tmp_path)
    put_cli_session("u1", "cli_agent", "grok", "sid-grok", base_dir=tmp_path)
    put_cli_session("u1", "other", "claude", "sid-other", base_dir=tmp_path)
    assert get_cli_session("u1", "cli_agent", "claude", base_dir=tmp_path) == "sid-claude"
    assert get_cli_session("u1", "cli_agent", "grok", base_dir=tmp_path) == "sid-grok"
    assert get_cli_session("u1", "other", "claude", base_dir=tmp_path) == "sid-other"
    record = chat_store.load("u1", "cli_agent", base_dir=tmp_path)
    assert record["cli_sessions"] == {"claude": "sid-claude", "grok": "sid-grok"}
    assert "sk-" not in str(record)


def test_put_rejects_secrets(tmp_path):
    assert put_cli_session("u1", "cli_agent", "claude", "sk-secret", base_dir=tmp_path) is None
    assert get_cli_session("u1", "cli_agent", "claude", base_dir=tmp_path) is None


def test_message_save_preserves_cli_sessions(tmp_path):
    put_cli_session("u1", "cli_agent", "echo", "sid-1", base_dir=tmp_path)
    chat_store.save(
        "u1",
        "cli_agent",
        [{"role": "user", "content": "hi"}],
        base_dir=tmp_path,
    )
    assert get_cli_session("u1", "cli_agent", "echo", base_dir=tmp_path) == "sid-1"


def test_resolve_thread_prefers_user_and_agent():
    assert resolve_thread(
        {"user_key": "u9", "agent": "cli_agent", "conversation_id": "other"},
        default_agent="cli_agent",
    ) == ("u9", "cli_agent")
    assert resolve_thread({"conversation_id": "conv-1"}, default_agent="cli_agent") == (
        "_api",
        "conv-1",
    )
    assert resolve_thread({}, default_agent="cli_agent") is None


def test_resume_failure_detects_missing_session():
    miss = CliResult(name="c", ok=False, text="", error="No conversation found with session ID")
    ok = CliResult(name="c", ok=True, text="hi")
    other = CliResult(name="c", ok=False, text="", error="model overloaded")
    assert is_resume_failure(miss) is True
    assert is_resume_failure(ok) is False
    assert is_resume_failure(other) is False
    assert is_resume_failure_text("session not found") is True
    assert is_resume_failure_text("model overloaded") is False


def test_session_notice_is_honest():
    assert "Restored" not in session_notice_text("claude", resumed=False)
    assert session_notice_text("claude", resumed=False) == "Started a new claude session."
    assert session_notice_text("claude", resumed=True) == "Resumed claude session."

"""REQ-171C-6 / C-H8: treat CLI prompts and session ids as untrusted argv."""

from __future__ import annotations

from swarm.core import agent_settings as settings_store
from swarm.core import session_policy as policy
from swarm.core.cli_adapter import (
    CliAdapter,
    _apply_tokens,
    _protect_prompt_argv,
)
from swarm.core.cli_catalog import catalog_entry
from swarm.core.cli_sessions import sanitize_cli_session_id


def test_apply_tokens_does_not_substitute_inside_prompt():
    workdir = "/tmp/safe-workdir"
    assert _apply_tokens("{prompt}", "see {workdir}", workdir) == "see {workdir}"
    assert _apply_tokens("cwd:{workdir}", "see {workdir}", workdir) == f"cwd:{workdir}"
    assert (
        _apply_tokens("p={prompt}", "keep {workdir} literal", workdir)
        == "p=keep {workdir} literal"
    )


def test_apply_tokens_does_not_substitute_inside_workdir():
    assert _apply_tokens("{workdir}", "ignored", "/tmp/{prompt}/x") == "/tmp/{prompt}/x"
    assert (
        _apply_tokens("{prompt}-{workdir}", "{workdir}", "{prompt}")
        == "{workdir}-{prompt}"
    )


def test_positional_flag_shaped_prompt_is_not_a_flag():
    adapter = CliAdapter.from_config(
        "opencode",
        {"cmd": ["opencode", "run", "{prompt}", "--model", "litellm/orchestration"]},
    )
    argv, stdin = adapter._build_invocation("--model evil", "/tmp/proj")
    assert stdin is None
    assert argv[0] == "opencode"
    assert "--model" in argv
    assert argv[argv.index("--model") + 1] == "litellm/orchestration"
    dash = argv.index("--")
    assert argv[dash + 1] == "--model evil"
    assert "--model" not in argv[dash + 1 :]
    assert argv.count("--model evil") == 1


def test_catalog_positional_prompts_keep_flag_shaped_text_after_end_marker():
    for name in ("opencode", "codex", "pi"):
        adapter = CliAdapter.from_config(name, catalog_entry(name))
        argv, _ = adapter._build_invocation("--model evil", "/tmp/proj")
        assert "--" in argv, name
        assert argv[argv.index("--") + 1] == "--model evil"
        assert argv[-1] == "--model evil"


def test_print_flag_attaches_flag_shaped_prompt():
    adapter = CliAdapter.from_config("grok", {"cmd": ["grok", "-p", "{prompt}"]})
    argv, _ = adapter._build_invocation("--model evil", "/tmp")
    assert argv == ["grok", "-p=--model evil"]
    assert "--model" not in argv


def test_catalog_attached_print_flag_keeps_prompt_off_the_flag_list():
    adapter = CliAdapter.from_config("grok", catalog_entry("grok"))
    argv, _ = adapter._build_invocation("--model evil", "/tmp")
    assert any(part == "-p=--model evil" for part in argv)
    assert "--model" not in argv
    assert "--model evil" not in argv


def test_prompt_workdir_token_stays_literal_in_invocation():
    adapter = CliAdapter.from_config(
        "echo",
        {"cmd": ["echo", "{prompt}"], "env": {"NOTE": "user:{prompt}"}},
    )
    argv, _ = adapter._build_invocation("see {workdir}", "/tmp/real-cwd")
    assert argv == ["echo", "see {workdir}"]
    env = adapter._build_env("see {workdir}", "/tmp/real-cwd", None)
    assert env["NOTE"] == "user:see {workdir}"


def test_protect_prompt_argv_leaves_innocent_positional_in_place():
    argv = _protect_prompt_argv(
        ["python", "-c", "print(1)", "{prompt}"], "hello world", "/tmp"
    )
    assert argv == ["python", "-c", "print(1)", "hello world"]


def test_stdin_mode_does_not_put_prompt_on_argv():
    adapter = CliAdapter.from_config(
        "cat", {"cmd": ["cat"], "prompt_mode": "stdin"}
    )
    argv, stdin = adapter._build_invocation("--model evil", "/tmp")
    assert argv == ["cat"]
    assert stdin == b"--model evil"


def test_sanitize_rejects_leading_dash_dot_and_dotdot():
    assert sanitize_cli_session_id("--help") is None
    assert sanitize_cli_session_id("-r") is None
    assert sanitize_cli_session_id(".") is None
    assert sanitize_cli_session_id("..") is None
    assert sanitize_cli_session_id(".hidden") is None
    assert sanitize_cli_session_id("sess-keep") == "sess-keep"
    assert sanitize_cli_session_id("8075bc20-afc5-439f-b281-1376e5785784")


def test_resume_cli_session_id_sanitizes_stored_and_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(tmp_path / "agent_settings.json"))
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    settings_store.reset_agent_settings_cache()
    policy.clear_active_sessions()
    settings_store.update_settings("reuse", {"new_chat_per_task": False})
    settings_store.set_cli_session_id("reuse", "--help")
    assert policy.resume_cli_session_id("reuse") is None
    assert policy.resume_cli_session_id("reuse", stored="--help") is None
    assert policy.resume_cli_session_id("reuse", stored="..") is None
    assert policy.resume_cli_session_id("reuse", stored="sess-keep") == "sess-keep"
    settings_store.set_cli_session_id("reuse", "sess-keep")
    # Settings cli_session_id alone does not resume (C-H7 / #613).
    assert policy.resume_cli_session_id("reuse") is None
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path / "chats"))
    from swarm.core.cli_sessions import put_cli_session

    put_cli_session("u1", "reuse", "reuse", "sess-keep")
    assert policy.resume_cli_session_id("reuse", user_key="u1") == "sess-keep"
    settings_store.reset_agent_settings_cache()
    policy.clear_active_sessions()


def test_build_invocation_drops_flag_shaped_session_id():
    adapter = CliAdapter.from_config(
        "echo",
        {
            "cmd": ["echo", "{prompt}"],
            "resume_argv": ["--resume", "{session_id}"],
            "resume_insert": 1,
        },
    )
    argv, _ = adapter._build_invocation("hi", "/tmp", session_id="--help")
    assert "--resume" not in argv
    assert "--help" not in argv
    argv_ok, _ = adapter._build_invocation("hi", "/tmp", session_id="sess-123")
    assert argv_ok[1:3] == ["--resume", "sess-123"]

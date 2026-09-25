"""#1178 — the hermes driver's argv matches the installed hermes CLI.

Live sweep (2026-09-25): the driver built ``hermes run --prompt <p>``, but the
installed hermes (v0.21.0) has no ``run`` subcommand — non-interactive turns
are ``hermes chat -q <prompt> --oneshot --cli``. The old argv died with
"invalid choice: 'run'" on every hermes seat turn.

Also pinned: stdin must be inherited/closed explicitly by the caller, not an
open pipe — qwen's CLI waits on stdin forever when a pipe is left open
(observed as a 170s HANG in the same sweep), so the driver documents the
contract the exec path must honor.
"""

from __future__ import annotations

from swarm.core.cli_registry import get_driver


def test_hermes_exec_argv_matches_installed_cli():
    driver = get_driver("hermes")
    assert driver is not None
    argv = driver.build_exec_argv("Reply with exactly: PING")
    assert argv[0] == "hermes"
    assert "run" not in argv, "installed hermes has no `run` subcommand"
    assert "chat" in argv
    assert "-q" in argv
    assert "--oneshot" in argv
    assert "--cli" in argv
    assert "Reply with exactly: PING" in argv


def test_hermes_resume_argv_uses_chat_continue():
    driver = get_driver("hermes")
    argv = driver.resume_session_argv("sess-123")
    assert argv[0] in ("--continue", "--resume") or "chat" in argv

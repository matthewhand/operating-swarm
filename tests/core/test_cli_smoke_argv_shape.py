"""Pin the corrected non-interactive argv shape for claude/codex/pi.

These are the three CLIs whose one-shot invocation broke the live host sweep:

* claude 2.x takes a BOOLEAN ``-p`` and a positional prompt; ``-p={prompt}``
  was parsed by commander as ``-p`` + ``-=<text>`` -> "unknown option".
* codex ``exec`` must be pinned to a reachable provider or it loops on
  "Reconnecting... waiting for network" against a dead local provider.
* pi's ``-p`` print flag is correct, but its provider-qualified model pin must
  resolve on the host (``litellm/tiny`` does not), and pi 0.74.2 accepts
  neither ``--approve`` nor a bare ``--`` — its prompt is fed on **stdin**
  (``prompt_mode: "stdin"``), which is the only channel its parser cannot
  mangle.

The assertions run through ``CliAdapter._build_invocation`` / ``smoke_check``
with stdout mocked, so they never touch a live model and cannot regress.
"""

from __future__ import annotations

import asyncio

import pytest

from swarm.core import cli_catalog
from swarm.core.cli_adapter import (
    DEFAULT_SMOKE_PROMPT,
    SMOKE_OK,
    CliAdapter,
    CliResult,
)

PROMPT = "Reply with the single word: OK"
WORKDIR = "/tmp/proj"


def _adapter(name: str, *, smoke: bool = False) -> CliAdapter:
    entry = cli_catalog.catalog_entry(name)
    cmd = cli_catalog.apply_smoke_flags(name, entry["cmd"]) if smoke else entry["cmd"]
    return CliAdapter.from_config(name, {**entry, "cmd": cmd})


def _invocation(name: str, *, smoke: bool = False, session_id: str | None = None):
    return _adapter(name, smoke=smoke)._build_invocation(
        PROMPT, WORKDIR, session_id=session_id
    )


def test_claude_print_is_boolean_and_prompt_is_positional():
    argv, stdin = _invocation("claude")
    assert stdin is None
    assert argv[0] == "claude"
    assert "-p" in argv
    # No attached value: claude's -p/--print takes no argument.
    assert not any(part.startswith("-p=") for part in argv)
    assert argv[-2:] == ["--", PROMPT]
    assert "--output-format" in argv
    assert "--dangerously-skip-permissions" in argv
    idx = argv.index("-p")
    assert argv[idx + 1] != PROMPT  # prompt must NOT follow -p directly


def test_claude_resume_keeps_boolean_print_and_positional_prompt():
    argv, _ = _invocation("claude", session_id="sid-abc123")
    assert argv[:3] == ["claude", "--resume", "sid-abc123"]
    assert not any(part.startswith("-p=") for part in argv)
    assert argv[-2:] == ["--", PROMPT]


def test_claude_smoke_does_not_reattach_prompt():
    # smoke_check must use the same corrected shape (no smoke-only rewrite).
    assert _invocation("claude", smoke=True) == _invocation("claude")


def test_codex_pins_reachable_gateway_provider():
    argv, stdin = _invocation("codex")
    assert stdin is None
    assert argv[:2] == ["codex", "exec"]
    assert argv[argv.index("-c") + 1] == "model_provider=litellm"
    assert argv.count("-c") == 2
    assert argv[argv.index("-c", argv.index("-c") + 1) + 1] == "model=delegation"
    assert "--dangerously-bypass-approvals-and-sandbox" in argv
    assert argv[-2:] == ["--", PROMPT]


def test_codex_resume_keeps_provider_pin():
    argv, _ = _invocation("codex", session_id="sid-abc123")
    assert argv[:4] == ["codex", "exec", "resume", "sid-abc123"]
    assert "model_provider=litellm" in argv
    assert argv[-2:] == ["--", PROMPT]


def test_pi_print_flag_and_reachable_model_pin():
    argv, stdin = _invocation("pi")
    # pi 0.74.2: the prompt is delivered on stdin, not argv. See
    # test_pi_argv_carries_no_flag_the_binary_rejects.
    assert stdin == PROMPT.encode("utf-8")
    assert argv == ["pi", "-p", "--mode", "text", "--model", "litellm-fly/orchestration"]
    assert argv[argv.index("--model") + 1] == "litellm-fly/orchestration"
    assert "--mode" in argv and "text" in argv


def test_pi_argv_carries_no_flag_the_binary_rejects():
    """pi 0.74.2 rejects both flags the old argv relied on.

    `pi -p --mode text --approve -- <prompt>` exits with
    `Error: Unknown options: --approve, --`, and removing the bogus flag leaves
    `Error: Unknown option: --`. pi's parser is hand-rolled with no `--`
    terminator branch, and its core ships no permission popups at all, so there
    is no approval flag to pass. Both are pinned off here so neither can creep
    back in through argv assembly.
    """
    argv, _ = _invocation("pi")
    assert "--" not in argv
    assert not any("approve" in part.lower() for part in argv)
    assert "--no-session" not in argv  # production cmd stays resumable


def test_pi_smoke_appends_no_session_without_an_end_marker():
    # pi has no `--` for the smoke flag to be inserted before, so
    # apply_smoke_flags appends it. The prompt still rides on stdin, so the
    # production and smoke argv stay byte-identical apart from that flag.
    prod, _ = _invocation("pi")
    assert "--no-session" not in prod
    smoked, smoked_stdin = _invocation("pi", smoke=True)
    assert "--no-session" in smoked
    assert smoked == [*prod, "--no-session"]
    assert smoked_stdin == prod_stdin_bytes()


def prod_stdin_bytes() -> bytes:
    argv, stdin = _invocation("pi")
    assert stdin is not None
    return stdin


def test_smoke_check_probes_the_corrected_argv(monkeypatch):
    captured: dict[str, list[str]] = {}

    async def fake_run(self, prompt, **kwargs):
        captured["argv"], captured["stdin"] = self._build_invocation(prompt, WORKDIR)
        return CliResult(name=self.name, ok=True, text="OK", returncode=0)

    monkeypatch.setattr(CliAdapter, "run", fake_run)
    monkeypatch.setattr(CliAdapter, "is_available", lambda self: True)

    for name in ("claude", "codex", "pi"):
        captured.clear()
        result = asyncio.run(_adapter(name).smoke_check())
        assert result.status == SMOKE_OK, name
        argv = captured["argv"]
        assert not any(part.startswith("-p=") for part in argv), name
        if name == "pi":
            # stdin-prompt CLI: the smoke prompt is on the pipe, and the
            # ephemeral --no-session is the only argv difference.
            assert captured["stdin"] == DEFAULT_SMOKE_PROMPT.encode("utf-8"), name
            assert "--no-session" in argv, name
            assert "--" not in argv, name
        else:
            assert argv[-1] == DEFAULT_SMOKE_PROMPT, name
            assert captured["stdin"] is None, name
        if name == "codex":
            assert "model_provider=litellm" in argv


@pytest.mark.parametrize("name", ["claude", "codex"])
def test_flag_shaped_prompt_stays_after_end_of_options(name):
    argv, _ = _adapter(name)._build_invocation("--model evil", WORKDIR)
    assert argv[argv.index("--") + 1] == "--model evil"
    assert argv[-1] == "--model evil"


def test_flag_shaped_prompt_reaches_pi_on_stdin_unmarked():
    """The one CLI where the end-of-options marker is not available.

    Defering a flag-shaped prompt behind `--` is right for claude/codex, but it
    is precisely the argv pi refuses to parse. pi's catalog entry uses
    prompt_mode "stdin" instead, so nothing is deferred, nothing is marked, and
    the text arrives intact.
    """
    argv, stdin = _adapter("pi")._build_invocation("--model evil", WORKDIR)
    assert stdin == b"--model evil"
    assert "--" not in argv
    assert "--model evil" not in argv
    assert argv == ["pi", "-p", "--mode", "text", "--model", "litellm-fly/orchestration"]

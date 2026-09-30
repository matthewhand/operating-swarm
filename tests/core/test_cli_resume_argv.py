"""REQ-171C-4 / C-H7: full assembled resume argv for every catalog CLI."""

from __future__ import annotations

from swarm.core.cli_adapter import CliAdapter, _strip_resume_conflicts
from swarm.core.cli_catalog import (
    apply_smoke_flags,
    catalog_entry,
    catalog_names,
    session_policy,
    smoke_flags,
)


SID = "sid-abc123"
PROMPT = "hello"
WORKDIR = "/tmp/proj"

# Locked assembled argv (token-substituted, resume inserted, conflicts stripped).
EXPECTED_RESUME_ARGV = {
    "grok": [
        "grok",
        "--resume",
        SID,
        "--output-format",
        "json",
        "--always-approve",
        f"-p={PROMPT}",
    ],
    "agy": [
        "agy",
        "--conversation",
        SID,
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        f"-p={PROMPT}",
    ],
    "claude": [
        "claude",
        "--resume",
        SID,
        "-p",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
        "--",
        PROMPT,
    ],
    "gemini": [
        "gemini",
        "--resume",
        SID,
        f"-p={PROMPT}",
        "-o",
        "json",
        "--yolo",
        "--skip-trust",
    ],
    "codex": [
        "codex",
        "exec",
        "resume",
        SID,
        "-c",
        "model_provider=litellm",
        "-c",
        "model=delegation",
        "--dangerously-bypass-approvals-and-sandbox",
        "--",
        PROMPT,
    ],
    "opencode": [
        "opencode",
        "run",
        "--session",
        SID,
        "--model",
        # #1747 moved the OpenCode seat off the metered gateway slug onto the
        # free Space Bunny model. This pin follows the catalog deliberately; if
        # the default moves again, this is the line that should fail, so it must
        # be updated in the same commit as the catalog change.
        "opencode/space-bunny-free",
        # #1747 also added `--auto` to the same catalog entry, so a CLI seat
        # keeps working when the Grok Bot quota is exhausted. It is pinned here
        # deliberately rather than omitted: `--auto` is the flag that
        # auto-approves, so if it is ever dropped from the catalog this line
        # must fail rather than quietly lose it.
        "--auto",
        "--",
        PROMPT,
    ],
    # #1658: kilo 1.0.0 has no `run` subcommand and no session flag, so it is
    # declared non-resumable with a stated reason. The adapter must then send
    # the plain one-shot argv and never invent a session id.
    "kilocode": [
        "kilo",
        "--auto",
        "-t",
        "240",
        PROMPT,
    ],
    "omp": [
        "omp",
        "-p",
        "--resume",
        SID,
        "--model",
        "litellm/orchestration",
        "--auto-approve",
        "--",
        PROMPT,
    ],
    # pi 0.74.2 rejects a bare `--` terminator (`Error: Unknown option: --`)
    # and has no `--approve` flag (the string "approve" appears nowhere in the
    # package; pi ships no permission popups). The prompt therefore rides on
    # stdin, so it is absent from argv entirely — see EXPECTED_STDIN.
    "pi": [
        "pi",
        "-p",
        "--session",
        SID,
        "--mode",
        "text",
        "--model",
        "litellm-fly/orchestration",
    ],
    "qwen": [
        "qwen",
        "--resume",
        SID,
        "--output-format",
        "json",
        "--yolo",
        f"-p={PROMPT}",
    ],
    # Workspace prose is not resumable. Upstream rejects --resume on
    # `ocr review` unless the turn is a range, a commit, or a scan, and that
    # rejection skips the model call. "hello" stays --background with no
    # --resume. Range turns still resume (test_ocr_review_1363.py).
    "ocr": [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
        f"--background={PROMPT}",
    ],
}

# Which catalog CLIs carry the prompt on stdin instead of argv, and what
# exactly reaches the pipe. Empty/absent name = "prompt must NOT be on stdin".
# pi is the first: its parser has no `--` terminator and no `--approve` flag,
# so a positional prompt is the only channel pi will not mangle (`@` becomes a
# file arg, `-` becomes an option) — and pi's own docs document merging piped
# stdin into the print-mode prompt. Asserting the *bytes* is what keeps the
# prompt from being double-fed into argv.
EXPECTED_STDIN = {
    "pi": PROMPT.encode("utf-8"),
}


def test_every_catalog_cli_assembled_resume_argv():
    assert set(EXPECTED_RESUME_ARGV) == set(catalog_names())
    for name in catalog_names():
        adapter = CliAdapter.from_config(name, catalog_entry(name))
        argv, stdin = adapter._build_invocation(PROMPT, WORKDIR, session_id=SID)
        expected_stdin = EXPECTED_STDIN.get(name)
        if expected_stdin is None:
            assert stdin is None, name
        else:
            # prompt_mode "stdin": argv carries no prompt, the pipe does.
            assert stdin == expected_stdin, name
            assert PROMPT not in argv, name
        assert argv == EXPECTED_RESUME_ARGV[name], name
        policy = session_policy(name) or {}
        if name == "ocr":
            # ocr is gated by its own rule (a workspace review rejects
            # --resume before the model runs), not by the catalog policy.
            assert "--resume" not in argv
            assert SID not in argv
        elif not policy.get("resume_argv"):
            # #1658: a declared non-resumable CLI must NOT be handed a session
            # id, and must not be given a guessed --resume either.
            assert policy.get("resume_unsupported_reason"), name
            assert SID not in argv, name
            assert "--resume" not in argv, name
        else:
            assert SID in argv, name
        assert "--no-session" not in argv


def test_production_pi_cmd_has_no_no_session():
    cmd = catalog_entry("pi")["cmd"]
    assert "--no-session" not in cmd
    adapter = CliAdapter.from_config("pi", catalog_entry("pi"))
    fresh, _ = adapter._build_invocation(PROMPT, WORKDIR)
    assert "--no-session" not in fresh
    resumed, _ = adapter._build_invocation(PROMPT, WORKDIR, session_id=SID)
    assert "--session" in resumed
    assert resumed[resumed.index("--session") + 1] == SID
    assert "--no-session" not in resumed


def test_resume_strips_conflicting_no_session():
    # A *user-configured* leftover, not the catalog shape: a config may still
    # carry a stale --no-session (and, on a pre-0.74.2 pi, flags pi no longer
    # accepts). The strip must run regardless of what else is in the argv.
    leftover = {
        **catalog_entry("pi"),
        "cmd": [
            "pi",
            "-p",
            "--mode",
            "text",
            "--no-session",
            "--",
            "{prompt}",
        ],
        "prompt_mode": "arg",
    }
    adapter = CliAdapter.from_config("pi", leftover)
    argv, _ = adapter._build_invocation(PROMPT, WORKDIR, session_id=SID)
    assert "--no-session" not in argv
    assert argv[argv.index("--session") + 1] == SID
    assert "--" in argv
    assert argv[argv.index("--") + 1] == PROMPT


def test_pi_smoke_flags_are_ephemeral_only():
    cmd = catalog_entry("pi")["cmd"]
    assert "--no-session" not in cmd
    assert smoke_flags("pi") == ["--no-session"]
    # pi has no `--` terminator, so the smoke flag is appended at the end
    # rather than inserted before one.
    assert "--" not in cmd
    assert apply_smoke_flags("pi", cmd) == [*cmd, "--no-session"]
    assert apply_smoke_flags("grok", catalog_entry("grok")["cmd"]) == catalog_entry("grok")[
        "cmd"
    ]


def test_pi_never_guesses_a_resume_flag():
    """pi declares a real policy, so the adapter must never invent one.

    A declared policy (``--session``) means ``resume_declared`` is true, which
    is what suppresses the ``--resume`` best guess. Pin it: if the catalog entry
    were ever dropped, the guess would silently resume a session pi cannot
    address by that flag.
    """
    adapter = CliAdapter.from_config("pi", catalog_entry("pi"))
    policy = adapter.session_policy()
    assert policy["resume_declared"] is True
    assert policy["can_resume"] is True
    argv, _ = adapter._build_invocation(PROMPT, WORKDIR, session_id=SID)
    assert argv.count("--session") == 1
    assert "--resume" not in argv


def test_strip_resume_conflicts_drops_continue_and_no_session():
    raw = ["pi", "-p", "--no-session", "--continue", "--approve", "--", "hi"]
    assert _strip_resume_conflicts(raw, ["--no-session"]) == [
        "pi",
        "-p",
        "--approve",
        "--",
        "hi",
    ]


def test_omp_smoke_flags_are_ephemeral_only():
    cmd = catalog_entry("omp")["cmd"]
    assert "--no-session" not in cmd
    assert smoke_flags("omp") == ["--no-session"]
    smoked = apply_smoke_flags("omp", cmd)
    assert "--no-session" in smoked
    assert smoked.index("--no-session") < smoked.index("--")

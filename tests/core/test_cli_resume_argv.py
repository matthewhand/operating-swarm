"""REQ-171C-4 / C-H7: full assembled resume argv for every catalog CLI."""

from __future__ import annotations

from swarm.core.cli_adapter import CliAdapter, _strip_resume_conflicts
from swarm.core.cli_catalog import (
    apply_smoke_flags,
    catalog_entry,
    catalog_names,
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
        f"-p={PROMPT}",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
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
        "litellm/orchestration",
        "--",
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
    "pi": [
        "pi",
        "-p",
        "--session",
        SID,
        "--mode",
        "text",
        "--approve",
        "--",
        PROMPT,
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
}


def test_every_catalog_cli_assembled_resume_argv():
    assert set(EXPECTED_RESUME_ARGV) == set(catalog_names())
    for name in catalog_names():
        adapter = CliAdapter.from_config(name, catalog_entry(name))
        argv, stdin = adapter._build_invocation(PROMPT, WORKDIR, session_id=SID)
        assert stdin is None, name
        assert argv == EXPECTED_RESUME_ARGV[name], name
        assert SID in argv
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
    leftover = {
        **catalog_entry("pi"),
        "cmd": [
            "pi",
            "-p",
            "--mode",
            "text",
            "--no-session",
            "--approve",
            "--",
            "{prompt}",
        ],
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
    smoked = apply_smoke_flags("pi", cmd)
    assert "--no-session" in smoked
    assert smoked.index("--no-session") < smoked.index("--")
    assert apply_smoke_flags("grok", catalog_entry("grok")["cmd"]) == catalog_entry("grok")[
        "cmd"
    ]


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

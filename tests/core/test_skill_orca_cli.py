"""orca-cli skill (#1364): discovery plus the JSON allowlist driver.

The driver never spawns a real ``orca`` binary. A fake runner stands in for
the CLI so CI stays hermetic.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from swarm.core import skills

SKILL_DIR = Path(__file__).resolve().parents[2] / "skills" / "orca-cli"


@pytest.fixture(scope="module")
def drive() -> ModuleType:
    spec = importlib.util.spec_from_file_location("orca_cli_drive", SKILL_DIR / "drive.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses consult sys.modules during class creation.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _completed(stdout: str, stderr: str = "", code: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["orca"], returncode=code, stdout=stdout, stderr=stderr)


# ------------------------------------------------------------ discovery


def test_skill_is_discovered_with_driver():
    catalog = skills.discover_skills(SKILL_DIR.parent)
    assert "orca-cli" in catalog
    skill = catalog["orca-cli"]
    assert "use when" in skill.description.lower()
    assert "drive.py" in skill.assets
    for needle in (
        "worktree create",
        "terminal send",
        "terminal wait",
        "terminal read",
        "--json",
        "tui-idle",
        "orca serve",
    ):
        assert needle in skill.instructions


# ------------------------------------------------------------ allowlist


def test_phase1_commands_always_pass_json(drive: ModuleType):
    created = drive.build_invocation(
        ["worktree", "create", "--repo", "id:repo", "--name", "my-task"]
    )
    assert created.argv == [
        "orca",
        "worktree",
        "create",
        "--repo",
        "id:repo",
        "--name",
        "my-task",
        "--json",
    ]

    sent = drive.build_invocation(
        ["terminal", "send", "--text", "continue", "--enter"]
    )
    assert sent.argv == [
        "orca",
        "terminal",
        "send",
        "--text",
        "continue",
        "--enter",
        "--json",
    ]

    waited = drive.build_invocation(
        ["terminal", "wait", "--for", "tui-idle", "--timeout-ms", "30000", "--json"]
    )
    assert waited.argv.count("--json") == 1
    assert "--for" in waited.argv and "tui-idle" in waited.argv

    read = drive.build_invocation(["terminal", "read", "--terminal", "term-1"])
    assert read.argv[:4] == ["orca", "terminal", "read", "--terminal"]
    assert read.argv[-1] == "--json"


def test_wait_timeout_extends_subprocess_budget(drive: ModuleType):
    short = drive.build_invocation(["terminal", "wait", "--for", "tui-idle"])
    assert short.timeout == drive.DEFAULT_SUBPROCESS_TIMEOUT
    long = drive.build_invocation(
        ["terminal", "wait", "--for", "tui-idle", "--timeout-ms", "300000"]
    )
    assert long.timeout == 300.0 + drive.TIMEOUT_SLACK_SECONDS


@pytest.mark.parametrize(
    "args",
    [
        ["serve", "--port", "6768"],
        ["account", "add", "--agent", "claude"],
        ["environment", "add", "--pairing-code", "orca://pair?code=secret"],
        ["artifacts", "share", "./notes.md"],
        ["computer", "click"],
        ["terminal", "send", "--text"],
        ["worktree", "create", "--nope", "x"],
        [],
    ],
)
def test_refused_commands_never_build_an_argv(drive: ModuleType, args: list[str]):
    with pytest.raises(drive.DriveError):
        drive.build_invocation(args)


def test_serve_refusal_names_pairing(drive: ModuleType):
    with pytest.raises(drive.DriveError, match="pairing"):
        drive.build_invocation(["serve", "--pairing-address", "100.64.1.20"])


# ------------------------------------------------------------ run


def test_run_parses_json_and_uses_resolved_binary(drive: ModuleType):
    seen: dict[str, object] = {}

    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        seen["argv"] = argv
        seen["timeout"] = timeout
        return _completed('{"worktrees": []}\n')

    outcome = drive.run(
        ["worktree", "ps"],
        which=lambda name: "/usr/local/bin/orca" if name == "orca" else None,
        runner=runner,
    )
    assert outcome.exit_code == 0
    assert outcome.payload == {"worktrees": []}
    assert seen["argv"] == ["/usr/local/bin/orca", "worktree", "ps", "--json"]


def test_run_passes_through_json_error_from_orca(drive: ModuleType):
    def runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        return _completed('{"error": "no active worktree"}\n', code=3)

    outcome = drive.run(["worktree", "current"], which=lambda _n: "/bin/orca", runner=runner)
    assert outcome.exit_code == 3
    assert outcome.payload == {"error": "no active worktree"}


def test_run_reports_missing_binary_without_calling_runner(drive: ModuleType):
    def runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner must not be called")

    outcome = drive.run(["status"], which=lambda _n: None, runner=runner)
    assert outcome.exit_code == 127
    assert outcome.payload["ok"] is False
    assert "not found" in outcome.payload["error"]


def test_run_wraps_non_json_stdout(drive: ModuleType):
    def runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        return _completed("not json", stderr="boom", code=1)

    outcome = drive.run(["status"], which=lambda _n: "/bin/orca", runner=runner)
    assert outcome.exit_code == 1
    assert outcome.payload["ok"] is False
    assert outcome.payload["error"] == "orca did not return JSON"
    assert "boom" in outcome.payload["stderr"]
    json.loads(outcome.stdout)


def test_run_reports_timeout_as_cancellation(drive: ModuleType):
    def runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd=argv, timeout=timeout)

    outcome = drive.run(
        ["terminal", "wait", "--for", "tui-idle", "--timeout-ms", "1000"],
        which=lambda _n: "/bin/orca",
        runner=runner,
    )
    assert outcome.exit_code == 124
    assert outcome.payload["ok"] is False
    assert "timed out" in outcome.payload["error"]
    assert outcome.payload["timeout_seconds"] >= 1


def test_refused_serve_does_not_spawn(drive: ModuleType):
    def runner(_argv: list[str], _timeout: float) -> subprocess.CompletedProcess[str]:
        raise AssertionError("runner must not be called")

    outcome = drive.run(["serve", "--port", "6768"], which=lambda _n: "/bin/orca", runner=runner)
    assert outcome.exit_code == 2
    assert outcome.payload["ok"] is False
    assert "pairing" in outcome.payload["error"]

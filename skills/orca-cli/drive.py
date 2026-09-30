#!/usr/bin/env python3
"""Drive the Orca ADE ``orca`` CLI and print its JSON.

Issue #1364 phase 1. This is an allowlist, not a shell: it only invokes the
documented worktree and terminal JSON commands and always passes ``--json``.
``orca serve`` pairing and ``orca account`` are refused — pairing is not a
documented third-party API, and account setup captures host credentials.

Usage (staged into the CLI workdir when the ``orca-cli`` skill is attached):

    python3 drive.py status
    python3 drive.py worktree create --repo id:<repoId> --name my-task
    python3 drive.py terminal send --text "continue" --enter
    python3 drive.py terminal wait --for tui-idle --timeout-ms 30000
    python3 drive.py terminal read
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

# Floor for the subprocess timeout. ``terminal wait --timeout-ms`` can ask
# Orca to block longer; the subprocess budget is that wait plus slack.
DEFAULT_SUBPROCESS_TIMEOUT = 60.0
TIMEOUT_SLACK_SECONDS = 15.0
_ERROR_TEXT_CAP = 4000

Runner = Callable[[list[str], float], subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]


class DriveError(Exception):
    """A request we will not send to ``orca``."""

    def __init__(self, message: str, *, exit_code: int = 2) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class Flag:
    name: str
    takes_value: bool = True


@dataclass(frozen=True)
class Invocation:
    argv: list[str]
    timeout: float


# Selectors shared by the documented commands. ``--environment`` picks an
# already-paired runtime; it does not perform pairing.
_SHARED: tuple[Flag, ...] = (
    Flag("--host"),
    Flag("--environment"),
    Flag("--worktree"),
    Flag("--json", takes_value=False),
)

_COMMANDS: dict[tuple[str, ...], tuple[Flag, ...]] = {
    ("status",): (),
    ("open",): (),
    ("worktree", "ps"): (),
    ("worktree", "current"): (),
    ("worktree", "list"): (Flag("--repo"),),
    ("worktree", "show"): (),
    ("worktree", "create"): (
        Flag("--repo"),
        Flag("--name"),
        Flag("--issue"),
        Flag("--agent"),
        Flag("--prompt"),
        Flag("--setup"),
        Flag("--parent-worktree"),
        Flag("--no-parent", takes_value=False),
    ),
    ("worktree", "set"): (Flag("--comment"),),
    ("worktree", "rm"): (Flag("--force", takes_value=False),),
    ("terminal", "list"): (),
    ("terminal", "show"): (Flag("--terminal"),),
    ("terminal", "read"): (
        Flag("--terminal"),
        Flag("--screen", takes_value=False),
        Flag("--cursor"),
        Flag("--limit"),
    ),
    ("terminal", "send"): (
        Flag("--terminal"),
        Flag("--text"),
        Flag("--enter", takes_value=False),
    ),
    ("terminal", "wait"): (
        Flag("--terminal"),
        Flag("--for"),
        Flag("--timeout-ms"),
    ),
    ("terminal", "create"): (
        Flag("--title"),
        Flag("--command"),
    ),
    ("terminal", "split"): (
        Flag("--terminal"),
        Flag("--direction"),
        Flag("--command"),
    ),
}

_REFUSED: dict[str, str] = {
    "serve": (
        "orca serve pairing is not a documented third-party API; "
        "this skill only drives the local JSON CLI (status, worktree, terminal)"
    ),
    "account": (
        "orca account captures host credentials; this skill does not drive it"
    ),
    "environment": (
        "pairing codes are not a third-party API; "
        "this skill does not add or remove remote environments"
    ),
}


def _flag_index(flags: tuple[Flag, ...]) -> dict[str, Flag]:
    indexed = {flag.name: flag for flag in _SHARED}
    indexed.update({flag.name: flag for flag in flags})
    return indexed


def _timeout_seconds(rest: list[str], flags: Mapping[str, Flag]) -> float:
    timeout = DEFAULT_SUBPROCESS_TIMEOUT
    index = 0
    while index < len(rest):
        token = rest[index]
        spec = flags.get(token)
        if spec is not None and spec.takes_value and token == "--timeout-ms":
            if index + 1 >= len(rest):
                break
            try:
                wait = float(rest[index + 1]) / 1000.0
            except ValueError:
                break
            timeout = max(timeout, wait + TIMEOUT_SLACK_SECONDS)
        index += 2 if spec is not None and spec.takes_value else 1
    return timeout


def build_invocation(args: list[str], *, binary: str = "orca") -> Invocation:
    """Turn CLI args into an ``orca … --json`` argv, or refuse them.

    ``binary`` is the executable path. The returned argv never uses a shell.
    """
    tokens = list(args)
    if not tokens:
        raise DriveError(
            "usage: python3 drive.py <status|open|worktree|terminal> …"
        )
    head = tokens[0]
    if head in _REFUSED:
        raise DriveError(_REFUSED[head])

    matched: tuple[str, ...] | None = None
    for length in (2, 1):
        if len(tokens) >= length:
            key = tuple(tokens[:length])
            if key in _COMMANDS:
                matched = key
                break
    if matched is None:
        known = ", ".join(" ".join(path) for path in sorted(_COMMANDS))
        raise DriveError(
            f"command not in the orca-cli allowlist: {' '.join(tokens)!r}. "
            f"Allowed: {known}"
        )

    rest = tokens[len(matched):]
    flags = _flag_index(_COMMANDS[matched])
    timeout = _timeout_seconds(rest, flags)
    cleaned: list[str] = []
    index = 0
    while index < len(rest):
        token = rest[index]
        if not token.startswith("-"):
            raise DriveError(
                f"unexpected argument {token!r} for '{' '.join(matched)}'"
            )
        spec = flags.get(token)
        if spec is None:
            raise DriveError(
                f"flag {token!r} is not allowed on '{' '.join(matched)}'"
            )
        if token == "--json":
            index += 1
            continue
        if spec.takes_value:
            if index + 1 >= len(rest) or rest[index + 1].startswith("-"):
                raise DriveError(f"flag {token} requires a value")
            cleaned.extend((token, rest[index + 1]))
            index += 2
            continue
        cleaned.append(token)
        index += 1

    argv = [binary, *matched, *cleaned, "--json"]
    return Invocation(argv=argv, timeout=timeout)


def _clip(text: str) -> str:
    if len(text) <= _ERROR_TEXT_CAP:
        return text
    return text[:_ERROR_TEXT_CAP] + "…[truncated]"


def _failure(message: str, *, exit_code: int, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": message, "exit_code": exit_code}
    for key, value in extra.items():
        if isinstance(value, str):
            payload[key] = _clip(value)
        elif value is not None:
            payload[key] = value
    return payload


def _parse_stdout(stdout: str, stderr: str, exit_code: int) -> tuple[Any, str, int]:
    text = stdout.strip()
    if not text:
        payload = _failure(
            "orca did not return JSON",
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )
        code = exit_code if exit_code else 1
        return payload, json.dumps(payload) + "\n", code
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        payload = _failure(
            "orca did not return JSON",
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )
        code = exit_code if exit_code else 1
        return payload, json.dumps(payload) + "\n", code
    raw = stdout if stdout.endswith("\n") else stdout + "\n"
    return parsed, raw, exit_code


def _default_runner(argv: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


@dataclass(frozen=True)
class DriveOutcome:
    exit_code: int
    payload: Any
    stdout: str


def run(
    args: list[str],
    *,
    which: Which = shutil.which,
    runner: Runner = _default_runner,
) -> DriveOutcome:
    """Execute one allowlisted ``orca`` command and return parsed JSON.

    Missing binary, refusal, timeout, and non-JSON output are reported as
    ``{"ok": false, "error": ...}``. A JSON stdout from ``orca`` is passed
    through unchanged, including when ``orca`` exits non-zero.
    """
    try:
        invocation = build_invocation(args)
    except DriveError as exc:
        payload = _failure(str(exc), exit_code=exc.exit_code)
        return DriveOutcome(exc.exit_code, payload, json.dumps(payload) + "\n")

    binary = which("orca")
    if not binary:
        payload = _failure(
            "orca binary not found on PATH",
            exit_code=127,
            hint=(
                "Register the Orca CLI in the Orca desktop app "
                "(Settings → General → Orca CLI), then retry."
            ),
        )
        return DriveOutcome(127, payload, json.dumps(payload) + "\n")

    argv = [binary, *invocation.argv[1:]]
    try:
        completed = runner(argv, invocation.timeout)
    except subprocess.TimeoutExpired:
        payload = _failure(
            "orca timed out",
            exit_code=124,
            timeout_seconds=invocation.timeout,
        )
        return DriveOutcome(124, payload, json.dumps(payload) + "\n")

    payload, stdout, code = _parse_stdout(
        completed.stdout or "",
        completed.stderr or "",
        int(completed.returncode or 0),
    )
    return DriveOutcome(code, payload, stdout)


def main(argv: list[str] | None = None) -> int:
    outcome = run(list(sys.argv[1:] if argv is None else argv))
    sys.stdout.write(outcome.stdout)
    return outcome.exit_code


if __name__ == "__main__":
    raise SystemExit(main())

"""#1363 — Open Code Review as a CLI reviewer seat (skeptic / gate)."""

from __future__ import annotations

import asyncio
import json

import pytest

from swarm.blueprints.code_reviewer.blueprint_code_reviewer import (
    CodeReviewerBlueprint as TeamAiCodeReviewer,
)
from swarm.blueprints.ocr_reviewer.blueprint_ocr_reviewer import (
    OcrReviewerBlueprint,
)
from swarm.core.cli_adapter import CliAdapter
from swarm.core.cli_catalog import (
    SIDEBAR_CLIS,
    catalog_entry,
    catalog_names,
    session_policy,
)
from swarm.core.cli_driver import OpenCodeReviewCliAgent
from swarm.core.cli_registry import get_driver
from swarm.core.cli_sessions import is_resume_failure_text
from swarm.core.kind_bases import CliKindBase
from swarm.core.ocr_review import (
    OCR_MISSING_MESSAGE,
    augment_ocr_argv,
    classify_ocr_review,
    ocr_resume_rejected,
    parse_ocr_stdout,
    render_ocr_review,
    resume_allowed,
)
from swarm.core.routines import ROUTINE_PRESETS

_CLEAN = json.dumps(
    {
        "status": "success",
        "message": "No comments generated. Looks good to me.",
        "session_id": "sess-1",
        "summary": {"files_reviewed": 3},
        "comments": [],
    }
)

_FINDING = json.dumps(
    {
        "status": "success",
        "session_id": "sess-2",
        "summary": {"files_reviewed": 1},
        "comments": [
            {
                "path": "src/app.py",
                "content": "Unchecked None.",
                "start_line": 12,
                "end_line": 14,
                "severity": "high",
                "category": "null-check",
                "suggestion_code": "if x is None: return",
            }
        ],
    }
)


def test_catalog_ocr_is_a_reviewer_not_a_chat_cli():
    assert "ocr" in catalog_names()
    assert "ocr" not in SIDEBAR_CLIS
    entry = catalog_entry("ocr")
    assert entry["cmd"] == ["ocr", "review", "--format", "json"]
    assert entry["prompt_mode"] == "none"
    assert entry["parse"] == "ocr"
    assert entry["mode"] == "readonly"
    assert "{prompt}" not in " ".join(entry["cmd"])
    assert "env_allowlist" not in entry
    policy = session_policy("ocr")
    assert policy["resume_argv"] == ["--resume", "{session_id}"]
    assert policy["resume_insert"] == 2
    assert policy["list_capability"] == "paste-only"


def test_instruction_never_becomes_a_positional_prompt():
    argv = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "please review the auth changes",
    )
    assert argv == [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
        "--background=please review the auth changes",
    ]
    assert "please" not in argv[:-1]

    ranged = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "from main to feature-branch",
    )
    assert ranged == [
        "ocr",
        "review",
        "--format",
        "json",
        "--from",
        "main",
        "--to",
        "feature-branch",
        "--audience",
        "agent",
    ]
    assert "--background" not in " ".join(ranged)

    commit = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "commit abcdef1",
    )
    assert commit == [
        "ocr",
        "review",
        "--format",
        "json",
        "--commit",
        "abcdef1",
        "--audience",
        "agent",
    ]

    scan = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "scan src/main.go",
    )
    assert scan == [
        "ocr",
        "scan",
        "--format",
        "json",
        "--path",
        "src/main.go",
        "--audience",
        "agent",
    ]

    mixed = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "Focus on token refresh. from main to feature",
    )
    assert mixed[-1] == "--background=Focus on token refresh. from main to feature"
    assert mixed[mixed.index("--from") + 1] == "main"
    assert mixed[mixed.index("--to") + 1] == "feature"


def test_instruction_drops_flag_injection_and_path_escape():
    injected = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "from --evil to feature; rm",
    )
    assert injected == [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
        "--background=from --evil to feature; rm",
    ]
    assert "--from" not in injected
    assert "--to" not in injected
    escaped = augment_ocr_argv(
        ["ocr", "review", "--format", "json"],
        "scan ../etc/passwd",
    )
    assert escaped == [
        "ocr",
        "review",
        "--format",
        "json",
        "--audience",
        "agent",
    ]
    assert "--path" not in escaped
    assert "--background" not in " ".join(escaped)


def test_adapter_keeps_prompt_off_argv_and_parses_json():
    adapter = CliAdapter.from_config("ocr", catalog_entry("ocr"))
    argv, stdin = adapter._build_invocation(
        "from main to feature",
        "/tmp/proj",
    )
    assert stdin is None
    assert argv == [
        "ocr",
        "review",
        "--format",
        "json",
        "--from",
        "main",
        "--to",
        "feature",
        "--audience",
        "agent",
    ]
    text, err, session_id = adapter._parse_output(_FINDING)
    assert err is None
    assert session_id == "sess-2"
    assert "request changes" in text
    assert "**Gate:** hold" in text
    assert "src/app.py:12-14" in text
    assert "null-check" in text


def test_clean_review_passes_skeptic_and_opens_the_gate():
    review = parse_ocr_stdout(_CLEAN)
    verdict = classify_ocr_review(review)
    assert verdict["skeptic"] == "pass"
    assert verdict["gate"] == "safe"
    rendered = render_ocr_review(review)
    assert "**Skeptic:** pass" in rendered
    assert "**Gate:** safe" in rendered
    assert review.files_reviewed == 3


def test_skipped_empty_diff_is_a_pass():
    raw = json.dumps(
        {
            "status": "skipped",
            "message": "No supported files changed.",
            "comments": [],
        }
    )
    verdict = classify_ocr_review(parse_ocr_stdout(raw))
    assert verdict == {
        "skeptic": "pass",
        "gate": "safe",
        "reason": "No supported files changed.",
    }


def test_budget_and_warning_statuses_hold_the_gate():
    budget = classify_ocr_review(
        parse_ocr_stdout(
            json.dumps(
                {
                    "status": "success",
                    "comments": [],
                    "summary": {"files_reviewed": 1, "budget_exceeded": True},
                }
            )
        )
    )
    assert budget["gate"] == "hold"
    assert budget["reason"] == "token budget exceeded"
    warned = classify_ocr_review(
        parse_ocr_stdout(
            json.dumps(
                {
                    "status": "completed_with_warnings",
                    "comments": [],
                    "message": "Some files could not be reviewed.",
                }
            )
        )
    )
    assert warned["skeptic"] == "request changes"
    assert warned["gate"] == "hold"


def test_workspace_prompt_is_not_resumable():
    assert resume_allowed("please review the auth changes") is False
    assert resume_allowed("from main to feature") is True
    assert resume_allowed("commit abcdef1") is True
    assert resume_allowed("scan src/main.go") is True


def test_adapter_drops_workspace_resume_and_keeps_a_range():
    adapter = CliAdapter.from_config("ocr", catalog_entry("ocr"))
    workspace, _stdin = adapter._build_invocation(
        "hello", "/tmp/proj", session_id="sid-abc123"
    )
    assert "--resume" not in workspace
    assert "sid-abc123" not in workspace
    ranged, _stdin = adapter._build_invocation(
        "from main to feature", "/tmp/proj", session_id="sid-abc123"
    )
    assert ranged[ranged.index("--resume") + 1] == "sid-abc123"


def test_upstream_resume_refusal_is_not_a_generic_session_miss():
    mismatch = (
        'exited 1: resume session review mode "full_scan" does not match '
        'current mode "range"'
    )
    assert ocr_resume_rejected(mismatch) is True
    assert ocr_resume_rejected(
        'load resume session: open resume session "sess": no such file or directory'
    )
    hint = "exited 1: review failed: boom\n[ocr] Session: sess-1 (retry with: --resume sess-1)"
    assert ocr_resume_rejected(hint) is False
    identity = (
        'exited 1: resume rejected: the reviewed input changed since session "sess" '
        "— a ref may now point at a different commit; start a new review instead of resuming"
    )
    assert ocr_resume_rejected(identity) is True
    assert is_resume_failure_text(identity) is False
    assert ocr_resume_rejected(
        'resume rejected: provider changed from "openai" to "anthropic" '
        "without being asked for"
    )
    assert (
        ocr_resume_rejected("exited 1: open resume.go: no such file or directory")
        is False
    )
    assert ocr_resume_rejected("exited 1: read resume.md: permission denied") is False


def test_partial_and_invalid_json_hold_the_gate():
    partial = classify_ocr_review(
        parse_ocr_stdout(json.dumps({"status": "partial", "comments": []}))
    )
    assert partial["skeptic"] == "request changes"
    assert partial["gate"] == "hold"
    broken = classify_ocr_review(parse_ocr_stdout("not-json"))
    assert broken["gate"] == "hold"
    assert "invalid JSON" in broken["reason"]


def test_driver_matches_catalog_argv():
    driver = get_driver("ocr")
    assert isinstance(driver, OpenCodeReviewCliAgent)
    argv = driver.build_exec_argv(
        "from main to feature",
        session_id="sess-9",
        model="claude-sonnet",
    )
    assert argv == [
        "ocr",
        "review",
        "--resume",
        "sess-9",
        "--format",
        "json",
        "--model",
        "claude-sonnet",
        "--from",
        "main",
        "--to",
        "feature",
        "--audience",
        "agent",
    ]
    workspace = driver.build_exec_argv("please review auth", session_id="sess-9")
    assert "--resume" not in workspace
    assert "--background=please review auth" in workspace
    assert "from main to feature" not in argv
    text = driver.parse_output(_CLEAN)
    assert "**Gate:** safe" in text


def test_cli_namespace_gates_the_model_pin():
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    bare = seat._adapter({"model": "default"})
    assert "--model" not in bare.config.cmd
    pinned = seat._adapter({"model": "claude-sonnet"})
    cmd = pinned.config.cmd
    assert cmd[cmd.index("--model") + 1] == "claude-sonnet"
    assert "claude-sonnet" not in " ".join(cmd[: cmd.index("--model")])


def test_code_reviewer_seat_is_cli_skeptic():
    meta = OcrReviewerBlueprint.metadata
    assert meta["name"] == "ocr_reviewer"
    assert OcrReviewerBlueprint is not TeamAiCodeReviewer
    assert meta["role"] == "skeptic"
    assert meta["rail"] is True
    assert meta["required_mcp_servers"] == []
    assert issubclass(OcrReviewerBlueprint, CliKindBase)
    assert OcrReviewerBlueprint.kind == "cli"
    assert OcrReviewerBlueprint.DEFAULT_CLI_ID == "ocr"


def test_routine_preset_runs_ocr_review_json():
    preset = next(row for row in ROUTINE_PRESETS if row["key"] == "ocr_code_review")
    assert preset["role"] == "skeptic"
    assert preset["trigger"]["event_type"] == "pull_request.opened"
    assert "ocr review --format json" in preset["instruction"]
    assert "Alibaba account" in preset["instruction"]
    assert "open-swarm[bot]" in preset["trigger"]["filters"]["exclude_authors"]


async def test_missing_binary_does_not_spawn(monkeypatch):
    spawned: list[str] = []

    async def explode(_self, *_args, **_kwargs):
        spawned.append("run")
        raise AssertionError("missing ocr must not spawn")

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: False)
    monkeypatch.setattr(CliAdapter, "run", explode)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    text = chunks[-1]["messages"][0]["content"]
    assert text == OCR_MISSING_MESSAGE
    assert spawned == []
    assert "No hosted Alibaba account is required." in text


async def test_seat_renders_adapter_text(monkeypatch):
    seen: dict[str, object] = {}

    class _Result:
        ok = True
        text = "## Open Code Review\n**Skeptic:** pass — no findings\n**Gate:** safe"
        error = None
        session_id = "sess-1"

    async def fake_run(_self, prompt, **kwargs):
        seen["prompt"] = prompt
        seen["session_id"] = kwargs.get("session_id")
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    seat.set_params({"cli_session_id": "sess-1"})
    chunks = [
        chunk
        async for chunk in seat.run(
            [{"role": "user", "content": "from main to feature"}]
        )
    ]
    body = chunks[-1]["messages"][0]["content"]
    assert "**Gate:** safe" in body
    assert seen["prompt"] == "from main to feature"
    assert seen["session_id"] == "sess-1"
    assert chunks[-1]["meta"]["backends"] == ["ocr"]


async def test_workspace_turn_does_not_resume(monkeypatch):
    seen: dict[str, object] = {}

    class _Result:
        ok = True
        text = "ok"
        error = None
        session_id = "sess-new"
        terminated = False

    async def fake_run(_self, _prompt, **kwargs):
        seen["session_id"] = kwargs.get("session_id")
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    seat.set_params({"cli_session_id": "sess-old"})
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review auth"}])
    ]
    assert seen["session_id"] is None
    assert chunks[-1]["messages"][0]["content"] == "ok"


async def test_timeout_stays_in_the_transcript(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "timed out after 600s"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    chunk = chunks[-1]
    assert chunk["messages"][0]["content"] == "timed out after 600s"
    assert chunk["meta"].get("fatal_config_error") is not True


async def test_user_stop_is_a_terminated_notice(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "terminated"
        session_id = None
        terminated = True

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    assert chunks[-1]["terminated"] is True
    assert "messages" not in chunks[-1]


async def test_mode_mismatch_clears_the_stored_resume(monkeypatch):
    calls: list[object] = []
    stored: list[object] = []

    class _Rejected:
        ok = False
        text = ""
        error = (
            'exited 1: resume session review mode "full_scan" does not match '
            'current mode "range"'
        )
        stderr = ""
        session_id = None
        terminated = False

    class _Fresh:
        ok = True
        text = "ok"
        error = None
        stderr = ""
        session_id = "sess-new"
        terminated = False

    async def fake_run(_self, _prompt, **kwargs):
        calls.append(kwargs.get("session_id"))
        return _Rejected() if len(calls) == 1 else _Fresh()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    monkeypatch.setattr(
        "swarm.core.cli_sessions.resolve_thread",
        lambda *_args, **_kwargs: ("user", "ocr_reviewer"),
    )
    monkeypatch.setattr(
        "swarm.core.cli_sessions.put_cli_session",
        lambda *_args, **_kwargs: stored.append(_args[3]),
    )
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    seat.set_params({"cli_session_id": "sess-scan"})
    chunks = [
        chunk
        async for chunk in seat.run(
            [{"role": "user", "content": "from main to feature"}]
        )
    ]
    assert calls == ["sess-scan", None]
    assert stored == [None, "sess-new"]
    assert chunks[-1]["messages"][0]["content"] == "ok"


async def test_input_identity_refusal_clears_the_stored_resume(monkeypatch):
    calls: list[object] = []
    stored: list[object] = []

    class _Rejected:
        ok = False
        text = ""
        error = (
            "exited 1: resume rejected: the reviewed input changed since session "
            '"sess-old" — a ref may now point at a different commit; '
            "start a new review instead of resuming"
        )
        stderr = ""
        session_id = None
        terminated = False

    class _Fresh:
        ok = True
        text = "ok"
        error = None
        stderr = ""
        session_id = "sess-new"
        terminated = False

    async def fake_run(_self, _prompt, **kwargs):
        calls.append(kwargs.get("session_id"))
        return _Rejected() if len(calls) == 1 else _Fresh()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    monkeypatch.setattr(
        "swarm.core.cli_sessions.resolve_thread",
        lambda *_args, **_kwargs: ("user", "ocr_reviewer"),
    )
    monkeypatch.setattr(
        "swarm.core.cli_sessions.put_cli_session",
        lambda *_args, **_kwargs: stored.append(_args[3]),
    )
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    seat.set_params({"cli_session_id": "sess-old"})
    chunks = [
        chunk
        async for chunk in seat.run(
            [{"role": "user", "content": "from main to feature"}]
        )
    ]
    assert calls == ["sess-old", None]
    assert stored == [None, "sess-new"]
    assert chunks[-1]["messages"][0]["content"] == "ok"


async def test_resume_hint_on_a_real_failure_does_not_retry(monkeypatch):
    calls: list[object] = []

    class _Result:
        ok = False
        text = "review failed"
        error = "[ocr] Session: sess-1 (retry with: --resume sess-1)"
        stderr = ""
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **kwargs):
        calls.append(kwargs.get("session_id"))
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    seat.set_params({"cli_session_id": "sess-1"})
    chunks = [
        chunk
        async for chunk in seat.run(
            [{"role": "user", "content": "from main to feature"}]
        )
    ]
    assert calls == ["sess-1"]
    assert "review failed" in chunks[-1]["messages"][0]["content"]


async def test_source_file_not_found_is_not_a_missing_binary(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "exited 1: open src/app.go: file not found"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    text = chunks[-1]["messages"][0]["content"]
    assert text == "exited 1: open src/app.go: file not found"
    assert "not on PATH" not in text
    assert chunks[-1]["meta"].get("fatal_config_error") is not True


async def test_executable_not_found_stays_the_install_message(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "executable not found on PATH: 'ocr'"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    assert chunks[-1]["messages"][0]["content"] == OCR_MISSING_MESSAGE
    assert chunks[-1]["meta"].get("fatal_config_error") is True


async def test_launch_enoent_for_the_ocr_binary_is_the_install_message(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "failed to launch: [Errno 2] No such file or directory: '/usr/bin/ocr'"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    assert chunks[-1]["messages"][0]["content"] == OCR_MISSING_MESSAGE
    assert chunks[-1]["meta"].get("fatal_config_error") is True


async def test_missing_workdir_named_ocr_stays_verbatim(monkeypatch):
    """A checkout directory named ocr is a missing cwd, not a missing binary."""
    gone = "/tmp/src/ocr"

    class _Result:
        ok = False
        text = ""
        error = f"failed to launch: [Errno 2] No such file or directory: {gone!r}"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    monkeypatch.setattr(
        "swarm.blueprints.ocr_reviewer.blueprint_ocr_reviewer.support.resolve_workdir",
        lambda *_args, **_kwargs: gone,
    )
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    text = chunks[-1]["messages"][0]["content"]
    assert text == _Result.error
    assert "not on PATH" not in text
    assert chunks[-1]["meta"].get("fatal_config_error") is not True


async def test_missing_binary_still_wins_when_workdir_is_named_ocr(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "failed to launch: [Errno 2] No such file or directory: '/usr/bin/ocr'"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    monkeypatch.setattr(
        "swarm.blueprints.ocr_reviewer.blueprint_ocr_reviewer.support.resolve_workdir",
        lambda *_args, **_kwargs: "/tmp/src/ocr",
    )
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    assert chunks[-1]["messages"][0]["content"] == OCR_MISSING_MESSAGE
    assert chunks[-1]["meta"].get("fatal_config_error") is True


async def test_missing_workdir_is_not_a_missing_binary(monkeypatch):
    class _Result:
        ok = False
        text = ""
        error = "failed to launch: [Errno 2] No such file or directory: '/tmp/gone'"
        session_id = None
        terminated = False

    async def fake_run(_self, _prompt, **_kwargs):
        return _Result()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", fake_run)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    chunks = [
        chunk async for chunk in seat.run([{"role": "user", "content": "review"}])
    ]
    text = chunks[-1]["messages"][0]["content"]
    assert text == "failed to launch: [Errno 2] No such file or directory: '/tmp/gone'"
    assert "not on PATH" not in text
    assert chunks[-1]["meta"].get("fatal_config_error") is not True


async def test_cancellation_propagates(monkeypatch):
    async def cancelled(_self, _prompt, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(CliAdapter, "is_available", lambda _self: True)
    monkeypatch.setattr(CliAdapter, "run", cancelled)
    seat = OcrReviewerBlueprint(blueprint_id="ocr_reviewer")
    with pytest.raises(asyncio.CancelledError):
        async for _chunk in seat.run([{"role": "user", "content": "review"}]):
            pass

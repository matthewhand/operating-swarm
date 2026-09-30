"""#1403 — Open Pull Request is a routine tool, default-on for issue triggers."""

from __future__ import annotations

import asyncio

from swarm.core import routines as store
from swarm.core.routine_tools import (
    TOOL_OPEN_PULL_REQUEST,
    default_tools_for_trigger,
    is_github_issue_trigger,
    open_pr_capability,
    reset_open_pr_runner,
    run_open_pr_if_enabled,
    set_open_pr_runner,
)


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    store.set_live_instruction_runner(None)


def _issue_trigger(owner_repo: str = "owner/repo"):
    return {"kind": "github_event", "event_type": "issues.opened", "owner_repo": owner_repo}


def _pr_trigger(owner_repo: str = "owner/repo"):
    return {"kind": "github_event", "event_type": "pull_request.opened", "owner_repo": owner_repo}


def test_issue_trigger_defaults_open_pr_on(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {"name": "Solve", "instruction": "Fix it.", "trigger": _issue_trigger()},
    )
    assert is_github_issue_trigger(created["trigger"]) is True
    assert created["tools"] == [TOOL_OPEN_PULL_REQUEST]
    assert created["tools_explicit"] is False
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again["tools"] == [TOOL_OPEN_PULL_REQUEST]
    assert again["tools_explicit"] is False


def test_non_issue_triggers_default_open_pr_off(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    cases = [
        {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
        _pr_trigger(),
        {"kind": "interval", "seconds": 3600},
        {"kind": "cron", "expression": "0 3 * * *"},
        {"kind": "mailbox_message", "sender": "support", "pattern": "prove"},
    ]
    for trigger in cases:
        row = store.create_routine(
            "codey",
            {"name": f"Off {trigger['kind']}", "instruction": "x", "trigger": trigger},
        )
        assert row["tools"] == [], trigger
        assert row["tools_explicit"] is False
        assert default_tools_for_trigger(row["trigger"]) == []


def test_operator_remove_persists(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {"name": "Solve", "instruction": "Fix it.", "trigger": _issue_trigger()},
    )
    assert created["tools"] == [TOOL_OPEN_PULL_REQUEST]
    updated = store.update_routine("codey", created["id"], {"tools": []})
    assert updated["tools"] == []
    assert updated["tools_explicit"] is True
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again["tools"] == []
    assert again["tools_explicit"] is True
    # Trigger edits must not revive a removed tool.
    moved = store.update_routine(
        "codey",
        created["id"],
        {"trigger": {"kind": "interval", "seconds": 60}},
    )
    assert moved["tools"] == []
    back = store.update_routine("codey", created["id"], {"trigger": _issue_trigger()})
    assert back["tools"] == []
    assert back["tools_explicit"] is True


def test_unset_tools_follow_trigger_change(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Later",
            "instruction": "x",
            "trigger": {"kind": "interval", "seconds": 3600},
        },
    )
    assert created["tools"] == []
    assert created["tools_explicit"] is False
    issue = store.update_routine("codey", created["id"], {"trigger": _issue_trigger()})
    assert issue["tools"] == [TOOL_OPEN_PULL_REQUEST]
    assert issue["tools_explicit"] is False
    cron = store.update_routine(
        "codey",
        created["id"],
        {"trigger": {"kind": "cron", "expression": "0 3 * * *"}},
    )
    assert cron["tools"] == []
    assert cron["tools_explicit"] is False


def test_explicit_open_pr_on_non_issue_is_kept(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Manual",
            "instruction": "x",
            "trigger": {"kind": "interval", "seconds": 3600},
            "tools": [TOOL_OPEN_PULL_REQUEST],
        },
    )
    assert created["tools"] == [TOOL_OPEN_PULL_REQUEST]
    assert created["tools_explicit"] is True


def test_legacy_issue_row_without_tools_defaults_on(tmp_path, monkeypatch):
    import json

    _isolate(tmp_path, monkeypatch)
    path = tmp_path / "agent_routines.json"
    path.write_text(
        json.dumps(
            {
                "schema": 2,
                "agents": {
                    "codey": [
                        {
                            "id": "legacy-issue",
                            "name": "Legacy solver",
                            "instruction": "Fix it.",
                            "active": True,
                            "trigger": _issue_trigger(),
                            "history": [],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    store.reset_routines_cache()
    row = store.get_routine("codey", "legacy-issue")
    assert row["tools"] == [TOOL_OPEN_PULL_REQUEST]
    assert row["tools_explicit"] is False


def test_rejects_invalid_and_secretish_tool_id(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_routine(
            "codey",
            {
                "name": "Bad",
                "instruction": "x",
                "trigger": _issue_trigger(),
                "tools": ["not a tool"],
            },
        )
    except ValueError as exc:
        assert "Invalid" in str(exc) or "Unknown" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    try:
        store.create_routine(
            "codey",
            {
                "name": "Secret",
                "instruction": "x",
                "trigger": _issue_trigger(),
                "tools": ["ghp_notasecret"],
            },
        )
    except ValueError as exc:
        assert "secret" in str(exc).lower() or "Invalid" in str(exc) or "Unknown" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_run_path_invokes_open_pr_when_enabled(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    seen: list[dict] = []

    def _runner(**context):
        seen.append(dict(context))
        return {
            "ok": True,
            "updated": False,
            "skipped": False,
            "reason": "",
            "url": "https://github.com/owner/repo/pull/9",
            "auto_merge": False,
        }

    set_open_pr_runner(_runner)

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            del kwargs
            seen.append({"prompt": messages[-1]["content"]})
            yield "branch ready"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del agent_id, params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    try:
        reply = asyncio.run(
            store.run_routine_agent_job(
                "codey",
                "Investigate and fix.",
                conversation_id="conv-github-issue-42",
                tools=[TOOL_OPEN_PULL_REQUEST],
                open_pr_context={"owner_repo": "owner/repo", "title": "Fix flux", "issue_number": 42},
            )
        )
    finally:
        reset_open_pr_runner()
    assert seen
    assert any(row.get("owner_repo") == "owner/repo" for row in seen if isinstance(row, dict))
    assert "https://github.com/owner/repo/pull/9" in reply
    assert "Open Pull Request" in seen[0]["prompt"]
    record = store.load_github_event_thread("codey", "conv-github-issue-42")
    assert record is not None
    assert "https://github.com/owner/repo/pull/9" in record["messages"][-1]["content"]


def test_run_path_skips_open_pr_when_disabled(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    called = []

    def _runner(**context):
        called.append(context)
        raise AssertionError("Open PR hook must not run when the tool is off")

    set_open_pr_runner(_runner)

    class _FakeBlueprint:
        async def run(self, messages, **kwargs):
            del messages, kwargs
            yield "ok"

    async def _fake_get_blueprint_instance(agent_id, params=None):
        del agent_id, params
        return _FakeBlueprint()

    monkeypatch.setattr("swarm.core.routine_jobs.get_blueprint_instance", _fake_get_blueprint_instance)

    try:
        reply = asyncio.run(
            store.run_routine_agent_job(
                "codey",
                "Just recap.",
                conversation_id="conv-github-pr-7",
                tools=[],
                open_pr_context={"owner_repo": "owner/repo", "title": "Nope"},
            )
        )
    finally:
        reset_open_pr_runner()
    assert reply == "ok"
    assert called == []


def test_open_pr_hook_never_auto_merges_or_leaks_tokens(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    cap = open_pr_capability()
    assert cap["wired"] is True
    assert cap["auto_merge"] is False
    assert cap["token_env_set"] is False
    assert "can_live" in cap
    blob = str(cap)
    assert "ghp_" not in blob
    assert "github_pat_" not in blob

    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="Fix",
        body="Fixes #1",
        reply="",
    )
    assert result is not None
    assert result["auto_merge"] is False
    assert result.get("url") in (None, "")
    assert "token" not in str(result.get("reason") or "").lower() or "GH_TOKEN" in str(result.get("reason"))


def _live_capability():
    return {
        "id": TOOL_OPEN_PULL_REQUEST,
        "wired": True,
        "gh_available": True,
        "token_env_set": True,
        "can_live": True,
        "reasons": [],
        "auto_merge": False,
    }


class _GhResult:
    def __init__(self, returncode: int = 0, stdout: str = "", stderr: str = ""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_open_pr_hook_does_not_create_without_head_branch(monkeypatch):
    """Issue events have no head. Do not ``gh pr create`` from the server checkout."""
    reset_open_pr_runner()
    monkeypatch.setattr("swarm.core.routine_tools.open_pr_capability", _live_capability)
    calls: list[list[str]] = []

    def _boom(args):
        calls.append(list(args))
        raise AssertionError("gh must not run without a head branch")

    monkeypatch.setattr("swarm.core.routine_tools._run_gh", _boom)
    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="task-14 login",
        body="See task-14 and ask-user before merging.",
        reply="Related: https://github.com/other/repo/pull/3",
    )
    assert calls == []
    assert result is not None
    assert result["ok"] is False
    assert result["skipped"] is True
    assert result["auto_merge"] is False
    assert result.get("url") in (None, "")
    assert "branch" in result["reason"]
    assert "secret" not in result["reason"].lower()
    assert "ghp_" not in str(result)


def test_open_pr_hook_records_same_repo_url_without_calling_gh(monkeypatch):
    reset_open_pr_runner()
    monkeypatch.setattr("swarm.core.routine_tools.open_pr_capability", _live_capability)

    def _boom(args):
        del args
        raise AssertionError("gh must not run when the reply already has this repo's PR")

    monkeypatch.setattr("swarm.core.routine_tools._run_gh", _boom)
    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="Fix",
        body="Fixes #9",
        branch="fix/issue-9",
        reply="Opened https://github.com/owner/repo/pull/9",
    )
    assert result is not None
    assert result["ok"] is True
    assert result["url"] == "https://github.com/owner/repo/pull/9"
    assert result["auto_merge"] is False


def test_open_pr_hook_creates_only_with_explicit_head(monkeypatch):
    reset_open_pr_runner()
    monkeypatch.setattr("swarm.core.routine_tools.open_pr_capability", _live_capability)
    calls: list[list[str]] = []

    def _fake(args):
        calls.append(list(args))
        if len(args) > 1 and args[1] == "list":
            return _GhResult(stdout="[]")
        return _GhResult(stdout="https://github.com/owner/repo/pull/4\n")

    monkeypatch.setattr("swarm.core.routine_tools._run_gh", _fake)
    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="task-14 login",
        body="Fixes #4",
        branch="fix/issue-4",
        reply="",
    )
    assert result is not None
    assert result["ok"] is True
    assert result["url"] == "https://github.com/owner/repo/pull/4"
    assert result["auto_merge"] is False
    create = next(args for args in calls if args[:2] == ["pr", "create"])
    assert "--head" in create
    assert "fix/issue-4" in create
    assert "task-14 login" in create


def test_open_pr_hook_allows_long_task_words_and_refuses_hyphenated_keys(monkeypatch):
    """``task-management`` is not a token. ``sk-proj-`` / ``sk-ant-`` keys are.

    Kebab-case names (``xai-grok-4-fast-reasoning``) are not keys either.
    A one-character segment, an underscore, or a doubled hyphen in front
    of a long tail is still a key.
    """
    reset_open_pr_runner()
    monkeypatch.setattr("swarm.core.routine_tools.open_pr_capability", _live_capability)
    calls: list[list[str]] = []

    def _fake(args):
        calls.append(list(args))
        if len(args) > 1 and args[1] == "list":
            return _GhResult(stdout="[]")
        return _GhResult(stdout="https://github.com/owner/repo/pull/8\n")

    monkeypatch.setattr("swarm.core.routine_tools._run_gh", _fake)
    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="task-management login",
        body="\n".join(
            [
                "ask-operator-about-deploy before shipping",
                "model xai-grok-4-fast-reasoning",
                "see sk-ant-style-configuration-for-the-team",
                "short xai-" + ("c" * 19),
                "short sk-" + ("d" * 19),
            ]
        ),
        branch="fix/issue-8",
        reply="",
    )
    assert result is not None
    assert result["ok"] is True
    assert result["skipped"] is False
    assert "secret" not in str(result.get("reason") or "").lower()
    create = next(args for args in calls if args[:2] == ["pr", "create"])
    assert "task-management login" in create
    body_arg = next(arg for arg in create if "xai-grok-4-fast-reasoning" in arg)
    assert "sk-ant-style-configuration-for-the-team" in body_arg
    assert "xai-" + ("c" * 19) in body_arg
    assert "sk-" + ("d" * 19) in body_arg

    for body in (
        "sk-proj-" + "a" * 40,
        "sk-ant-api03-" + "b" * 40,
        "xai-" + "c" * 40,
        "sk-proj-5-" + "A" * 30,
        "sk-proj-" + "Ab_cd-" + "E" * 25,
        "sk-proj--" + "F" * 25,
        "xai-5-" + "G" * 25,
    ):
        calls.clear()
        refused = run_open_pr_if_enabled(
            [TOOL_OPEN_PULL_REQUEST],
            owner_repo="owner/repo",
            title="Fix",
            body=body,
            branch="fix/issue-8",
            reply="",
        )
        assert refused is not None
        assert refused["ok"] is False
        assert refused["skipped"] is True
        assert calls == []
        assert body not in str(refused)
        assert "sk-" not in str(refused)
        assert "xai-" not in str(refused)
        assert "secret" in refused["reason"].lower()


def test_open_pr_hook_refuses_secret_body(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    result = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="Fix",
        body="use ghp_notarealtokenhere",
        reply="",
    )
    assert result is not None
    assert result["ok"] is False
    assert result["skipped"] is True
    assert "secret" in result["reason"].lower()
    assert "ghp_" not in result["reason"]


def test_open_pr_skips_without_head_and_ignores_foreign_reply_url(monkeypatch):
    """Issue events have no head. ``gh pr create`` must not use the server checkout.

    A PR URL for a different repo in the agent reply is not this routine's PR.
    """
    monkeypatch.setattr(
        "swarm.core.routine_tools.open_pr_capability",
        lambda: {
            "can_live": True,
            "reasons": [],
            "auto_merge": False,
            "wired": True,
            "gh_available": True,
            "token_env_set": True,
        },
    )
    calls: list[list[str]] = []

    def _refuse(args):
        calls.append(list(args))
        raise AssertionError(f"gh must not run without a head: {args}")

    monkeypatch.setattr("swarm.core.routine_tools._run_gh", _refuse)
    foreign = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="Fix",
        body="Fixes #1",
        branch="",
        reply="Opened https://github.com/other/repo/pull/9",
    )
    assert calls == []
    assert foreign is not None
    assert foreign["skipped"] is True
    assert foreign["ok"] is False
    assert "head" in foreign["reason"]

    matched = run_open_pr_if_enabled(
        [TOOL_OPEN_PULL_REQUEST],
        owner_repo="owner/repo",
        title="Fix",
        reply="See https://github.com/owner/repo/pull/9",
    )
    assert calls == []
    assert matched is not None
    assert matched["ok"] is True
    assert matched["url"] == "https://github.com/owner/repo/pull/9"


def test_issue_solver_preset_includes_open_pr():
    solver = next(p for p in store.ROUTINE_PRESETS if p["key"] == "github_issue_solver")
    reviewer = next(p for p in store.ROUTINE_PRESETS if p["key"] == "github_pr_reviewer")
    assert TOOL_OPEN_PULL_REQUEST in solver["tools"]
    assert reviewer.get("tools") in (None, [])

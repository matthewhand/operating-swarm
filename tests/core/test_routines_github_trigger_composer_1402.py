"""#1402 — GitHub trigger composer serializes onto existing github_event plumbing."""

from __future__ import annotations

from swarm.core import routines as store


def _github_event_trigger(event_type: str, owner_repo: str = "owner/repo", **filters):
    trigger = {"kind": "github_event", "event_type": event_type, "owner_repo": owner_repo}
    if filters:
        trigger["filters"] = filters
    return trigger


def _issue_comment_payload(*, number=17, pull_request=False, author="octocat", body="Looks flaky"):
    issue = {
        "number": number,
        "title": "Flaky login",
        "body": "Repro on main.",
        "html_url": f"https://github.com/owner/repo/issues/{number}",
        "user": {"login": "mona"},
        "labels": [],
    }
    if pull_request:
        issue["html_url"] = f"https://github.com/owner/repo/pull/{number}"
        issue["pull_request"] = {"url": f"https://api.github.com/repos/owner/repo/pulls/{number}"}
    return {
        "action": "created",
        "issue": issue,
        "comment": {"body": body, "user": {"login": author}},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": author},
    }


def _issue_assigned_payload(*, number=17, author="octocat"):
    return {
        "action": "assigned",
        "issue": {
            "number": number,
            "title": "Flaky login",
            "body": "Repro on main.",
            "html_url": f"https://github.com/owner/repo/issues/{number}",
            "user": {"login": "mona"},
            "labels": [],
        },
        "assignee": {"login": "mona"},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": author},
    }


def test_public_trigger_round_trips_issue_comment_issue_assigned_pr_comment():
    issue_comment = store.public_trigger(
        _github_event_trigger("issue_comment.created", object_kind="issue")
    )
    assert issue_comment["kind"] == "github_event"
    assert issue_comment["event_type"] == "issue_comment.created"
    assert issue_comment["owner_repo"] == "owner/repo"
    assert issue_comment["filters"]["object_kind"] == "issue"
    assert issue_comment == store.public_trigger(issue_comment)

    assigned = store.public_trigger(
        _github_event_trigger("issues.assigned", object_kind="issue", actor="mona")
    )
    assert assigned["event_type"] == "issues.assigned"
    assert assigned["filters"]["object_kind"] == "issue"
    assert assigned["filters"]["actor"] == "mona"
    assert assigned == store.public_trigger(assigned)

    pr_comment = store.public_trigger(
        _github_event_trigger("issue_comment.created", object_kind="pull_request")
    )
    assert pr_comment["event_type"] == "issue_comment.created"
    assert pr_comment["filters"]["object_kind"] == "pull_request"
    assert pr_comment == store.public_trigger(pr_comment)


def test_issue_comment_and_assigned_fire_matching_routines(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)

    comment = store.create_routine(
        "codey",
        {
            "name": "Issue comments",
            "instruction": "Reply to the comment.",
            "trigger": _github_event_trigger("issue_comment.created", object_kind="issue"),
        },
    )
    assigned = store.create_routine(
        "codey",
        {
            "name": "Issue assigned",
            "instruction": "Pick up the issue.",
            "trigger": _github_event_trigger("issues.assigned", object_kind="issue"),
        },
    )
    pr_comment = store.create_routine(
        "codey",
        {
            "name": "PR comments",
            "instruction": "Reply on the PR.",
            "trigger": _github_event_trigger("issue_comment.created", object_kind="pull_request"),
        },
    )

    fired_issue_comment = store.deliver_github_event(
        _issue_comment_payload(),
        event_header="issue_comment",
    )
    assert {row["routine"]["id"] for row in fired_issue_comment} == {comment["id"]}
    comment_hist = store.get_routine("codey", comment["id"])["history"][0]
    assert comment_hist["event"] == "issue_comment.created #17"
    assert comment_hist["conversation_id"] == "conv-github-issue-17"
    assert "Looks flaky" in store.fired_prompts()[0]["instruction"]
    assert "octocat" in store.fired_prompts()[0]["instruction"]

    fired_assigned = store.deliver_github_event(
        _issue_assigned_payload(),
        event_header="issues",
    )
    assert {row["routine"]["id"] for row in fired_assigned} == {assigned["id"]}
    assigned_hist = store.get_routine("codey", assigned["id"])["history"][0]
    assert assigned_hist["event"] == "issues.assigned #17"
    assert assigned_hist["conversation_id"] == "conv-github-issue-17"

    fired_pr_comment = store.deliver_github_event(
        _issue_comment_payload(number=42, pull_request=True, body="Ship it"),
        event_header="issue_comment",
    )
    assert {row["routine"]["id"] for row in fired_pr_comment} == {pr_comment["id"]}
    pr_hist = store.get_routine("codey", pr_comment["id"])["history"][0]
    assert pr_hist["event"] == "issue_comment.created #42"
    assert pr_hist["conversation_id"] == "conv-github-pr-42"

    store.reset_routines_cache()
    store.set_instruction_runner(None)


def test_actor_filter_on_github_event_skips_other_authors(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)

    store.create_routine(
        "codey",
        {
            "name": "Mona only",
            "instruction": "Mona commented.",
            "trigger": _github_event_trigger(
                "issue_comment.created",
                object_kind="issue",
                actor="mona",
            ),
        },
    )
    assert store.deliver_github_event(_issue_comment_payload(author="octocat"), event_header="issue_comment") == []
    fired = store.deliver_github_event(_issue_comment_payload(author="mona"), event_header="issue_comment")
    assert len(fired) == 1

    store.reset_routines_cache()
    store.set_instruction_runner(None)


def test_from_chip_matches_the_performer_not_the_issue_author(tmp_path, monkeypatch):
    """#1426 — "from mona" is the user who did the action.

    Assigned used to match issue.user (the opener). A login chip matches
    sender for assignments and review requests, the comment author for
    comments, and sender.login (not pusher.name) for pushes.
    """
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)

    store.create_routine(
        "codey",
        {
            "name": "Assigned by mona",
            "instruction": "Pick up the assigned issue.",
            "trigger": _github_event_trigger("issues.assigned", object_kind="issue", actor="mona"),
        },
    )
    assigned_by_mona = {
        "action": "assigned",
        "issue": {
            "number": 17,
            "title": "Flaky login",
            "body": "Repro on main.",
            "html_url": "https://github.com/owner/repo/issues/17",
            "user": {"login": "octocat"},
            "assignee": {"login": "hubot"},
            "labels": [],
        },
        "assignee": {"login": "hubot"},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "mona"},
    }
    opener_assigned = {
        **assigned_by_mona,
        "sender": {"login": "octocat"},
    }
    assignee_assigned = {
        **assigned_by_mona,
        "sender": {"login": "hubot"},
    }
    assert store.deliver_github_event(opener_assigned, event_header="issues") == []
    assert store.deliver_github_event(assignee_assigned, event_header="issues") == []
    fired = store.deliver_github_event(assigned_by_mona, event_header="issues")
    assert len(fired) == 1
    assert "Actor: mona" in store.fired_prompts()[-1]["instruction"]
    assert "Author: octocat" in store.fired_prompts()[-1]["instruction"]

    store.create_routine(
        "codey",
        {
            "name": "Review requested by mona",
            "instruction": "Review.",
            "trigger": _github_event_trigger("pull_request.review_requested", actor="mona"),
        },
    )
    review_by_mona = {
        "action": "review_requested",
        "pull_request": {
            "number": 9,
            "title": "Add webhook routines",
            "body": "Please review.",
            "html_url": "https://github.com/owner/repo/pull/9",
            "user": {"login": "octocat"},
            "base": {"ref": "main"},
        },
        "requested_reviewer": {"login": "hubot"},
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "mona"},
    }
    assert store.deliver_github_event(
        {**review_by_mona, "sender": {"login": "octocat"}},
        event_header="pull_request",
    ) == []
    assert len(store.deliver_github_event(review_by_mona, event_header="pull_request")) == 1

    comment_by_mona = _issue_comment_payload(author="mona")
    comment_by_mona["issue"]["user"] = {"login": "octocat"}
    comment_by_mona["sender"] = {"login": "hubot"}
    store.create_routine(
        "codey",
        {
            "name": "Comments from mona",
            "instruction": "Reply.",
            "trigger": _github_event_trigger("issue_comment.created", object_kind="issue", actor="mona"),
        },
    )
    assert len(store.deliver_github_event(comment_by_mona, event_header="issue_comment")) == 1
    assert store.deliver_github_event(
        _issue_comment_payload(author="hubot"),
        event_header="issue_comment",
    ) == []

    store.create_routine(
        "codey",
        {
            "name": "Pushes from mona",
            "instruction": "Note the push.",
            "trigger": _github_event_trigger("push", actor="mona"),
        },
    )
    push = {
        "ref": "refs/heads/main",
        "after": "abc1234deadbeef",
        "repository": {"full_name": "owner/repo"},
        "pusher": {"name": "Mona Lisa"},
        "head_commit": {"id": "abc1234deadbeef", "message": "Ship it"},
        "sender": {"login": "mona"},
    }
    assert store.deliver_github_event(
        {**push, "sender": {"login": "Mona Lisa"}},
        event_header="push",
    ) == []
    assert len(store.deliver_github_event(push, event_header="push")) == 1

    store.reset_routines_cache()
    store.set_instruction_runner(None)


def test_rejects_unknown_object_kind():
    try:
        store.public_trigger(
            _github_event_trigger("issue_comment.created", object_kind="discussion")
        )
    except ValueError as exc:
        assert "object_kind" in str(exc)
    else:
        raise AssertionError("expected ValueError")

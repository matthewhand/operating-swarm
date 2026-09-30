"""REQ-80 routines store — CRUD, Test run, fake GitHub PR-merge delivery."""

from swarm.core import routines as store


def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def test_list_empty_then_create(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    assert store.list_routines("codey") == []
    created = store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "instruction": "Summarize the merged pull request.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
        },
    )
    assert created["name"] == "Ship notes"
    assert created["active"] is True
    assert created["model"] == ""
    assert created["trigger"]["kind"] == "github_pr_merged"
    assert created["trigger"]["owner_repo"] == "owner/repo"
    assert created["trigger"]["event"] == "merged"
    assert created["trigger"]["actor"] == "anyone"
    assert created["history"] == []
    assert store.trigger_summary(created["trigger"]) == "When a PR merges in owner/repo…"
    listed = store.list_routines("codey")
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_update_active_and_delete(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine("codey", {"name": "Nightly"})
    updated = store.update_routine("codey", created["id"], {"active": False, "name": "Paused"})
    assert updated["active"] is False
    assert updated["name"] == "Paused"
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again is not None
    assert again["active"] is False
    assert store.delete_routine("codey", created["id"]) is True
    assert store.get_routine("codey", created["id"]) is None
    assert store.delete_routine("codey", created["id"]) is False


def test_test_run_is_dry_run_preview_without_firing(tmp_path, monkeypatch):
    """#1405 — Test is a documented preview, not a live fire."""
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "instruction": "Write the merge recap.",
            "model": "orchestration",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "owner/repo"},
        },
    )
    ran = store.test_run("codey", created["id"])
    assert ran["history"] == []
    preview = ran["preview"]
    assert preview["dry_run"] is True
    assert preview["side_effects"] == "none"
    assert preview["prompt"] == "Write the merge recap."
    assert preview["model"] == "orchestration"
    assert preview["trigger_kind"] == "github_pr_merged"
    assert "owner/repo" in preview["trigger_summary"]
    assert "No messages sent" in preview["note"]
    assert "token" not in preview["prompt"].lower()
    assert store.fired_prompts() == []
    again = store.get_routine("codey", created["id"])
    assert again is not None
    assert again["history"] == []


def test_save_inactive_draft_and_model_round_trip(tmp_path, monkeypatch):
    """#1405 — Save persists a draft without requiring Active; model stores."""
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Draft recap",
            "instruction": "Summarize the merge.",
            "active": False,
            "model": "auxiliary",
        },
    )
    assert created["active"] is False
    assert created["model"] == "auxiliary"
    store.reset_routines_cache()
    loaded = store.get_routine("codey", created["id"])
    assert loaded is not None
    assert loaded["active"] is False
    assert loaded["model"] == "auxiliary"
    updated = store.update_routine(
        "codey",
        created["id"],
        {"active": True, "model": "delegation", "instruction": "Keep the draft."},
    )
    assert updated["active"] is True
    assert updated["model"] == "delegation"
    assert updated["instruction"] == "Keep the draft."
    store.reset_routines_cache()
    again = store.get_routine("codey", created["id"])
    assert again is not None
    assert again["active"] is True
    assert again["model"] == "delegation"


def test_model_rejects_secrets(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_routine("codey", {"name": "No", "model": "ghp_abcdefghijklmnopqrstuvwxyz012345"})
        raise AssertionError("expected secret rejection")
    except ValueError as exc:
        assert "secrets" in str(exc).lower()


def test_inactive_routine_does_not_fire_on_fake_merge(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    active = store.create_routine(
        "codey",
        {
            "name": "Active ship",
            "instruction": "Note the merge.",
            "trigger": {"owner_repo": "owner/repo"},
        },
    )
    inactive = store.create_routine(
        "codey",
        {
            "name": "Paused ship",
            "instruction": "Should not run.",
            "active": False,
            "trigger": {"owner_repo": "owner/repo"},
        },
    )
    other = store.create_routine(
        "codey",
        {
            "name": "Other repo",
            "instruction": "Wrong repo.",
            "trigger": {"owner_repo": "acme/other"},
        },
    )
    fired = store.deliver_github_pr_merged({"owner_repo": "owner/repo", "actor": "octocat"})
    ids = {row["routine"]["id"] for row in fired}
    assert active["id"] in ids
    assert inactive["id"] not in ids
    assert other["id"] not in ids
    assert store.get_routine("codey", inactive["id"])["history"] == []
    assert store.get_routine("codey", other["id"])["history"] == []
    ran = store.get_routine("codey", active["id"])
    assert ran["history"][0]["source"] == "github_pr_merged"
    assert store.fired_prompts()[0]["instruction"] == "Note the merge."


def test_github_shaped_payload_and_actor_filter(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    anyone = store.create_routine(
        "codey",
        {"name": "Anyone", "instruction": "Anyone recap.", "trigger": {"owner_repo": "owner/repo"}},
    )
    only_me = store.create_routine(
        "codey",
        {
            "name": "Only octocat",
            "instruction": "Octocat recap.",
            "trigger": {"owner_repo": "owner/repo", "actor": "octocat"},
        },
    )
    fired = store.deliver_github_pr_merged(
        {
            "action": "closed",
            "pull_request": {"merged": True, "merged_by": {"login": "mona"}},
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "mona"},
        }
    )
    ids = {row["routine"]["id"] for row in fired}
    assert anyone["id"] in ids
    assert only_me["id"] not in ids


def test_trailing_slash_full_name_still_matches_merge(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {"name": "Ship", "instruction": "Note the merge.", "trigger": {"owner_repo": "owner/repo"}},
    )
    fired = store.deliver_github_pr_merged(
        {
            "action": "closed",
            "pull_request": {"merged": True},
            "repository": {"full_name": "owner/repo/"},
            "sender": {"login": "mona"},
        }
    )
    assert [row["routine"]["id"] for row in fired] == [created["id"]]


def test_merge_event_uses_the_same_repo_pairing(tmp_path, monkeypatch):
    """Merge delivery pairs a repository object the same way a trigger does.

    A slash-only or slash-less ``full_name`` must not hide ``name`` or the
    object's owner. A qualified ``full_name`` still wins, and a bare name
    with no owner is still rejected.
    """
    _isolate(tmp_path, monkeypatch)
    cases = [
        (
            {"repository": {"full_name": "/", "name": "widgets", "owner": {"login": "/", "name": "acme"}}},
            "acme/widgets",
        ),
        (
            {"repository": {"full_name": "   ", "name": "widgets", "owner": {"login": "acme"}}},
            "acme/widgets",
        ),
        (
            {"repository": {"full_name": "widgets", "owner": {"login": "acme"}}},
            "acme/widgets",
        ),
        (
            {"owner": "outer", "repository": {"full_name": "widgets/", "owner": {"login": "inner"}}},
            "inner/widgets",
        ),
        (
            {"owner": {"login": "/", "name": "acme"}, "repo": "widgets"},
            "acme/widgets",
        ),
        (
            {"owner_repo": "/", "repository": "acme/widgets"},
            "acme/widgets",
        ),
        (
            {"repository_full_name": "acme/widgets/"},
            "acme/widgets",
        ),
        (
            {
                "owner": "outer",
                "repository": {"full_name": "acme/widgets/", "name": "nope", "owner": {"login": "inner"}},
            },
            "acme/widgets",
        ),
    ]
    for extra, expected in cases:
        payload = {"action": "closed", "pull_request": {"merged": True}, "sender": {"login": "mona"}, **extra}
        got = store.parse_github_merge_event(payload)["owner_repo"]
        assert got == expected, extra

    created = store.create_routine(
        "codey",
        {"name": "Ship", "instruction": "Note the merge.", "trigger": {"owner_repo": "acme/widgets"}},
    )
    fired = store.deliver_github_pr_merged(
        {
            "action": "closed",
            "pull_request": {"merged": True},
            "repository": {"full_name": "widgets", "owner": {"login": "acme"}},
            "sender": {"login": "mona"},
        }
    )
    assert [row["routine"]["id"] for row in fired] == [created["id"]]
    try:
        store.parse_github_merge_event(
            {"action": "closed", "pull_request": {"merged": True}, "repository": {"full_name": "widgets"}}
        )
    except ValueError as exc:
        assert "owner/repo" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_rejects_unknown_trigger_and_bad_repo(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_routine("codey", {"trigger": {"kind": "file_watch"}})
    except ValueError as exc:
        assert "kind" in str(exc).lower() or "Supported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
    try:
        store.create_routine("codey", {"trigger": {"owner_repo": "not-a-repo"}})
    except ValueError as exc:
        assert "owner/repo" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_interval_run_now_and_tick(tmp_path, monkeypatch):
    from datetime import datetime, timedelta, timezone

    _isolate(tmp_path, monkeypatch)
    created = store.create_routine(
        "codey",
        {
            "name": "Hourly",
            "instruction": "Recap the hour.",
            "trigger": {"kind": "interval", "seconds": 60},
        },
    )
    assert created["trigger"]["kind"] == "interval"
    assert store.trigger_summary(created["trigger"]) == "Every 1 min…"
    ran = store.run_now("codey", created["id"])
    assert ran["history"][0]["source"] == "run_now"
    assert ran["history"][0]["duration_ms"] >= 0

    now = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
    row = store.get_routine("codey", created["id"])
    row["history"] = []
    row["next_run"] = (now - timedelta(seconds=1)).isoformat()
    store._persist_agent("codey", [row])
    fired = store.tick_due_routines(now)
    assert fired
    assert store.get_routine("codey", created["id"])["history"][0]["source"] == "schedule"


def test_mailbox_message_delivery(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    matching = store.create_routine(
        "codey",
        {
            "name": "Prove",
            "instruction": "Handle the mailbox note.",
            "trigger": {"kind": "mailbox_message", "sender": "support", "pattern": "prove"},
        },
    )
    store.create_routine(
        "codey",
        {
            "name": "Other",
            "instruction": "Ignore.",
            "trigger": {"kind": "mailbox_message", "sender": "support", "pattern": "unrelated"},
        },
    )
    fired = store.deliver_mailbox_message(
        {"sender": "support", "content": "please prove the remote health"}
    )
    ids = {row["routine"]["id"] for row in fired}
    assert matching["id"] in ids
    assert len(ids) == 1
    assert store.get_routine("codey", matching["id"])["history"][0]["source"] == "mailbox_message"


def test_schema_v2_reads_v1_file(tmp_path, monkeypatch):
    import json

    _isolate(tmp_path, monkeypatch)
    path = tmp_path / "agent_routines.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "agents": {
                    "codey": [
                        {
                            "id": "legacy",
                            "name": "Legacy",
                            "instruction": "Old recap.",
                            "active": True,
                            "trigger": {
                                "kind": "github_pr_merged",
                                "owner_repo": "owner/repo",
                                "event": "merged",
                                "actor": "anyone",
                            },
                            "history": [],
                        }
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    store.reset_routines_cache()
    row = store.get_routine("codey", "legacy")
    assert row is not None
    assert row["trigger"]["kind"] == "github_pr_merged"
    assert row["name"] == "Legacy"


def test_rejects_secret_looking_actor(tmp_path, monkeypatch):
    _isolate(tmp_path, monkeypatch)
    try:
        store.create_routine("codey", {"trigger": {"owner_repo": "owner/repo", "actor": "ghp_notasecret"}})
    except ValueError as exc:
        assert "login" in str(exc)
    else:
        raise AssertionError("expected ValueError")

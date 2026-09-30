"""Routines-domain pack (#1394): fill-ins + import pending enable."""

from pathlib import Path

import pytest

from swarm.core import routines as store
from swarm.core.routine_pack import (
    PackValidationError,
    apply_fill_ins,
    build_pack,
    import_pack,
    routines_section_for_pack,
    validate_pack,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "agent_routines_pack.json"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    store.reset_routines_cache()
    store.set_instruction_runner(None)
    yield
    store.reset_routines_cache()
    store.set_instruction_runner(None)


def _solver_pack(**overrides) -> dict:
    row = {
        "name": "GitHub Issue Solver (Issue → PR)",
        "instruction": "Investigate the issue in {{owner_repo}} and open a fix PR.",
        "trigger": {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner_repo": "{{owner_repo}}",
            "filters": {"exclude_authors": ["open-swarm[bot]"]},
        },
    }
    row.update(overrides)
    return {"routines": [row]}


def test_validate_pack_extracts_owner_repo_fill_in():
    pack = validate_pack(_solver_pack())
    assert pack["object"] == "agent_routines_pack"
    assert pack["kind"] == "agent_routines_pack"
    keys = {slot["key"] for slot in pack["fill_ins"]}
    assert keys == {"owner_repo"}
    slot = pack["fill_ins"][0]
    assert slot["required"] is True
    assert slot["label"] == "GitHub owner/repo"
    assert pack["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert "history" not in pack["routines"][0]
    assert "id" not in pack["routines"][0]


def test_empty_github_owner_repo_becomes_fill_in():
    pack = validate_pack(
        {
            "routines": [
                {
                    "name": "Preset solver",
                    "instruction": "Investigate the issue.",
                    "trigger": {
                        "kind": "github_event",
                        "event_type": "issues.opened",
                        "owner_repo": "",
                    },
                }
            ]
        }
    )
    assert pack["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert any(slot["key"] == "owner_repo" for slot in pack["fill_ins"])


def test_fixture_is_secret_free():
    import json

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    blob = json.dumps(raw).lower()
    assert "sk-" not in blob
    assert "ghp_" not in blob
    assert "bearer " not in blob
    pack = validate_pack(raw)
    assert pack["fill_ins"][0]["key"] == "owner_repo"


def test_secrets_in_instruction_are_refused():
    with pytest.raises(PackValidationError, match="secrets"):
        validate_pack(_solver_pack(instruction="Use Bearer sk-abcdefghijklmnopqrst"))


def test_binary_fields_are_refused():
    with pytest.raises(PackValidationError, match="prose only") as exc:
        validate_pack(_solver_pack(assets=["helper.py"]))
    assert exc.value.code == "pack_binaries"


def test_empty_routines_fails():
    with pytest.raises(PackValidationError, match="routines") as exc:
        validate_pack({"routines": []})
    assert exc.value.code == "pack_routines_missing"


def test_build_pack_from_seat_and_presets():
    store.create_routine(
        "codey",
        {
            "name": "Nightly recap",
            "instruction": "Summarize the day.",
            "trigger": {"kind": "interval", "seconds": 86400},
        },
    )
    seat = build_pack("codey")
    assert [row["name"] for row in seat["routines"]] == ["Nightly recap"]
    assert seat["fill_ins"] == []

    with_presets = build_pack("codey", include_presets=True)
    names = {row["name"] for row in with_presets["routines"]}
    assert "Nightly recap" in names
    assert any("Issue Solver" in name for name in names)
    assert any(slot["key"] == "owner_repo" for slot in with_presets["fill_ins"])


def test_routines_section_empty_when_seat_has_none():
    section = routines_section_for_pack("writer")
    assert section == {"routines": [], "fill_ins": []}


def test_apply_fill_ins_substitutes_nested_trigger():
    filled = apply_fill_ins(
        {"owner_repo": "{{owner_repo}}", "note": "see {{owner_repo}}"},
        {"owner_repo": "acme/widgets"},
    )
    assert filled == {"owner_repo": "acme/widgets", "note": "see acme/widgets"}


def test_import_applies_fill_ins_and_stays_pending():
    imported = import_pack("writer", _solver_pack(), fill_ins={"owner_repo": "acme/widgets"})
    assert imported["object"] == "agent_routines_pack_import"
    assert imported["pending_enable"] is True
    assert imported["created_count"] == 1
    assert imported["fill_ins_applied"] == ["owner_repo"]
    assert imported["fill_ins_remaining"] == []
    row = imported["routines"][0]
    assert row["active"] is False
    assert row["trigger"]["owner_repo"] == "acme/widgets"
    assert "{{" not in row["instruction"]
    stored = store.list_routines("writer")
    assert len(stored) == 1
    assert stored[0]["active"] is False


def _issue_opened(owner_repo: str = "acme/widgets", number: int = 12) -> dict:
    return {
        "action": "opened",
        "issue": {
            "number": number,
            "title": "Bug",
            "body": "Repro.",
            "html_url": f"https://github.com/{owner_repo}/issues/{number}",
            "user": {"login": "octocat"},
            "labels": [],
        },
        "repository": {"full_name": owner_repo},
        "sender": {"login": "octocat"},
    }


def test_import_without_fill_ins_keeps_placeholder_and_does_not_fire():
    imported = import_pack("codey", _solver_pack())
    row = imported["routines"][0]
    assert row["active"] is False
    assert row["trigger"]["owner_repo"] == "{{owner_repo}}"
    remaining = {slot["key"] for slot in imported["fill_ins_remaining"]}
    assert remaining == {"owner_repo"}
    fired = store.deliver_github_event(_issue_opened(), event_header="issues")
    assert fired == []
    assert store.get_routine("codey", row["id"])["history"] == []


def test_import_pending_does_not_fire_even_after_fill_in():
    imported = import_pack("codey", _solver_pack(), fill_ins={"owner_repo": "acme/widgets"})
    row = imported["routines"][0]
    fired = store.deliver_github_event(_issue_opened(number=4), event_header="issues")
    assert fired == []
    enabled = store.update_routine("codey", row["id"], {"active": True})
    assert enabled["active"] is True
    fired = store.deliver_github_event(_issue_opened(number=5), event_header="issues")
    assert len(fired) == 1
    assert fired[0]["routine"]["id"] == row["id"]


def test_normalize_owner_repo_accepts_fill_in_placeholder():
    assert store.normalize_owner_repo("{{owner_repo}}", allow_fill_in=True) == "{{owner_repo}}"
    assert store.fill_in_token("{{ owner_repo }}") == "{{owner_repo}}"
    with pytest.raises(ValueError, match="owner/repo"):
        store.normalize_owner_repo("{{owner_repo}}")
    with pytest.raises(ValueError, match="owner/repo"):
        store.normalize_owner_repo("{{cron}}", allow_fill_in=True)


def test_repository_alias_is_not_rewritten_to_fill_in():
    pack = validate_pack(
        {
            "routines": [
                {
                    "name": "Ship notes",
                    "instruction": "Summarize merges.",
                    "trigger": {"kind": "github_pr_merged", "repository": "acme/widgets"},
                }
            ]
        }
    )
    assert pack["routines"][0]["trigger"]["owner_repo"] == "acme/widgets"
    assert pack["fill_ins"] == []


def test_named_repo_aliases_are_not_replaced_with_a_fill_in():
    """A repo named beside a blank slot, or as a GitHub object, is the repo.

    Whitespace ``owner_repo`` used to hide ``repository``. A ``full_name``
    object used to normalize to an empty pr-merged trigger.
    """
    triggers = [
        {"kind": "github_pr_merged", "owner_repo": "  ", "repository": "acme/widgets"},
        {"kind": "github_pr_merged", "owner_repo": "", "repo": "acme/widgets"},
        {"kind": "github_pr_merged", "repository": {"full_name": "acme/widgets"}},
        {
            "kind": "github_pr_merged",
            "repository": {"name": "widgets", "owner": {"login": "acme"}},
        },
        {"kind": "github_pr_merged", "owner": "acme", "repo": "widgets"},
        {
            "kind": "github_event",
            "event_type": "issues.opened",
            "repository": {"full_name": "acme/widgets"},
        },
        {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner_repo": "   ",
            "repository": "acme/widgets",
        },
    ]
    for trigger in triggers:
        assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets", trigger
        pack = validate_pack(
            {
                "routines": [
                    {
                        "name": "Ship notes",
                        "instruction": "Summarize.",
                        "trigger": trigger,
                    }
                ]
            }
        )
        assert pack["routines"][0]["trigger"]["owner_repo"] == "acme/widgets", trigger
        assert pack["fill_ins"] == [], trigger


def test_whitespace_owner_repo_without_alias_is_still_a_fill_in():
    pack = validate_pack(
        {
            "routines": [
                {
                    "name": "Preset solver",
                    "instruction": "Investigate the issue.",
                    "trigger": {
                        "kind": "github_event",
                        "event_type": "issues.opened",
                        "owner_repo": "   ",
                    },
                }
            ]
        }
    )
    assert pack["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert any(slot["key"] == "owner_repo" for slot in pack["fill_ins"])


def test_split_repo_objects_keep_the_named_repo():
    """Owner and a repo object, or a qualified name, stay owner/repo.

    A ``repo`` object used to be stringified into the owner pair and
    rejected. A ``name`` that already contained a slash was prefixed
    again. A slash-less ``full_name`` hid ``owner`` + ``name``. A blank
    ``login`` hid ``owner.name``. A leading slash on a bare name blocked
    the pair.
    """
    triggers = [
        {"kind": "github_pr_merged", "owner": "acme", "repo": {"name": "widgets"}},
        {
            "kind": "github_pr_merged",
            "owner": {"login": "acme"},
            "repo": {"name": "widgets"},
        },
        {
            "kind": "github_pr_merged",
            "repository": {"owner": {"login": "acme"}, "name": "acme/widgets"},
        },
        {"kind": "github_pr_merged", "repository": {"name": "acme/widgets"}},
        {
            "kind": "github_pr_merged",
            "repository": {
                "full_name": "widgets",
                "owner": {"login": "acme"},
                "name": "widgets",
            },
        },
        {
            "kind": "github_pr_merged",
            "repository": {
                "owner": {"login": "  ", "name": "acme"},
                "name": "widgets",
            },
        },
        {"kind": "github_pr_merged", "owner": "acme", "repo": "/widgets"},
        {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner": "acme",
            "repo": {"full_name": "widgets"},
        },
    ]
    for trigger in triggers:
        assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets", trigger
        pack = validate_pack(
            {
                "routines": [
                    {
                        "name": "Ship notes",
                        "instruction": "Summarize.",
                        "trigger": trigger,
                    }
                ]
            }
        )
        assert pack["routines"][0]["trigger"]["owner_repo"] == "acme/widgets", trigger
        assert pack["fill_ins"] == [], trigger


def test_slashless_full_name_without_owner_is_still_invalid():
    with pytest.raises(PackValidationError, match="owner/repo"):
        validate_pack(
            {
                "routines": [
                    {
                        "name": "Ship notes",
                        "instruction": "Summarize.",
                        "trigger": {
                            "kind": "github_pr_merged",
                            "repository": {"full_name": "widgets"},
                        },
                    }
                ]
            }
        )


def test_whitespace_owner_without_a_repo_is_a_fill_in():
    pack = validate_pack(
        {
            "routines": [
                {
                    "name": "Preset solver",
                    "instruction": "Investigate the issue.",
                    "trigger": {
                        "kind": "github_event",
                        "event_type": "issues.opened",
                        "owner": "   ",
                    },
                }
            ]
        }
    )
    assert pack["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert any(slot["key"] == "owner_repo" for slot in pack["fill_ins"])


def test_repository_alias_pairs_with_outer_owner():
    """``repository`` is the same pair as ``repo`` when the name is bare.

    A repository object used to be returned before the outer owner was
    applied, so ``{name: widgets}`` became an empty pr-merged repo and
    ``{full_name: widgets}`` failed validation.
    """
    triggers = [
        {"kind": "github_pr_merged", "owner": "acme", "repository": {"name": "widgets"}},
        {"kind": "github_pr_merged", "owner": "acme", "repository": {"full_name": "widgets"}},
        {"kind": "github_pr_merged", "owner": "acme", "repository": "widgets"},
        {
            "kind": "github_pr_merged",
            "owner": {"login": "  ", "name": "acme"},
            "repository": {"name": "widgets"},
        },
        {
            "kind": "github_event",
            "event_type": "issues.opened",
            "owner": "acme",
            "repository": {"name": "widgets"},
        },
        {
            "kind": "github_pr_merged",
            "owner_repo": {"full_name": "widgets"},
            "repository": "acme/widgets",
        },
    ]
    for trigger in triggers:
        assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets", trigger
        pack = validate_pack(
            {
                "routines": [
                    {
                        "name": "Ship notes",
                        "instruction": "Summarize.",
                        "trigger": trigger,
                    }
                ]
            }
        )
        assert pack["routines"][0]["trigger"]["owner_repo"] == "acme/widgets", trigger
        assert pack["fill_ins"] == [], trigger


def test_surrounding_slashes_do_not_block_the_pair():
    triggers = [
        {"kind": "github_pr_merged", "owner": "acme", "repo": "widgets/"},
        {"kind": "github_pr_merged", "owner": "acme", "repo": {"name": "widgets/"}},
        {"kind": "github_pr_merged", "repository": {"full_name": "acme/widgets/"}},
        {"kind": "github_pr_merged", "owner_repo": "/acme/widgets/"},
    ]
    for trigger in triggers:
        assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets", trigger


def test_slashless_full_name_does_not_hide_the_repo_name():
    trigger = {
        "kind": "github_pr_merged",
        "owner": "acme",
        "repo": {"full_name": "nope", "name": "widgets"},
    }
    assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets"


def test_slash_only_repo_does_not_hide_the_name():
    """A slash-only ``repo`` is unnamed, same as whitespace.

    ``/`` used to count as present, so ``name`` was dropped and the pack
    stored a blank pr-merged repo.
    """
    triggers = [
        {"kind": "github_pr_merged", "owner": "acme", "repository": {"repo": "/", "name": "widgets"}},
        {"kind": "github_pr_merged", "owner": "acme", "repository": {"repo": "///", "name": "widgets"}},
        {"kind": "github_pr_merged", "owner": {"login": "/", "name": "acme"}, "repo": "widgets"},
        {"kind": "github_pr_merged", "owner": "/acme/", "repo": "/widgets/"},
        {"kind": "github_pr_merged", "owner": {"login": "/acme/"}, "repository": {"name": "widgets/"}},
    ]
    for trigger in triggers:
        assert store.public_trigger(trigger)["owner_repo"] == "acme/widgets", trigger


def test_object_owner_pairs_with_slashless_full_name():
    """The repository object's owner completes a slash-less ``full_name``.

    That owner wins over a different trigger-level owner. A trailing slash
    on a qualified name still normalizes.
    """
    paired = {"kind": "github_pr_merged", "repository": {"full_name": "widgets", "owner": {"login": "acme"}}}
    inner = {
        "kind": "github_pr_merged",
        "owner": "outer",
        "repository": {"full_name": "widgets/", "owner": {"login": "inner"}},
    }
    assert store.public_trigger(paired)["owner_repo"] == "acme/widgets"
    assert store.public_trigger(inner)["owner_repo"] == "inner/widgets"
    assert store.normalize_owner_repo("acme/widgets/") == "acme/widgets"
    assert store.normalize_owner_repo({"owner": "/acme/", "repo": "widgets/"}) == "acme/widgets"


def test_owner_without_a_repo_is_a_fill_in():
    for kind, extra in (
        ("github_pr_merged", {}),
        ("github_event", {"event_type": "issues.opened"}),
    ):
        pack = validate_pack(
            {
                "routines": [
                    {
                        "name": "Preset solver",
                        "instruction": "Investigate the issue.",
                        "trigger": {"kind": kind, "owner": "acme", **extra},
                    }
                ]
            }
        )
        assert pack["routines"][0]["trigger"]["owner_repo"] == "{{owner_repo}}", kind
        assert any(slot["key"] == "owner_repo" for slot in pack["fill_ins"]), kind


def test_import_does_not_persist_when_a_later_row_is_invalid():
    with pytest.raises(PackValidationError, match="owner/repo") as exc:
        import_pack(
            "writer",
            {
                "routines": [
                    {
                        "name": "Keep me out",
                        "instruction": "Ping.",
                        "trigger": {"kind": "interval", "seconds": 3600},
                    },
                    {
                        "name": "Bad repo",
                        "instruction": "Watch {{owner_repo}}",
                        "trigger": {
                            "kind": "github_event",
                            "event_type": "issues.opened",
                            "owner_repo": "{{owner_repo}}",
                        },
                    },
                ]
            },
            fill_ins={"owner_repo": "not a repo"},
        )
    assert exc.value.code == "pack_import_invalid"
    assert store.list_routines("writer") == []


def _arm_legacy_fill_in(agent_id: str, routine: dict) -> None:
    """Store an already-armed fill-in row. PATCH enable must refuse this."""
    armed = dict(routine)
    armed["active"] = True
    armed["enabled"] = True
    store._persist_agent(agent_id, [armed])


def test_enabled_placeholder_does_not_fire_on_token_repo():
    imported = import_pack("codey", _solver_pack())
    row = imported["routines"][0]
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.update_routine("codey", row["id"], {"active": True})
    _arm_legacy_fill_in("codey", row)
    assert store.deliver_github_event(_issue_opened("{{owner_repo}}"), event_header="issues") == []
    assert store.deliver_github_event(_issue_opened("acme/widgets"), event_header="issues") == []
    assert store.get_routine("codey", row["id"])["history"] == []

    merged = import_pack(
        "codey",
        {
            "routines": [
                {
                    "name": "Merge watcher",
                    "instruction": "Note the merge.",
                    "trigger": {"kind": "github_pr_merged", "owner_repo": "{{owner_repo}}"},
                }
            ]
        },
    )
    merge_row = merged["routines"][0]
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.update_routine("codey", merge_row["id"], {"active": True})
    _arm_legacy_fill_in("codey", merge_row)
    with pytest.raises(ValueError, match="owner/repo"):
        store.deliver_github_pr_merged({"owner_repo": "{{owner_repo}}", "merged": True, "actor": "octocat"})
    assert store.get_routine("codey", merge_row["id"])["history"] == []


def test_import_is_idempotent_on_fingerprint():
    first = import_pack("codey", _solver_pack(), fill_ins={"owner_repo": "acme/widgets"})
    second = import_pack("codey", _solver_pack(), fill_ins={"owner_repo": "acme/widgets"})
    assert first["created_count"] == 1
    assert second["created_count"] == 0
    assert second["skipped"]
    assert len(store.list_routines("codey")) == 1


def test_secret_fill_in_value_is_refused():
    with pytest.raises((PackValidationError, ValueError), match="secrets"):
        import_pack("codey", _solver_pack(), fill_ins={"owner_repo": "Bearer sk-abcdefghijklmnopqrst"})


def test_export_strips_concrete_repo_id_into_fill_in():
    store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "description": "Recap merges in acme/widgets.",
            "instruction": "Summarize acme/widgets merges.",
            "slug": "ship-notes",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
    )
    pack = build_pack("codey")
    row = pack["routines"][0]
    assert row["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert row["slug"] == "ship-notes"
    assert row["enabled"] is False
    assert "{{owner_repo}}" in row["instruction"]
    assert "{{owner_repo}}" in row["description"]
    assert "acme/widgets" not in row["instruction"]
    assert "acme/widgets" not in row["trigger"]["owner_repo"]
    assert {slot["key"] for slot in pack["fill_ins"]} == {"owner_repo"}


def test_export_strips_mailbox_sender():
    store.create_routine(
        "codey",
        {
            "name": "Inbox",
            "instruction": "Triage mail from ops@acme.example.",
            "trigger": {
                "kind": "mailbox_message",
                "sender": "ops@acme.example",
                "pattern": "from ops@acme.example",
            },
        },
    )
    pack = build_pack("codey")
    row = pack["routines"][0]
    assert row["trigger"]["sender"] == "{{sender}}"
    assert row["trigger"]["pattern"] == "from {{sender}}"
    assert "{{sender}}" in row["instruction"]
    assert "ops@acme.example" not in row["instruction"]
    assert "ops@acme.example" not in row["trigger"]["pattern"]
    assert {slot["key"] for slot in pack["fill_ins"]} == {"sender"}


def test_export_strips_repo_case_insensitively_without_eating_neighbors():
    store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "instruction": "See ACME/WIDGETS and leave acme/widgets-extra alone.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
    )
    pack = build_pack("codey")
    instruction = pack["routines"][0]["instruction"]
    assert "{{owner_repo}}" in instruction
    assert "ACME/WIDGETS" not in instruction
    assert "acme/widgets-extra" in instruction


def test_export_strips_ids_at_ellipsis_without_eating_dotted_neighbors():
    store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "instruction": "See acme/widgets. Then acme/widgets... later. Leave acme/widgets.docs.",
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
    )
    store.create_routine(
        "codey",
        {
            "name": "Inbox",
            "instruction": "Ping ops@acme.example... and keep ops@acme.example.com.",
            "trigger": {"kind": "mailbox_message", "sender": "ops@acme.example"},
        },
    )
    pack = build_pack("codey")
    by_name = {row["name"]: row for row in pack["routines"]}
    repo = by_name["Ship notes"]["instruction"]
    mail = by_name["Inbox"]["instruction"]
    assert repo == "See {{owner_repo}}. Then {{owner_repo}}... later. Leave acme/widgets.docs."
    assert mail == "Ping {{sender}}... and keep ops@acme.example.com."


def test_export_strips_ids_after_an_ellipsis_without_eating_dotted_prefixes():
    store.create_routine(
        "codey",
        {
            "name": "Ship notes",
            "instruction": (
                "See ...acme/widgets later. Also acme/widgets...acme/widgets. "
                "Leave notes.acme/widgets."
            ),
            "trigger": {"kind": "github_pr_merged", "owner_repo": "acme/widgets"},
        },
    )
    store.create_routine(
        "codey",
        {
            "name": "Inbox",
            "instruction": (
                "Ping ...ops@acme.example later. Also ops@acme.example...ops@acme.example. "
                "Leave team.ops@acme.example."
            ),
            "trigger": {"kind": "mailbox_message", "sender": "ops@acme.example"},
        },
    )
    pack = build_pack("codey")
    by_name = {row["name"]: row for row in pack["routines"]}
    repo = by_name["Ship notes"]["instruction"]
    mail = by_name["Inbox"]["instruction"]
    assert repo == (
        "See ...{{owner_repo}} later. Also {{owner_repo}}...{{owner_repo}}. "
        "Leave notes.acme/widgets."
    )
    assert mail == (
        "Ping ...{{sender}} later. Also {{sender}}...{{sender}}. "
        "Leave team.ops@acme.example."
    )


def test_mailbox_fill_in_sender_does_not_match_a_token_event():
    imported = import_pack(
        "codey",
        {
            "routines": [
                {
                    "name": "Inbox",
                    "instruction": "Triage {{sender}}.",
                    "trigger": {
                        "kind": "mailbox_message",
                        "sender": "{{sender}}",
                        "pattern": "P1",
                    },
                }
            ]
        },
    )
    row = imported["routines"][0]
    assert row["trigger"]["sender"] == "{{sender}}"
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.update_routine("codey", row["id"], {"enabled": True})
    _arm_legacy_fill_in("codey", row)
    assert store.deliver_mailbox_message({"sender": "{{sender}}", "content": "P1"}) == []
    assert store.deliver_mailbox_message({"sender": "ops@acme.example", "content": "P1"}) == []


def test_import_persists_slug_and_description():
    import json

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    imported = import_pack("writer", raw, fill_ins={"owner_repo": "acme/widgets"})
    row = imported["routines"][0]
    assert row["slug"] == "github_issue_solver"
    assert row["active"] is False
    assert row["enabled"] is False
    assert "acme/widgets" in row["description"]
    stored = store.get_routine("writer", row["id"])
    assert stored is not None
    assert stored["slug"] == "github_issue_solver"
    assert stored["description"]
    assert stored["enabled"] is False


def test_enable_blocked_while_fill_ins_remain():
    imported = import_pack("codey", _solver_pack())
    row = imported["routines"][0]
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.update_routine("codey", row["id"], {"active": True})
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.update_routine("codey", row["id"], {"enabled": True})
    stored = store.get_routine("codey", row["id"])
    assert stored is not None
    assert stored["active"] is False
    assert stored["enabled"] is False


def test_create_active_with_fill_in_is_refused():
    with pytest.raises(ValueError, match="fill-ins remain"):
        store.create_routine(
            "codey",
            {
                "name": "Armed template",
                "instruction": "Work {{owner_repo}}",
                "active": True,
                "trigger": {
                    "kind": "github_event",
                    "event_type": "issues.assigned",
                    "owner_repo": "{{owner_repo}}",
                },
            },
        )
    assert store.list_routines("codey") == []


def test_issue_assigned_export_import_enable_round_trip():
    store.create_routine(
        "codey",
        {
            "name": "Assigned solver",
            "slug": "issue-assigned-solver",
            "description": "When an issue is assigned in acme/widgets.",
            "instruction": "Fix the assigned issue in acme/widgets.",
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.assigned",
                "owner_repo": "acme/widgets",
            },
        },
    )
    pack = build_pack("codey")
    row = pack["routines"][0]
    assert row["slug"] == "issue-assigned-solver"
    assert row["trigger"]["event_type"] == "issues.assigned"
    assert row["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert row["enabled"] is False
    assert "acme/widgets" not in row["instruction"]
    assert "acme/widgets" not in row["description"]
    assert any(slot["key"] == "owner_repo" for slot in pack["fill_ins"])

    imported = import_pack("writer", pack, fill_ins={"owner_repo": "other/repo"})
    stored = imported["routines"][0]
    assert stored["slug"] == "issue-assigned-solver"
    assert stored["active"] is False
    assert stored["trigger"]["owner_repo"] == "other/repo"
    assert "other/repo" in stored["description"]
    assert stored["trigger"]["event_type"] == "issues.assigned"

    enabled = store.update_routine("writer", stored["id"], {"enabled": True})
    assert enabled["active"] is True
    assert enabled["enabled"] is True
    payload = _issue_opened("other/repo", 9)
    payload["action"] = "assigned"
    fired = store.deliver_github_event(payload, event_header="issues")
    assert len(fired) == 1
    assert fired[0]["routine"]["id"] == stored["id"]


def test_issue_assigned_round_trip_strips_ids_and_gates_enable():
    """Concrete repo/channel ids become named fill-ins; enable waits on fill-ins."""
    import json

    created = store.create_routine(
        "codey",
        {
            "name": "GitHub Issue Solver",
            "slug": "github-issue-solver",
            "description": "When an issue is opened, investigate and open a fix PR.",
            "instruction": "Investigate the issue in acme/widgets and open a pull request.",
            "active": True,
            "trigger": {
                "kind": "github_event",
                "event_type": "issues.opened",
                "owner_repo": "acme/widgets",
                "channel": "C0123ABCDEF",
                "filters": {"exclude_authors": ["open-swarm[bot]"]},
            },
        },
    )
    assert created["slug"] == "github-issue-solver"
    assert created["description"].startswith("When an issue")
    assert created["job"] == created["instruction"]
    assert created["enabled"] is True
    assert created["pending_fill"] is False

    pack = build_pack("codey", routine_ids=[created["id"]])
    row = pack["routines"][0]
    blob = json.dumps(pack)
    assert row["slug"] == "github-issue-solver"
    assert row["description"].startswith("When an issue")
    assert row["trigger"]["kind"] == "github_event"
    assert row["trigger"]["event_type"] == "issues.opened"
    assert row["trigger"]["owner_repo"] == "{{owner_repo}}"
    assert row["trigger"]["channel"] == "{{channel}}"
    assert "acme/widgets" not in blob
    assert "C0123ABCDEF" not in blob
    keys = {slot["key"] for slot in pack["fill_ins"]}
    assert {"owner_repo", "channel"} <= keys
    assert row["trigger"].get("history") is None

    imported = import_pack("writer", pack)
    got = imported["routines"][0]
    assert imported["pending_enable"] is True
    assert got["active"] is False
    assert got["enabled"] is False
    assert got["pending_fill"] is True
    assert "owner_repo" in got["fill_in_keys"]
    assert got["description"].startswith("When an issue")
    assert got["slug"] == "github-issue-solver"

    with pytest.raises(ValueError, match="fill-ins"):
        store.enable_routine("writer", got["id"])

    partial = store.apply_routine_fill_ins(
        "writer",
        got["id"],
        {"owner_repo": "acme/widgets"},
    )
    assert partial["active"] is False
    assert partial["pending_fill"] is True
    with pytest.raises(ValueError, match="channel"):
        store.enable_routine("writer", got["id"])

    filled = store.apply_routine_fill_ins(
        "writer",
        got["id"],
        {"channel": "C0123ABCDEF"},
    )
    assert filled["pending_fill"] is False
    assert filled["trigger"]["owner_repo"] == "acme/widgets"
    assert filled["trigger"]["channel"] == "C0123ABCDEF"
    assert "{{" not in filled["instruction"]

    enabled = store.enable_routine("writer", got["id"])
    assert enabled["enabled"] is True
    fired = store.deliver_github_event(_issue_opened(number=9), event_header="issues")
    writer_hits = [row for row in fired if row.get("agent_id") == "writer"]
    assert len(writer_hits) == 1
    assert writer_hits[0]["routine"]["id"] == got["id"]


def test_credential_shaped_strings_rejected_in_packed_config():
    with pytest.raises(PackValidationError, match="secrets") as exc:
        validate_pack(
            {
                "routines": [
                    {
                        "name": "Issue solver",
                        "description": "When an issue is assigned",
                        "instruction": "Fix the issue.",
                        "trigger": {
                            "kind": "github_event",
                            "event_type": "issues.opened",
                            "owner_repo": "{{owner_repo}}",
                            "channel": "ghp_abcdefghijklmnopqrstuvwxyz",
                        },
                    }
                ]
            }
        )
    assert exc.value.code == "pack_secret"

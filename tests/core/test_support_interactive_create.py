"""#1373 — Support interactive create: routines + team/group seating."""

from swarm.core.decision_question import parse_decision_question
from swarm.core.support_interactive_create import (
    ADD_ROUTINE_LABEL,
    CREATE_GROUP_LABEL,
    ROUTINE_GITHUB_REPO_QUESTION_ID,
    ROUTINE_PURPOSE_QUESTION_ID,
    SEAT_ON_TEAM_LABEL,
    SEATING_TARGET_QUESTION_ID,
    SUPPORT_INTERACTIVE_FIXTURE,
    SUPPORT_ROUTINE_FENCE,
    SUPPORT_SEATING_FENCE,
    create_nl_routine,
    create_nl_seating,
    interactive_create_or_socratic,
    interpret_seating_nl,
    persist_seating_draft,
    seating_design_is_specified,
    wants_routine_create,
    wants_seating,
)
from swarm.core.support_nl_blueprint import TEAM_PURPOSE_QUESTION_ID
from swarm.core.team_rosters import reset_team_rosters


def test_underspecified_routine_is_socratic():
    reply = interactive_create_or_socratic("Create a routine")
    assert reply is not None
    assert "```question" in reply
    parsed = parse_decision_question(reply)
    assert parsed is not None
    assert parsed["id"] == ROUTINE_PURPOSE_QUESTION_ID
    assert SUPPORT_ROUTINE_FENCE not in reply


def test_specified_routine_drafts_without_persist():
    reply = interactive_create_or_socratic(
        "Create a daily standup routine for codey that posts notes"
    )
    assert reply is not None
    assert f"```{SUPPORT_ROUTINE_FENCE}" in reply
    assert ADD_ROUTINE_LABEL in reply
    assert '"persisted": false' in reply
    assert "codey" in reply
    assert "Daily at 09:00" in reply
    assert SUPPORT_INTERACTIVE_FIXTURE in reply
    assert wants_routine_create("Create a daily standup routine for codey")
    assert not wants_routine_create("Create a team")
    assert not wants_routine_create("Add a remote")


def test_routine_purpose_answer_drafts_standup():
    history = [
        {"role": "user", "content": "Create a routine"},
        {"role": "assistant", "content": interactive_create_or_socratic("Create a routine")},
    ]
    reply = interactive_create_or_socratic("Daily standup", history)
    assert reply is not None
    assert "Daily standup" in reply
    assert f"```{SUPPORT_ROUTINE_FENCE}" in reply


def test_persist_routine_uses_existing_store(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_ROUTINES_PATH", str(tmp_path / "agent_routines.json"))
    created = create_nl_routine(
        "Create an hourly health check routine for ada",
        persist=True,
    )
    assert created.persisted is True
    assert created.item["name"] == "Hourly check"
    assert created.item["trigger"]["kind"] == "interval"
    assert created.item["trigger"]["seconds"] == 3600
    assert created.agent_id == "ada"
    from swarm.core.routines import list_routines

    rows = list_routines("ada")
    assert len(rows) == 1
    assert rows[0]["id"] == created.item["id"]


def test_underspecified_seating_is_socratic():
    reply = interactive_create_or_socratic("Seat someone on a team")
    assert reply is not None
    assert "```question" in reply
    parsed = parse_decision_question(reply)
    assert parsed is not None
    assert parsed["id"] == SEATING_TARGET_QUESTION_ID
    assert SUPPORT_SEATING_FENCE not in reply
    assert wants_seating("Seat someone on a team")
    assert not wants_seating("Create a team")
    assert not wants_seating("Add a remote")
    assert not seating_design_is_specified("Seat someone on a team")


def test_specified_seating_drafts_without_persist():
    reply = interactive_create_or_socratic("Seat Ada on the office team")
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert SEAT_ON_TEAM_LABEL in reply
    assert '"persisted": false' in reply
    assert "Ada" in reply
    assert "office" in reply
    assert SUPPORT_INTERACTIVE_FIXTURE in reply
    assert seating_design_is_specified("Seat Ada on the office team")


def test_create_group_drafts_seating_card():
    reply = interactive_create_or_socratic("Create a group with Ada and Pat")
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert CREATE_GROUP_LABEL in reply
    assert "Ada" in reply
    assert "Pat" in reply
    assert '"mode": "create_group"' in reply


def test_create_team_still_uses_existing_socratic():
    reply = interactive_create_or_socratic("Create a team")
    assert reply is not None
    parsed = parse_decision_question(reply)
    assert parsed is not None
    assert parsed["id"] == TEAM_PURPOSE_QUESTION_ID
    assert SUPPORT_ROUTINE_FENCE not in reply
    assert SUPPORT_SEATING_FENCE not in reply


def test_persist_seating_merges_existing_roster():
    reset_team_rosters(
        {
            "office": {
                "id": "office",
                "name": "Office",
                "members": [
                    {
                        "id": "pat",
                        "name": "Pat",
                        "kind": "api",
                        "role": "default",
                        "source": "blueprint:pat",
                    }
                ],
                "wires": {"handoff": True, "as_tool": True},
            }
        }
    )
    created = create_nl_seating("Seat Ada on the office team", persist=True)
    assert created.persisted is True
    ids = [row["id"] for row in created.item["members"]]
    assert "pat" in ids
    assert "ada" in ids
    reset_team_rosters()


def test_persist_seating_creates_group(tmp_path, monkeypatch):
    from swarm.core import team_rosters as store

    reset_team_rosters({})
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: tmp_path)
    parsed = {
        "id": "desk",
        "title": "Desk",
        "mode": "create_group",
        "members": [
            {"id": "ada", "name": "Ada", "kind": "api", "role": "default"},
            {"id": "pat", "name": "Pat", "kind": "api", "role": "default"},
        ],
    }
    stored = persist_seating_draft(parsed, disk=True)
    assert stored["id"] == "desk"
    assert {row["id"] for row in stored["members"]} == {"ada", "pat"}
    reset_team_rosters()


def test_fresh_github_and_hourly_phrases_are_not_routines():
    github = interactive_create_or_socratic("On GitHub, how do I add a remote?") or ""
    assert SUPPORT_ROUTINE_FENCE not in github
    assert ROUTINE_GITHUB_REPO_QUESTION_ID not in github
    assert ROUTINE_PURPOSE_QUESTION_ID not in github
    hourly = interactive_create_or_socratic("Hourly check the server logs") or ""
    assert SUPPORT_ROUTINE_FENCE not in hourly
    assert ROUTINE_PURPOSE_QUESTION_ID not in hourly


def test_put_in_and_group_chat_are_not_seating():
    put = interactive_create_or_socratic("put the quickstart in the reply") or ""
    assert SUPPORT_SEATING_FENCE not in put
    assert SEATING_TARGET_QUESTION_ID not in put
    chat = interactive_create_or_socratic("Create a group chat") or ""
    assert SUPPORT_SEATING_FENCE not in chat
    assert SEATING_TARGET_QUESTION_ID not in chat
    assert not wants_seating("Create a group chat")
    assert not wants_seating("put the quickstart in the reply")


def test_daily_schedule_beats_incidental_github_mention():
    created = create_nl_routine(
        "Create a daily routine that posts a github digest",
        persist=False,
    )
    assert created.trigger["kind"] == "cron"
    assert created.trigger["expression"] == "0 9 * * *"
    assert created.agent_id == "support"


def test_gerund_is_not_an_agent_id():
    created = create_nl_routine(
        "Create a daily standup routine for posting notes",
        persist=False,
    )
    assert created.agent_id == "support"
    assert created.name == "Daily standup"


def test_github_merge_without_repo_asks_instead_of_drafting():
    reply = interactive_create_or_socratic("Create a GitHub merge routine")
    assert reply is not None
    assert SUPPORT_ROUTINE_FENCE not in reply
    parsed = parse_decision_question(reply)
    assert parsed is not None
    assert parsed["id"] == ROUTINE_GITHUB_REPO_QUESTION_ID


def test_github_repo_answer_drafts_owner_repo():
    history = [
        {"role": "user", "content": "Create a GitHub merge routine"},
        {
            "role": "assistant",
            "content": interactive_create_or_socratic("Create a GitHub merge routine"),
        },
    ]
    reply = interactive_create_or_socratic("acme/widgets", history)
    assert reply is not None
    assert f"```{SUPPORT_ROUTINE_FENCE}" in reply
    assert "acme/widgets" in reply
    assert '"persisted": false' in reply


def test_purpose_choice_still_drafts_only_after_the_question():
    fresh = interactive_create_or_socratic("On GitHub merge")
    assert not fresh or SUPPORT_ROUTINE_FENCE not in fresh
    history = [
        {"role": "user", "content": "Create a routine"},
        {"role": "assistant", "content": interactive_create_or_socratic("Create a routine")},
    ]
    reply = interactive_create_or_socratic("On GitHub merge", history)
    assert reply is not None
    assert SUPPORT_ROUTINE_FENCE not in reply
    assert ROUTINE_GITHUB_REPO_QUESTION_ID in reply
    drafted = interactive_create_or_socratic("On GitHub merge of acme/widgets", history)
    assert drafted is not None
    assert "acme/widgets" in drafted
    assert f"```{SUPPORT_ROUTINE_FENCE}" in drafted


def test_topic_change_after_routine_question_is_not_a_card():
    history = [
        {"role": "user", "content": "Create a routine"},
        {"role": "assistant", "content": interactive_create_or_socratic("Create a routine")},
    ]
    reply = interactive_create_or_socratic("Add a remote", history)
    assert not reply or SUPPORT_ROUTINE_FENCE not in reply


def test_put_on_team_still_drafts_seating():
    reply = interactive_create_or_socratic("put Ada on the office team")
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert "Ada" in reply
    assert "office" in reply


def _github_repo_history() -> list[dict[str, str]]:
    return [
        {"role": "user", "content": "Create a GitHub merge routine"},
        {
            "role": "assistant",
            "content": interactive_create_or_socratic("Create a GitHub merge routine")
            or "",
        },
    ]


def test_github_url_is_the_repository_not_the_host():
    created = create_nl_routine(
        "Create a GitHub merge routine for https://github.com/acme/widgets.git",
        persist=False,
    )
    assert created.trigger["kind"] == "github_pr_merged"
    assert created.trigger["owner_repo"] == "acme/widgets"
    assert created.agent_id == "support"


def test_explicit_merge_beats_daily_wording_in_the_instruction():
    created = create_nl_routine(
        "Create a GitHub merge routine for acme/widgets that posts a daily digest",
        persist=False,
    )
    assert created.trigger["kind"] == "github_pr_merged"
    assert created.trigger["owner_repo"] == "acme/widgets"
    assert created.agent_id == "support"
    assert "daily digest" in created.instruction


def test_put_in_team_seats_and_put_in_reply_does_not():
    reply = interactive_create_or_socratic("put Ada in the office team")
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert "Ada" in reply
    assert "office" in reply
    assert wants_seating("put Ada in the office team")
    assert wants_seating("seat Ada in the office team")
    assert not wants_seating("put the quickstart in the reply")


def test_repo_answer_keeps_instruction_and_skips_a_path():
    history = _github_repo_history()
    reply = interactive_create_or_socratic(
        "acme/widgets that posts the changelog",
        history,
    )
    assert reply is not None
    assert '"owner_repo": "acme/widgets"' in reply
    assert '"agentId": "support"' in reply
    assert '"agentId": "acm"' not in reply
    assert "changelog" in reply
    path = interactive_create_or_socratic("use acme/widgets, not src/swarm", history)
    assert path is not None
    assert '"owner_repo": "acme/widgets"' in path
    assert '"owner_repo": "src/swarm"' not in path


def test_seating_after_repo_question_is_not_a_routine():
    reply = interactive_create_or_socratic(
        "Create a group with Ada and Pat for acme/widgets",
        _github_repo_history(),
    )
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert SUPPORT_ROUTINE_FENCE not in reply


def test_bare_names_after_seating_question_draft_and_put_in_does_not():
    history = [
        {"role": "user", "content": "Seat someone on a team"},
        {
            "role": "assistant",
            "content": interactive_create_or_socratic("Seat someone on a team") or "",
        },
    ]
    reply = interactive_create_or_socratic("Ada on office", history)
    assert reply is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in reply
    assert "Ada" in reply
    assert "office" in reply
    stolen = interactive_create_or_socratic("put the quickstart in the reply", history)
    assert not stolen or SUPPORT_SEATING_FENCE not in stolen
    oxford = interactive_create_or_socratic("Ada, Pat, and Jo on office", history)
    assert oxford is not None
    assert f"```{SUPPORT_SEATING_FENCE}" in oxford
    assert "Ada" in oxford and "Pat" in oxford and "Jo" in oxford


def test_named_repo_beats_a_docs_url_and_a_gist_is_not_a_repo():
    named = create_nl_routine(
        "Create a GitHub merge routine for acme/widgets, not https://github.com/docs/guide",
        persist=False,
    )
    assert named.trigger["owner_repo"] == "acme/widgets"
    assert named.agent_id == "support"
    www = create_nl_routine(
        "Create a GitHub merge routine for https://www.github.com/acme/widgets/",
        persist=False,
    )
    assert www.trigger["owner_repo"] == "acme/widgets"
    assert www.agent_id == "support"
    ssh = create_nl_routine(
        "Create a GitHub merge routine for git@github.com:acme/widgets.git",
        persist=False,
    )
    assert ssh.trigger["owner_repo"] == "acme/widgets"
    assert ssh.agent_id == "support"
    ssh_url = create_nl_routine(
        "Create a GitHub merge routine for ssh://git@github.com/acme/widgets.git",
        persist=False,
    )
    assert ssh_url.trigger["owner_repo"] == "acme/widgets"
    assert ssh_url.agent_id == "support"
    api_host = create_nl_routine(
        "Create a GitHub merge routine for https://api.github.com/repos/acme/widgets",
        persist=False,
    )
    assert api_host.trigger["owner_repo"] == "acme/widgets"
    assert api_host.agent_id == "support"
    ssh_port = create_nl_routine(
        "Create a GitHub merge routine for ssh://git@github.com:22/acme/widgets.git",
        persist=False,
    )
    assert ssh_port.trigger["owner_repo"] == "acme/widgets"
    assert ssh_port.agent_id == "support"
    gist = create_nl_routine(
        "Create a GitHub merge routine for https://gist.github.com/acme/abc123def",
        persist=False,
    )
    assert not gist.trigger["owner_repo"]


def test_a_word_after_team_is_not_seating():
    for phrase in (
        "put the notes in the team folder",
        "put Ada in the group chat",
        "sit in the team standup",
        "put the file on the team folder",
        "add the notes to the team folder",
        "move the file to the group chat",
        "sit on the team folder",
        "add the notes to the team's folder",
        "put the file on the team\u2019s folder",
    ):
        assert not wants_seating(phrase), phrase
        reply = interactive_create_or_socratic(phrase) or ""
        assert SUPPORT_SEATING_FENCE not in reply
        assert SEATING_TARGET_QUESTION_ID not in reply
    assert wants_seating("add Ada to the office team")
    assert wants_seating("seat Ada on the office team")
    assert wants_seating("move Ada to the office team")
    for phrase, member, roster in (
        ("add Ada to the office team please", "Ada", "office"),
        ("seat Ada on the office team today", "Ada", "office"),
        ("seat Ada on the office team now", "Ada", "office"),
        ("move Pat to the design team tomorrow", "Pat", "design"),
        ("put Ada in the engineering team please", "Ada", "engineering"),
        ("add Ada to the office team and the design team", "Ada", "office"),
        ("seat Ada on the office team with Pat", "Ada", "office"),
    ):
        assert wants_seating(phrase), phrase
        reply = interactive_create_or_socratic(phrase) or ""
        assert f"```{SUPPORT_SEATING_FENCE}" in reply
        assert member in reply
        assert roster in reply
    with_pat = interactive_create_or_socratic("seat Ada on the office team with Pat") or ""
    assert "Pat" in with_pat
    unnamed = interactive_create_or_socratic("seat Ada on the team with Pat") or ""
    assert wants_seating("seat Ada on the team with Pat")
    assert SUPPORT_SEATING_FENCE not in unnamed
    assert SEATING_TARGET_QUESTION_ID in unnamed


def test_polite_tail_is_not_the_roster_or_member_name():
    for phrase in (
        "seat Ada on the team today",
        "seat Ada on the team please",
        "add Ada to the team please",
        "move Pat to the team tomorrow",
        "put Ada in the team now",
        "seat Ada on the team thanks",
        "add Ada to the team and the design team",
    ):
        assert wants_seating(phrase), phrase
        assert not seating_design_is_specified(phrase), phrase
        reply = interactive_create_or_socratic(phrase) or ""
        assert SUPPORT_SEATING_FENCE not in reply, phrase
        assert SEATING_TARGET_QUESTION_ID in reply, phrase

    named = interpret_seating_nl("seat Ada on the office team with Pat please")
    assert named["id"] == "office"
    assert [member["name"] for member in named["members"]] == ["Ada", "Pat"]

    both = interpret_seating_nl("seat Ada on the office team with Pat and Sam please")
    assert [member["name"] for member in both["members"]] == ["Ada", "Pat", "Sam"]

    clause = interpret_seating_nl("seat Ada on the office team with write access")
    assert [member["name"] for member in clause["members"]] == ["Ada"]
    assert clause["id"] == "office"


def test_capitalized_ing_name_is_an_agent_and_a_gerund_is_not():
    named = create_nl_routine("Create a daily routine for Sterling", persist=False)
    assert named.agent_id == "sterling"
    gerund = create_nl_routine("Create a daily routine for creating notes", persist=False)
    assert gerund.agent_id == "support"

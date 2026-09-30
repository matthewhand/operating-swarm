"""#1410 — instruction-gap tool suggestions. Never auto-enable."""

from __future__ import annotations

from swarm.core.routine_tool_suggestions import (
    apply_suggested_tool,
    instruction_fingerprint,
    suggest_routine_tools,
    visible_tool_suggestions,
)
from swarm.core.routine_tools import TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST, compose_routine_picker_catalog


def _ids(rows):
    return [row["id"] for row in rows]


def test_picker_catalog_includes_memories_label():
    items = compose_routine_picker_catalog({})
    by_id = {row["id"]: row for row in items}
    assert by_id["memories"]["label"] == "Memories"
    assert by_id["memories"]["kind"] == "builtin"
    assert by_id["memories"]["wired"] is False
    assert by_id["memories"]["can_live"] is False


def test_mention_pr_suggests_open_pull_request():
    rows = suggest_routine_tools("Investigate the issue and open a pull request.", [])
    assert _ids(rows) == [TOOL_OPEN_PULL_REQUEST]
    assert rows[0]["reason"] == "Instructions mention opening a PR — add Open Pull Request?"
    assert rows[0]["auto_enable"] is False
    assert rows[0]["destructive"] is True


def test_mention_pr_abbreviation():
    assert _ids(suggest_routine_tools("Please open a PR with Fixes #12.", [])) == [
        TOOL_OPEN_PULL_REQUEST
    ]


def test_mention_memory_suggests_memories():
    rows = suggest_routine_tools("Remember prior context from MEMORIES.", [])
    assert _ids(rows) == [TOOL_MEMORIES]
    assert rows[0]["reason"] == "Instructions mention memory — add Memories?"
    assert rows[0]["auto_enable"] is False


def test_slack_mention_does_not_invent_a_tool_id():
    rows = suggest_routine_tools("Post the recap to Slack.", [])
    assert rows == []
    assert "slack" not in _ids(rows)


def test_bare_remember_does_not_suggest_memories():
    rows = suggest_routine_tools("Remember to file the weekly report.", [])
    assert TOOL_MEMORIES not in _ids(rows)


def test_tools_already_present_no_nag():
    text = "Open a PR and remember prior context from MEMORIES."
    rows = suggest_routine_tools(
        text,
        [TOOL_OPEN_PULL_REQUEST, TOOL_MEMORIES],
    )
    assert rows == []


def test_mixed_case_present_id_is_not_suggested_again():
    rows = suggest_routine_tools("Please open a PR.", ["Open_Pull_Request"])
    assert rows == []


def test_multiline_negation_does_not_suggest_open_pr():
    rows = suggest_routine_tools("Investigate the issue.\nDo not\nopen a pull request.", [])
    assert TOOL_OPEN_PULL_REQUEST not in _ids(rows)


def test_negation_does_not_suggest_open_pr():
    rows = suggest_routine_tools("Investigate the issue. Do not open a pull request.", [])
    assert TOOL_OPEN_PULL_REQUEST not in _ids(rows)


def test_pull_request_trigger_can_suggest_open_pr():
    rows = suggest_routine_tools(
        "Review the incoming change.",
        [],
        {"kind": "github_event", "event_type": "pull_request.opened"},
    )
    assert _ids(rows) == [TOOL_OPEN_PULL_REQUEST]


def test_merge_trigger_kind_does_not_suggest_open_pr():
    rows = suggest_routine_tools(
        "Summarize what landed.",
        [],
        {"kind": "github_pr_merged", "event": "merged"},
    )
    assert rows == []


def test_token_shaped_instruction_never_copied_into_reason():
    token = "ghp_notarealtokenvalue12"
    rows = suggest_routine_tools(f"Open a PR. Auth {token}", [])
    blob = str(rows)
    assert token not in blob
    assert "ghp_" not in blob
    assert rows[0]["reason"] == "Instructions mention opening a PR — add Open Pull Request?"


def test_never_auto_enable_destructive_without_confirm():
    tools: list[str] = []
    rows = suggest_routine_tools("Open a PR and remember prior context from MEMORIES.", tools)
    assert {row["id"] for row in rows} == {TOOL_OPEN_PULL_REQUEST, TOOL_MEMORIES}
    assert all(row["auto_enable"] is False for row in rows)
    unchanged = apply_suggested_tool(tools, TOOL_OPEN_PULL_REQUEST, confirmed=False)
    assert unchanged == []
    confirmed = apply_suggested_tool(tools, TOOL_OPEN_PULL_REQUEST, confirmed=True)
    assert confirmed == [TOOL_OPEN_PULL_REQUEST]


def test_dismiss_persists_for_fingerprint_until_material_change():
    instruction = "Please open a PR."
    dismissed = {TOOL_OPEN_PULL_REQUEST: instruction_fingerprint(instruction)}
    hidden = visible_tool_suggestions(instruction, [], None, dismissed)
    assert hidden == []
    still = visible_tool_suggestions("Please open a PR!", [], None, dismissed)
    assert still == []
    again = visible_tool_suggestions("Please open a PR and also remember MEMORIES.", [], None, dismissed)
    assert TOOL_OPEN_PULL_REQUEST in _ids(again)
    assert TOOL_MEMORIES in _ids(again)

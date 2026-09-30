"""View-model tests: grouping, status signals, badges, deep links."""

from __future__ import annotations

import pytest

from os_marchy_systray.model import (
    build_view,
    chat_url,
    kind_badge,
    status_from_row,
    status_glyph,
)
from tests.fixtures import (
    AGENTS_PAYLOAD,
    CLI_PAYLOAD,
    REMOTES_PAYLOAD,
    ROSTERS_PAYLOAD,
)


def _view(**overrides):
    kwargs = {
        "base_url": "http://os.test",
        "agents_payload": AGENTS_PAYLOAD,
        "rosters_payload": ROSTERS_PAYLOAD,
        "cli_payload": CLI_PAYLOAD,
        "remotes_payload": REMOTES_PAYLOAD,
        "connection": "ok",
    }
    kwargs.update(overrides)
    return build_view(**kwargs)


def test_static_rig_groups_roster_members():
    view = _view()
    newsroom = view.rig_named("newsroom")
    assert newsroom is not None
    assert newsroom.kind == "team"
    assert newsroom.is_static is True
    assert {agent.id for agent in newsroom.agents} == {"cos", "research"}
    assert all(agent.rig_id == "newsroom" for agent in newsroom.agents)


def test_unassigned_bucket_holds_orphans_and_cli_seats():
    view = _view()
    unassigned = view.unassigned
    assert unassigned is not None
    ids = {agent.id for agent in unassigned.agents}
    assert {"lonely", "cli_agent", "api_agent", "agy_agent"} <= ids
    # The rig list puts Unassigned last.
    assert view.rigs[-1].kind == "unassigned"


def test_remote_is_a_dynamic_section_rig_with_member_agents():
    view = _view()
    omb = view.rig_named("remote:omb")
    assert omb is not None
    assert omb.kind == "section"
    assert {agent.id for agent in omb.agents} == {"bot-a", "bot-b"}
    assert all(agent.kind == "remote_agent" for agent in omb.agents)
    assert omb.agents[0].status == "working"
    assert omb.agents[1].status == "idle"


def test_remote_without_members_appears_as_itself():
    view = _view()
    herdr = view.rig_named("remote:herdr-x")
    assert herdr is not None
    assert [agent.kind for agent in herdr.agents] == ["remote"]
    assert herdr.agents[0].id == "herdr-x"


def test_explicit_section_rig_claims_members():
    view = _view(
        sections=[{"id": "sec-desk", "name": "Desk", "agents": ["lonely"]}],
    )
    sec = view.rig_named("sec-desk")
    assert sec is not None
    assert sec.kind == "section"
    assert [agent.id for agent in sec.agents] == ["lonely"]
    assert "lonely" not in {agent.id for agent in view.unassigned.agents}


def test_counts_and_status_summary():
    view = _view()
    assert view.agent_count == 3 + 3 + 2 + 1  # agents + cli + omb + herdr
    counts = view.status_counts()
    assert counts.get("working") == 1  # bot-a
    assert counts.get("idle", 0) >= 1


@pytest.mark.parametrize(
    "row,expected",
    [
        ({"status": "running"}, "working"),
        ({"status": "working"}, "working"),
        ({"working": True}, "working"),
        ({"status": "finished"}, "idle"),
        ({"status": "error"}, "error"),
        ({"error": "boom"}, "error"),
        ({"status": "offline"}, "offline"),
        ({"online": False}, "offline"),
        ({"status": "waiting"}, "waiting"),
        ({}, "idle"),
    ],
)
def test_status_signal_mapping(row, expected):
    assert status_from_row(row) == expected


def test_kind_badges():
    assert kind_badge("cli") == "CLI"
    assert kind_badge("api") == "API"
    assert kind_badge("blueprint") == "Blueprint"
    assert kind_badge("remote_agent") == "Remote"
    assert kind_badge("whatever") == "Whatever"
    assert status_glyph("working") != status_glyph("idle")


def test_chat_url_per_kind():
    assert chat_url("blueprint", "writer") == "/chat?blueprint=writer"
    assert chat_url("api", "cos") == "/chat?blueprint=cos"
    assert chat_url("blueprint", "research", team_id="newsroom") == (
        "/chat?team=newsroom&session=research"
    )
    assert chat_url("team", "newsroom") == "/chat?team=newsroom"
    assert chat_url("remote", "herdr-x") == "/chat?remote=herdr-x"
    assert chat_url("remote_agent", "bot-a", remote_id="omb") == (
        "/chat?remote=omb&session=bot-a"
    )
    assert chat_url("cli", "cli_agent", cli="grok") == (
        "/chat?blueprint=cli_agent&cli=grok"
    )
    assert chat_url("cli", "agy_agent", cli="agy") == "/chat?blueprint=agy_agent"


def test_chat_url_is_absolute_when_base_url_given():
    assert chat_url("blueprint", "writer", base_url="http://os.test/") == (
        "http://os.test/chat?blueprint=writer"
    )


def test_chat_url_requires_agent_id():
    with pytest.raises(ValueError):
        chat_url("blueprint", "")


def test_agent_view_carries_kind_badge_and_status_glyph():
    view = _view()
    agent = next(a for a in view.all_agents() if a.id == "bot-a")
    assert agent.badge == "Remote"
    assert agent.status == "working"
    assert agent.status_glyph == status_glyph("working")
    assert agent.rig_id == "remote:omb"

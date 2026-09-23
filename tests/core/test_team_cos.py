"""REQ-107: optional team-scoped CoS + how-to-use-the-team brief."""

import pytest

from swarm.core.team_cos import (
    COS_INSTRUCTIONS_HELPER,
    COS_REMOTE_REASON,
    DEFAULT_COS_STARTER,
    apply_cos_fields,
    cos_brief_for_member,
    messages_with_cos_brief,
    normalize_cos_id,
    resolve_chief_of_staff,
    runtime_brief_for_target,
    team_run_context,
)
from swarm.core.team_rosters import normalize_roster, reset_team_rosters, upsert_roster


@pytest.fixture(autouse=True)
def _clean_rosters(tmp_path, monkeypatch):
    from swarm.core import team_rosters as store

    cfg = tmp_path / "cfg"
    cfg.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(store, "get_user_config_dir_for_swarm", lambda: cfg)
    monkeypatch.setattr(store, "ensure_swarm_directories_exist", lambda: None)
    reset_team_rosters()
    yield
    reset_team_rosters()


def _three_members():
    return [
        {"id": "jeeves", "kind": "api", "role": "default", "source": "blueprint:jeeves"},
        {"id": "grok_agent", "kind": "cli", "role": "default", "source": "cli:grok_agent"},
        {"id": "skeptic", "kind": "api", "role": "skeptic", "source": "blueprint:skeptic"},
    ]


def test_starter_has_no_secrets_or_live_host():
    blob = f"{DEFAULT_COS_STARTER}\n{COS_INSTRUCTIONS_HELPER}".lower()
    for leak in ("api_key", "secret", "token", "password", "neon", ":8001", "bearer"):
        assert leak not in blob


def test_remote_cannot_be_cos():
    members = [
        {"id": "hermes", "kind": "remote", "role": "default", "source": "placeholder:remote:hermes"},
        {"id": "jeeves", "kind": "api", "role": "default", "source": "blueprint:jeeves"},
    ]
    with pytest.raises(ValueError, match="API or CLI"):
        normalize_cos_id("hermes", members)
    assert COS_REMOTE_REASON


def test_persist_cos_and_reload():
    stored = upsert_roster(
        {
            "id": "research-squad",
            "name": "Research Squad",
            "members": _three_members(),
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "prefer grok_agent for revision control",
        }
    )
    assert stored["chief_of_staff_id"] == "jeeves"
    assert stored["chief_of_staff_instructions"] == "prefer grok_agent for revision control"
    # #739: leadership is roster-level; the member role tag is never written.
    roles = {m["id"]: m["role"] for m in stored["members"]}
    assert roles["jeeves"] == "default"
    assert roles["skeptic"] == "skeptic"
    assert resolve_chief_of_staff(stored)["id"] == "jeeves"

    again = normalize_roster(stored, roster_id="research-squad")
    assert again["chief_of_staff_id"] == "jeeves"
    assert again["chief_of_staff_instructions"] == "prefer grok_agent for revision control"


def test_clear_cos_omits_brief_at_runtime():
    roster = normalize_roster(
        {
            "id": "lab",
            "members": _three_members(),
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": DEFAULT_COS_STARTER,
        }
    )
    cleared = apply_cos_fields(roster, {"chief_of_staff_id": None, "chief_of_staff_instructions": ""})
    assert cleared["chief_of_staff_id"] is None
    assert cleared["chief_of_staff_instructions"] == ""
    assert runtime_brief_for_target(cleared, "all") is None
    assert cos_brief_for_member(cleared, "jeeves") is None
    ctx = team_run_context(cleared, "all", [{"role": "user", "content": "hi"}])
    assert ctx["brief_applied"] is False
    assert ctx["model_messages"] == [{"role": "user", "content": "hi"}]


def test_same_agent_on_two_teams_keeps_two_briefs():
    members = _three_members()
    alpha = normalize_roster(
        {
            "id": "team-a",
            "members": members,
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "prefer grok_agent for revision control",
        }
    )
    bravo = normalize_roster(
        {
            "id": "team-b",
            "members": members,
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "use skeptic only after implement",
        }
    )
    assert cos_brief_for_member(alpha, "jeeves") == "prefer grok_agent for revision control"
    assert cos_brief_for_member(bravo, "jeeves") == "use skeptic only after implement"
    assert cos_brief_for_member(alpha, "skeptic") is None
    assert cos_brief_for_member(bravo, "grok_agent") is None

    alpha_msgs = messages_with_cos_brief(alpha, "jeeves", [{"role": "user", "content": "go"}])
    bravo_msgs = messages_with_cos_brief(bravo, "jeeves", [{"role": "user", "content": "go"}])
    assert alpha_msgs[0]["role"] == "developer"
    assert "revision control" in alpha_msgs[0]["content"]
    assert "after implement" in bravo_msgs[0]["content"]
    non_cos = messages_with_cos_brief(alpha, "skeptic", [{"role": "user", "content": "go"}])
    assert non_cos == [{"role": "user", "content": "go"}]


def test_no_cos_is_today_behaviour():
    roster = normalize_roster({"id": "plain", "members": _three_members()})
    assert roster["chief_of_staff_id"] is None
    assert roster["chief_of_staff_instructions"] == ""
    ctx = team_run_context(roster, "all", [{"role": "user", "content": "hi"}])
    assert ctx["brief_applied"] is False
    assert ctx["chief_of_staff_id"] is None


def test_all_target_uses_cos_brief_member_target_does_not_unless_cos():
    roster = normalize_roster(
        {
            "id": "lab",
            "members": _three_members(),
            "chief_of_staff_id": "jeeves",
            "chief_of_staff_instructions": "coordinate the roster",
        }
    )
    assert runtime_brief_for_target(roster, "all") == "coordinate the roster"
    assert runtime_brief_for_target(roster, "jeeves") == "coordinate the roster"
    assert runtime_brief_for_target(roster, "skeptic") is None

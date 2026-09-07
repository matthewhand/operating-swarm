"""REQ-153 / #561 — list_agents + send_message, same-kind, team graph."""

from __future__ import annotations

from swarm.core import chat_store
from swarm.core.agent_mailbox import (
    ERROR_CALLER_KIND,
    ERROR_KIND_FILTER,
    ERROR_KIND_MISMATCH,
    ERROR_NOT_DISCOVERABLE,
    ERROR_TARGET_ARCHIVED,
    ERROR_TARGET_HIDDEN,
    ERROR_UNKNOWN_ID,
    LIST_TOOL_NAME,
    SEND_TOOL_NAME,
    AclEntry,
    AclPolicy,
    MailboxContext,
    Peer,
    attach_to_agent,
    install_mailbox_on_blueprint,
)
from swarm.core.transcript_roles import reconstruct_display

OFFICE = {
    "office": {
        "id": "office",
        "name": "Office",
        "members": [
            {"id": "pat", "kind": "api", "role": "default", "source": "blueprint:pat"},
            {"id": "cos", "kind": "api", "role": "chief_of_staff", "source": "blueprint:cos"},
            {"id": "support", "kind": "api", "role": "support", "source": "blueprint:support"},
            {"id": "research", "kind": "team", "team_id": "research", "role": "default", "source": "team:research"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "research": {
        "id": "research",
        "name": "Research",
        "members": [
            {"id": "ada", "kind": "api", "role": "default", "source": "blueprint:ada"},
            {"id": "lee", "kind": "cli", "role": "default", "source": "cli:lee"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "ops": {
        "id": "ops",
        "name": "Ops",
        "members": [
            {"id": "kim", "kind": "remote", "role": "default", "source": "placeholder:remote:kim"},
            {"id": "ivy", "kind": "api", "role": "default", "source": "blueprint:ivy"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
}


def _ctx(caller_id: str, **kwargs) -> MailboxContext:
    kwargs.setdefault("rosters", OFFICE)
    kwargs.setdefault("relationships", [])
    return MailboxContext(caller_id=caller_id, **kwargs)


def test_list_agents_is_team_scoped_same_kind():
    listed = _ctx("pat").list_peers()
    assert listed["ok"] is True
    ids = {row["id"] for row in listed["agents"]}
    assert ids == {"cos", "support"}
    assert all(row["kind"] == "api" for row in listed["agents"])
    assert "ada" not in ids
    assert "ivy" not in ids
    assert "lee" not in ids


def test_list_agents_omits_other_kinds_on_same_team():
    research = _ctx("ada").list_peers()
    ids = {row["id"] for row in research["agents"]}
    assert ids == set()
    assert "lee" not in ids


def test_unteamed_api_agent_sees_nobody():
    listed = _ctx("stranger", extra_peers=(Peer(id="stranger", kind="api"),)).list_peers()
    assert listed["ok"] is True
    assert listed["agents"] == []


def test_support_allow_all_same_kind():
    listed = _ctx("support").list_peers()
    ids = {row["id"] for row in listed["agents"]}
    assert ids == {"pat", "cos", "ada", "ivy"}
    assert listed["scope"] == "support_allow_all"
    assert "lee" not in ids
    assert "kim" not in ids


def test_cos_allow_all_same_kind():
    ids = {row["id"] for row in _ctx("cos").list_peers()["agents"]}
    assert "ivy" in ids
    assert "ada" in ids
    assert "lee" not in ids


def test_list_agents_kind_filter_rejects_cli():
    result = _ctx("pat").list_peers(kind="cli")
    assert result["ok"] is False
    assert result["error"] == ERROR_KIND_FILTER


def test_cli_caller_cannot_use_mailbox():
    result = _ctx("lee", caller_kind="cli").list_peers()
    assert result["ok"] is False
    assert result["error"] == ERROR_CALLER_KIND


def test_relationship_edge_makes_teams_mutually_discoverable():
    edges = [
        {
            "from_kind": "team",
            "from_id": "office",
            "to_kind": "team",
            "to_id": "ops",
        }
    ]
    pat = _ctx("pat", relationships=edges).list_peers()
    ids = {row["id"] for row in pat["agents"]}
    assert "ivy" in ids
    assert "cos" in ids
    assert "kim" not in ids

    ivy = _ctx("ivy", relationships=edges).list_peers()
    ivy_ids = {row["id"] for row in ivy["agents"]}
    assert "pat" in ivy_ids
    assert "cos" in ivy_ids


def test_team_agent_edge_is_mutual_and_same_kind():
    edges = [
        {"from_kind": "team", "from_id": "office", "to_kind": "agent", "to_id": "ada"}
    ]
    pat_ids = {row["id"] for row in _ctx("pat", relationships=edges).list_peers()["agents"]}
    assert "ada" in pat_ids
    ada_ids = {row["id"] for row in _ctx("ada", relationships=edges).list_peers()["agents"]}
    assert "pat" in ada_ids
    assert "lee" not in ada_ids


def test_send_message_delivers_attributed_transcript(tmp_path):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    result = ctx.send("cos", "please draft the brief")
    assert result["ok"] is True
    assert result["delivered"] is True
    assert result["target_id"] == "cos"
    assert result["sender_id"] == "pat"

    record = chat_store.load("u1", "cos", base_dir=tmp_path)
    assert record is not None
    turns = record["messages"]
    assert turns[-1]["role"] == "user"
    assert turns[-1]["content"] == "please draft the brief"
    assert turns[-1]["name"] == "pat"
    display = reconstruct_display(turns, record["ui_events"])
    hops = [row for row in display if str(row.get("content") or "").startswith("Message from ")]
    assert hops
    assert hops[-1]["content"] == "Message from pat"
    assert hops[-1].get("kind") == "hop"


def test_send_unknown_id():
    result = _ctx("pat").send("nobody", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_UNKNOWN_ID


def test_send_kind_guard_rejects_cli_teammate():
    result = _ctx("ada").send("lee", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_KIND_MISMATCH


def test_send_hidden_target():
    result = _ctx("pat", hidden_ids=frozenset({"cos"})).send("cos", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_TARGET_HIDDEN
    listed = _ctx("pat", hidden_ids=frozenset({"cos"})).list_peers()
    assert "cos" not in {row["id"] for row in listed["agents"]}


def test_send_archived_target():
    result = _ctx("pat", archived_ids=frozenset({"cos"})).send("cos", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_TARGET_ARCHIVED


def test_send_cross_team_denied():
    result = _ctx("pat").send("ivy", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_NOT_DISCOVERABLE


def test_acl_blacklist_hides_peer():
    acl = AclPolicy(mode="blacklist", entries=(AclEntry(kind="agent", id="cos"),))
    ids = {row["id"] for row in _ctx("pat", acl=acl).list_peers()["agents"]}
    assert "cos" not in ids
    assert "support" in ids


def test_acl_whitelist_limits_peers():
    acl = AclPolicy(mode="whitelist", entries=(AclEntry(kind="role", id="support"),))
    ids = {row["id"] for row in _ctx("pat", acl=acl).list_peers()["agents"]}
    assert ids == {"support"}


def test_empty_whitelist_hides_everyone_for_workers():
    acl = AclPolicy(mode="whitelist", entries=())
    ids = {row["id"] for row in _ctx("pat", acl=acl).list_peers()["agents"]}
    assert ids == set()
    denied = _ctx("pat", acl=acl).send("support", "hi")
    assert denied["ok"] is False
    assert denied["error"] == ERROR_NOT_DISCOVERABLE


def test_support_empty_whitelist_allow_all():
    acl = AclPolicy(mode="whitelist", entries=(), allow_all=True)
    ids = {row["id"] for row in _ctx("support", acl=acl).list_peers()["agents"]}
    assert ids == {"pat", "cos", "ada", "ivy"}


def test_acl_team_entry_matches_roster_members():
    acl = AclPolicy(mode="whitelist", entries=(AclEntry(kind="team", id="office"),))
    ids = {row["id"] for row in _ctx("support", acl=acl).list_peers()["agents"]}
    assert ids == {"pat", "cos"}
    assert "ada" not in ids


def test_acl_blacklist_role_hides_matching_peers():
    acl = AclPolicy(mode="blacklist", entries=(AclEntry(kind="role", id="chief_of_staff"),))
    ids = {row["id"] for row in _ctx("pat", acl=acl).list_peers()["agents"]}
    assert "cos" not in ids
    assert "support" in ids


def test_send_message_enforces_whitelist():
    acl = AclPolicy(mode="whitelist", entries=(AclEntry(kind="agent", id="support"),))
    ok = _ctx("pat", acl=acl).send("support", "need a hand")
    assert ok["ok"] is True
    blocked = _ctx("pat", acl=acl).send("cos", "secret")
    assert blocked["ok"] is False
    assert blocked["error"] == ERROR_NOT_DISCOVERABLE


def test_send_redacts_secrets_in_store_and_logs(tmp_path, caplog):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    with caplog.at_level("INFO", logger="swarm.core.agent_mailbox"):
        result = ctx.send("cos", secret)
    assert result["ok"] is True
    record = chat_store.load("u1", "cos", base_dir=tmp_path)
    stored = record["messages"][-1]["content"]
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in stored
    assert "REDACTED" in stored or "sk-" not in stored
    joined = "\n".join(record.message for record in caplog.records)
    assert secret not in joined


def test_tenant_user_key_does_not_write_other_user(tmp_path):
    ctx = _ctx("pat", user_key="u1", chat_base_dir=tmp_path)
    ctx.send("cos", "private to u1")
    assert chat_store.load("u2", "cos", base_dir=tmp_path) is None
    assert chat_store.load("u1", "cos", base_dir=tmp_path) is not None


def test_tools_are_named_list_agents_and_send_message():
    ctx = _ctx("pat")
    names = {getattr(fn, "name", fn.__name__) for fn in ctx.as_callables()}
    assert names == {LIST_TOOL_NAME, SEND_TOOL_NAME}
    listed = ctx.list_agents_tool()
    assert listed["ok"] is True


def test_install_attaches_tools_to_existing_agent():
    ctx = _ctx("pat")

    class _Agent:
        tools = []

    class _Blueprint:
        metadata = {"role": "default"}
        agents = {"pat": _Agent()}

    attached = install_mailbox_on_blueprint(_Blueprint(), ctx)
    assert LIST_TOOL_NAME in attached
    assert SEND_TOOL_NAME in attached
    names = {getattr(t, "name", None) for t in _Blueprint.agents["pat"].tools}
    assert LIST_TOOL_NAME in names
    assert SEND_TOOL_NAME in names


def test_herdr_member_is_not_api_kind():
    rosters = {
        "office": {
            "id": "office",
            "name": "Office",
            "members": [
                {"id": "pat", "kind": "api", "role": "default", "source": "blueprint:pat"},
                {"id": "herd", "kind": "herdr", "role": "default", "source": "herdr:herd"},
            ],
            "wires": {"handoff": True, "as_tool": True},
        }
    }
    ids = {row["id"] for row in MailboxContext(caller_id="pat", rosters=rosters, relationships=[]).list_peers()["agents"]}
    assert "herd" not in ids
    result = MailboxContext(caller_id="pat", rosters=rosters, relationships=[]).send("herd", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_KIND_MISMATCH


def test_cli_install_attaches_nothing():
    ctx = _ctx("lee", caller_kind="cli")

    class _Agent:
        tools = []

    attached = attach_to_agent(_Agent(), ctx)
    assert attached == []

def test_send_message_surfaces_warning_without_user_key(tmp_path):
    ctx = _ctx("pat", user_key="", chat_base_dir=tmp_path)
    result = ctx.send("cos", "unauthenticated message")
    assert result["ok"] is True
    assert result["delivered"] is False
    assert result["warning"] == "delivery_skipped_no_user_key"


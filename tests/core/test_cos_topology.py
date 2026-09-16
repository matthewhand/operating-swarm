"""Issue #219 — CoS persistent section/topology tools (not TrueForge temp sub-agents)."""

from __future__ import annotations

import pytest

from swarm.core.agent_mailbox import AclEntry, AclPolicy, MailboxContext, Peer, apply_acl
from swarm.core.agent_mailbox_acl import (
    reset_mailbox_acl_cache,
    resolve_acl_policy,
)
from swarm.core.agent_roles import can_manage_agent_lifecycle, can_manage_topology
from swarm.core.agent_sections import (
    UNASSIGNED_SECTION_ID,
    SectionStore,
    reset_sections_cache,
    section_id_for_agent,
)
from swarm.core.cos_topology import (
    ARCHIVE_SECTION_TOOL,
    CREATE_SECTION_TOOL,
    ERROR_ALREADY_ARCHIVED,
    ERROR_CALLER_KIND,
    ERROR_PROTECTED,
    ERROR_ROLE,
    ERROR_UNKNOWN_ID,
    ERROR_UNKNOWN_SECTION,
    ERROR_XOR,
    LIST_SECTIONS_TOOL,
    MOVE_AGENT_TOOL,
    RENAME_SECTION_TOOL,
    SET_TALK_ACL_TOOL,
    TopologyContext,
    TopologyStores,
    attach_to_agent,
)
from swarm.core.roles.adapters import ChiefOfStaffRole
from swarm.core.roles.base import RoleContext


OFFICE = {
    "office": {
        "id": "office",
        "name": "Office",
        "members": [
            {"id": "cos", "kind": "api", "role": "chief_of_staff"},
            {"id": "skeptic_a", "kind": "api", "role": "skeptic"},
            {"id": "skeptic_b", "kind": "api", "role": "skeptic"},
            {"id": "pat", "kind": "api", "role": "default"},
            {"id": "eng", "kind": "api", "role": "engineer"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    }
}


@pytest.fixture(autouse=True)
def _isolate_stores(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_AGENT_SECTIONS_PATH", str(tmp_path / "agent_sections.json"))
    monkeypatch.setenv("SWARM_MAILBOX_ACL_PATH", str(tmp_path / "agent_mailbox_acl.json"))
    reset_sections_cache()
    reset_mailbox_acl_cache()
    yield
    reset_sections_cache()
    reset_mailbox_acl_cache()


def _ctx(role: str = "chief_of_staff", **kwargs) -> TopologyContext:
    stores = kwargs.pop("stores", None) or TopologyStores(
        sections=SectionStore(),
        rosters=OFFICE,
        known_ids=frozenset({"cos", "skeptic_a", "skeptic_b", "pat", "eng"}),
    )
    kwargs.setdefault("caller_id", "cos")
    kwargs.setdefault("caller_role", role)
    return TopologyContext(stores=stores, **kwargs)


def test_cos_gets_topology_tools_support_and_engineer_do_not():
    assert can_manage_topology("chief_of_staff")
    assert can_manage_topology("cos")
    assert not can_manage_topology("support")
    assert not can_manage_topology("engineer")
    assert can_manage_agent_lifecycle("support")
    assert can_manage_agent_lifecycle("cos")

    names = {getattr(fn, "name", fn.__name__) for fn in _ctx().as_callables()}
    assert names == {
        CREATE_SECTION_TOOL,
        RENAME_SECTION_TOOL,
        ARCHIVE_SECTION_TOOL,
        MOVE_AGENT_TOOL,
        SET_TALK_ACL_TOOL,
        LIST_SECTIONS_TOOL,
    }
    assert _ctx("support", caller_id="support").tool_objects() == []
    assert _ctx("engineer", caller_id="eng").tool_objects() == []
    assert _ctx("chief_of_staff").tool_objects()


def test_cli_cos_does_not_get_tools():
    ctx = _ctx(caller_kind="cli")
    assert ctx.tool_objects() == []
    denied = ctx.create_section("Review")
    assert denied["ok"] is False
    assert denied["error"] == ERROR_CALLER_KIND


def test_engineer_cannot_create_section():
    denied = _ctx("engineer", caller_id="eng").create_section("Review")
    assert denied["ok"] is False
    assert denied["error"] == ERROR_ROLE


def test_create_rename_archive_and_move():
    ctx = _ctx()
    created = ctx.create_section("Review", agent_ids="skeptic_a")
    assert created["ok"] is True
    section_id = created["section"]["id"]
    assert section_id.startswith("sec_")
    assert created["section"]["members"] == ["skeptic_a"]
    assert section_id_for_agent("skeptic_a", ctx.payload()) == section_id

    renamed = ctx.rename_section(section_id, "Locked review")
    assert renamed["ok"] is True
    assert renamed["section"]["name"] == "Locked review"

    moved = ctx.move_agent_to_section("skeptic_b", section_id)
    assert moved["ok"] is True
    listed = ctx.list_sections()
    assert listed["ok"] is True
    assert set(listed["sections"][0]["members"]) == {"skeptic_a", "skeptic_b"}

    unassigned = ctx.move_agent_to_section("skeptic_a", UNASSIGNED_SECTION_ID)
    assert unassigned["ok"] is True
    assert section_id_for_agent("skeptic_a", ctx.payload()) == UNASSIGNED_SECTION_ID

    archived = ctx.archive_section(section_id)
    assert archived["ok"] is True
    assert archived["section"]["archived"] is True
    assert section_id_for_agent("skeptic_b", ctx.payload()) == UNASSIGNED_SECTION_ID
    assert ctx.list_sections()["sections"] == []


def test_unknown_ids_are_honest_failures():
    ctx = _ctx()
    created = ctx.create_section("Review")
    section_id = created["section"]["id"]
    missing_agent = ctx.move_agent_to_section("no_such_bot", section_id)
    assert missing_agent["ok"] is False
    assert missing_agent["error"] == ERROR_UNKNOWN_ID
    missing_section = ctx.move_agent_to_section("pat", "sec_missing")
    assert missing_section["ok"] is False
    assert missing_section["error"] == ERROR_UNKNOWN_SECTION
    assert ctx.archive_section(UNASSIGNED_SECTION_ID)["error"] == ERROR_PROTECTED
    assert ctx.archive_section("sec_missing")["error"] == ERROR_UNKNOWN_SECTION
    assert ctx.archive_section(section_id)["ok"] is True
    assert ctx.archive_section(section_id)["error"] == ERROR_ALREADY_ARCHIVED


def test_nl_locked_review_section_writes_section_and_acl():
    ctx = _ctx()
    result = ctx.create_section(
        "locked review",
        agent_ids="skeptic_a,skeptic_b",
        internal_only=True,
    )
    assert result["ok"] is True
    section_id = result["section"]["id"]
    assert set(result["section"]["members"]) == {"skeptic_a", "skeptic_b"}
    assert result["section"]["internal_only"] is True
    assert result["acl"]
    for aid in ("skeptic_a", "skeptic_b"):
        resolved = resolve_acl_policy(aid, "skeptic")
        assert resolved.source == "agent"
        assert resolved.policy.mode == "whitelist"
        assert resolved.policy.entries == (AclEntry(kind="section", id=section_id),)


def test_set_talk_acl_xor_and_unknown_entry():
    ctx = _ctx()
    created = ctx.create_section("Review", agent_ids="skeptic_a")
    section_id = created["section"]["id"]
    both = ctx.set_talk_acl("pat", allow="skeptic_a", deny="eng")
    assert both["error"] == ERROR_XOR
    empty = ctx.set_talk_acl("pat")
    assert empty["error"] == ERROR_XOR
    unknown = ctx.set_talk_acl("pat", allow="ghost_bot")
    assert unknown["error"] == ERROR_UNKNOWN_ID
    ok = ctx.set_talk_acl("pat", allow=section_id)
    assert ok["ok"] is True
    assert ok["mode"] == "whitelist"
    assert ok["entries"] == [{"kind": "section", "id": section_id}]
    deny = ctx.set_talk_acl("pat", deny="eng")
    assert deny["ok"] is True
    assert deny["mode"] == "blacklist"
    team = ctx.set_talk_acl("pat", allow="team")
    assert team["ok"] is True
    assert team["entries"] == [{"kind": "team", "id": "office"}]


def test_section_acl_entry_filters_mailbox_peers():
    ctx = _ctx()
    created = ctx.create_section("Review", agent_ids="skeptic_a,skeptic_b")
    section_id = created["section"]["id"]
    catalog = {
        "skeptic_a": Peer(id="skeptic_a", kind="api", role="skeptic", sections={section_id}),
        "skeptic_b": Peer(id="skeptic_b", kind="api", role="skeptic", sections={section_id}),
        "pat": Peer(id="pat", kind="api", role="default"),
    }
    policy = AclPolicy(
        mode="whitelist",
        entries=(AclEntry(kind="section", id=section_id),),
    )
    visible = apply_acl({"skeptic_a", "skeptic_b", "pat"}, catalog, policy)
    assert visible == {"skeptic_a", "skeptic_b"}

    mailbox = MailboxContext(
        caller_id="skeptic_a",
        caller_role="skeptic",
        rosters=OFFICE,
        extra_peers=(
            Peer(id="skeptic_a", kind="api", role="skeptic", sections={section_id}),
            Peer(id="skeptic_b", kind="api", role="skeptic", sections={section_id}),
            Peer(id="pat", kind="api", role="default"),
        ),
        acl=policy,
    )
    ids = {row["id"] for row in mailbox.list_peers()["agents"]}
    assert ids == {"skeptic_b"}


def test_chief_of_staff_role_attaches_tools_when_wired():
    role = ChiefOfStaffRole()
    assert role.as_tool(RoleContext()) is None

    class Dummy:
        tools = []

    ctx = _ctx()
    attached = role.as_tool(RoleContext(agent=Dummy(), params={"topology": ctx}))
    assert CREATE_SECTION_TOOL in attached
    assert SET_TALK_ACL_TOOL in attached

    support = Dummy()
    support.tools = []
    assert attach_to_agent(support, _ctx("support", caller_id="support")) == []
    assert support.tools == []

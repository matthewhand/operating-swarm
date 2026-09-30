"""Issue #1224 — qualified role addresses (`role@rig`).

Sections are dynamic rigs; team rosters / Team Blueprints are static rigs.
Hermetic: no disk, injected catalogs and in-memory stores.
"""

from __future__ import annotations

import json

import pytest

from swarm.core import agent_sections
from swarm.core.agent_mailbox import MailboxContext
from swarm.core.rig_addresses import (
    ERROR_AMBIGUOUS_ROLE,
    ERROR_INVALID,
    ERROR_UNKNOWN_RIG,
    ERROR_UNKNOWN_ROLE,
    RIG_KIND_DYNAMIC,
    RIG_KIND_STATIC,
    UNASSIGNED_RIG,
    build_rig_catalog,
    format_rig_address,
    parse_rig_address,
    qualified_rig_address,
    resolve_rig_address,
    rig_for_agent,
)

FACTORY = {
    "factory": {
        "id": "factory",
        "name": "Factory",
        "blueprint_id": "factory-rsi",
        "members": [
            {"id": "skeptic", "kind": "api", "role": "skeptic", "source": "blueprint:skeptic"},
            {"id": "impl", "kind": "api", "role": "engineer", "source": "blueprint:impl"},
            {"id": "pat", "kind": "api", "role": "default", "source": "blueprint:pat"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
    "ops": {
        "id": "ops",
        "name": "Ops",
        "members": [
            {"id": "skeptic_two", "kind": "api", "role": "skeptic", "source": "blueprint:skeptic_two"},
            {"id": "kim", "kind": "api", "role": "default", "source": "blueprint:kim"},
        ],
        "wires": {"handoff": True, "as_tool": True},
    },
}

SECTIONS = {
    "schema": 1,
    "sections": [{"id": "sec_local", "name": "local"}],
    "membership": {"pat": "sec_local", "scout": "sec_local"},
}


def test_parse_and_format_roundtrip():
    parsed = parse_rig_address("skeptic@local")
    assert parsed is not None
    assert parsed.role == "skeptic"
    assert parsed.rig == "local"
    bare = parse_rig_address("skeptic")
    assert bare is not None and bare.role == "skeptic" and bare.rig is None
    assert parse_rig_address("") is None
    assert parse_rig_address("a@b@c") is None
    assert parse_rig_address("@local") is None
    assert format_rig_address("skeptic", "local") == "skeptic@local"
    assert format_rig_address("skeptic") == "skeptic"


def test_catalog_assigns_static_and_dynamic_rigs():
    catalog = build_rig_catalog(rosters=FACTORY, sections=SECTIONS)
    static = catalog.find_rig("factory")
    assert static is not None and static.kind == RIG_KIND_STATIC
    dynamic = catalog.find_rig("local")
    assert dynamic is not None and dynamic.kind == RIG_KIND_DYNAMIC
    assert {a.id for a in catalog.agents_in_rig(static)} >= {"skeptic", "impl", "pat"}
    assert {a.id for a in catalog.agents_in_rig(dynamic)} == {"pat", "scout"}


def test_qualified_hits_the_right_rig():
    # Same role "skeptic" exists in two static rigs; the suffix disambiguates.
    hit = resolve_rig_address("skeptic@ops", rosters=FACTORY)
    assert hit.ok is True
    assert hit.agent_id == "skeptic_two"
    assert hit.rig == "ops"
    assert hit.rig_kind == RIG_KIND_STATIC

    hit_factory = resolve_rig_address("skeptic@factory", rosters=FACTORY)
    assert hit_factory.ok is True
    assert hit_factory.agent_id == "skeptic"

    hit_member = resolve_rig_address("impl@factory", rosters=FACTORY)
    assert hit_member.ok is True and hit_member.agent_id == "impl"

    dynamic = resolve_rig_address("pat@local", rosters=FACTORY, sections=SECTIONS)
    assert dynamic.ok is True
    assert dynamic.agent_id == "pat"
    assert dynamic.rig_kind == RIG_KIND_DYNAMIC


def test_bare_role_resolves_in_active_rig():
    resolved = resolve_rig_address("skeptic", active_rig="ops", rosters=FACTORY)
    assert resolved.ok is True and resolved.agent_id == "skeptic_two"
    assert resolved.rig == "ops"


def test_bare_role_without_active_rig_is_ambiguous_when_repeated():
    resolved = resolve_rig_address("skeptic", rosters=FACTORY)
    assert resolved.ok is False
    assert resolved.error == ERROR_AMBIGUOUS_ROLE


def test_bare_role_without_active_rig_resolves_unique_seat():
    resolved = resolve_rig_address("engineer", rosters=FACTORY)
    assert resolved.ok is True and resolved.agent_id == "impl"


def test_unknown_rig_is_honest_error():
    resolved = resolve_rig_address("skeptic@nowhere", rosters=FACTORY)
    assert resolved.ok is False
    assert resolved.error == ERROR_UNKNOWN_RIG


def test_unknown_role_is_honest_error():
    resolved = resolve_rig_address("ghost@factory", rosters=FACTORY)
    assert resolved.ok is False
    assert resolved.error == ERROR_UNKNOWN_ROLE


def test_active_rig_unknown_is_honest_error():
    resolved = resolve_rig_address("skeptic", active_rig="ghost", rosters=FACTORY)
    assert resolved.ok is False
    assert resolved.error == ERROR_UNKNOWN_RIG


def test_malformed_address_is_honest_error():
    assert resolve_rig_address("skeptic@a@b").error == ERROR_INVALID


def test_rig_for_agent_prefers_team_blueprint_then_section():
    roster_rig = rig_for_agent("skeptic", rosters=FACTORY)
    assert roster_rig is not None and roster_rig.kind == RIG_KIND_STATIC
    # pat is on Factory AND in section local — the team blueprint wins.
    pat_rig = rig_for_agent("pat", rosters=FACTORY, sections=SECTIONS)
    assert pat_rig is not None and pat_rig.id == "factory"
    section_rig = rig_for_agent("scout", rosters=FACTORY, sections=SECTIONS)
    assert section_rig is not None and section_rig.kind == RIG_KIND_DYNAMIC


def test_qualified_rig_address_display():
    assert qualified_rig_address("skeptic", rosters=FACTORY) == "skeptic@Factory"
    assert qualified_rig_address("scout", rosters=FACTORY, sections=SECTIONS) == "default@local"
    assert qualified_rig_address("ghost") == "default"
    assert (
        qualified_rig_address("ghost", show_unassigned=True) == f"default@{UNASSIGNED_RIG}"
    )
    catalog = build_rig_catalog(agents={"ghost": "default"})
    assert catalog.find_rig("factory") is None


@pytest.fixture()
def _sections(tmp_path, monkeypatch):
    path = tmp_path / "agent_sections.json"
    monkeypatch.setenv("SWARM_AGENT_SECTIONS_PATH", str(path))
    path.write_text(json.dumps(SECTIONS), encoding="utf-8")
    agent_sections.reset_sections_cache()
    yield
    agent_sections.reset_sections_cache()


def test_mailbox_send_accepts_qualified_address(_sections):
    ctx = MailboxContext(caller_id="pat", rosters=FACTORY, relationships=[])
    result = ctx.send("skeptic@Factory", "review this")
    assert result["ok"] is True
    assert result["target_id"] == "skeptic"

    dynamic = ctx.send("pat@local", "self ping")
    assert dynamic["ok"] is True
    assert dynamic["target_id"] == "pat"


def test_mailbox_send_unknown_rig_is_honest_error(_sections):
    ctx = MailboxContext(caller_id="pat", rosters=FACTORY, relationships=[])
    result = ctx.send("skeptic@nowhere", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_UNKNOWN_RIG


def test_mailbox_send_unknown_role_is_honest_error(_sections):
    ctx = MailboxContext(caller_id="pat", rosters=FACTORY, relationships=[])
    result = ctx.send("ghost@Factory", "hi")
    assert result["ok"] is False
    assert result["error"] == ERROR_UNKNOWN_ROLE

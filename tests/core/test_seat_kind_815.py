"""#815 — canonical SeatKind + SeatDescriptor (backend half)."""

from __future__ import annotations

import json

from swarm.core.seat_kind import (
    SEAT_KINDS,
    dispatch_seat_kind,
    normalize_seat_kind,
    resolve_hop_kind,
    seat_descriptor,
    seat_kind_for_agent,
    seat_kind_from_stored,
    seat_param_for_kind,
)


def test_seat_kinds_are_exactly_the_four_routing_values():
    assert SEAT_KINDS == ("api", "cli", "remote", "team")


def test_normalize_rejects_unknown_kinds():
    assert normalize_seat_kind("api") == "api"
    assert normalize_seat_kind("design") is None  # authoring tag, not a seat
    assert normalize_seat_kind("") is None


def test_classification_by_source_prefix():
    assert seat_kind_for_agent("cli:grok") == "cli"
    assert seat_kind_for_agent("remote:omb") == "remote"
    assert seat_kind_for_agent("team:office") == "team"
    assert seat_kind_for_agent("jeeves") == "api"


def test_classification_prefers_explicit_kind():
    assert seat_kind_for_agent("office", explicit="team") == "team"
    # Unknown explicit kinds fall through to prefix classification.
    assert seat_kind_for_agent("cli:grok", explicit="design") == "cli"


def test_remote_impl_ids_and_cli_rail_ids_classify():
    assert seat_kind_for_agent("omb") == "remote"
    assert seat_kind_for_agent("herdr:w3:p5") == "remote"
    assert seat_kind_for_agent("grok") == "cli"  # CLI catalog rail id


def test_stored_kinds_collapse_onto_one_seat_kind():
    """#1437 — blueprint/swarm/personality are API seats, not extra kinds."""
    assert seat_kind_from_stored("blueprint") == "api"
    assert seat_kind_from_stored("swarm") == "api"
    assert seat_kind_from_stored("personality") == "api"
    assert seat_kind_from_stored("llm") == "api"
    assert seat_kind_from_stored("herdr") == "remote"
    assert seat_kind_from_stored("team") == "team"
    assert seat_kind_from_stored("design") is None
    assert seat_kind_from_stored("") is None


def test_recipe_ids_classify_as_their_seat():
    assert seat_kind_for_agent("remote_harness") == "remote"
    assert seat_kind_for_agent("cli_agent") == "cli"


def test_design_file_does_not_reclassify_an_api_id(monkeypatch, tmp_path):
    """A router design is metadata on the agent object. The id classifier
    must stay api for an unknown id even when that id is a CLI or remote
    design on disk — otherwise ``jeeves == api`` depends on the operator's
    ``router_designs.json``.
    """
    path = tmp_path / "router_designs.json"
    path.write_text(
        json.dumps(
            {
                "agents": [
                    {"agent_id": "jeeves", "kind": "cli"},
                    {"agent_id": "desk", "kind": "remote"},
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(path))
    assert seat_kind_for_agent("jeeves") == "api"
    assert seat_kind_for_agent("desk") == "api"


def test_dispatch_seat_kind_does_not_let_blueprint_reclassify():
    assert dispatch_seat_kind("cli", "support") == "cli"
    assert dispatch_seat_kind("remote", "codey") == "remote"
    assert dispatch_seat_kind("blueprint", "codey") == "api"
    assert dispatch_seat_kind("swarm", "desk") == "api"
    assert dispatch_seat_kind(None, "remote_harness") == "remote"


def test_blueprint_prefix_does_not_hide_remote_or_cli_issue_1436():
    assert seat_kind_for_agent("blueprint:omb") == "remote"
    assert seat_kind_for_agent("blueprint:remote:herdr") == "remote"
    assert seat_kind_for_agent("blueprint:cli:grok") == "cli"
    assert seat_kind_for_agent("blueprint:planner") == "api"
    seat = seat_descriptor("blueprint:remote:herdr")
    assert seat["kind"] == "remote"
    assert seat["id"] == "herdr"


def test_resolve_hop_kind_does_not_hardcode_api_issue_1436():
    assert resolve_hop_kind("api", "omb") == "remote"
    assert resolve_hop_kind("api", "grok") == "cli"
    assert resolve_hop_kind("blueprint", "omb") == "remote"
    assert resolve_hop_kind("blueprint", "auxiliary") == "api"
    assert resolve_hop_kind("api", "support") == "api"
    assert resolve_hop_kind("remote", "omb") == "remote"
    assert resolve_hop_kind("cli", "agy") == "cli"


def test_seat_param_vocabulary_matches_spa():
    assert seat_param_for_kind("api") == "blueprint"
    assert seat_param_for_kind("cli") == "cli"
    assert seat_param_for_kind("remote") == "remote"
    assert seat_param_for_kind("team") == "team"


def test_descriptor_strips_source_prefixes_and_keeps_state():
    seat = seat_descriptor("cli:grok", session="sess-9")
    assert seat["kind"] == "cli"
    assert seat["id"] == "grok"
    assert seat["session"] == "sess-9"

    gateway = seat_descriptor("api_agent", model="claude-work")
    assert gateway["kind"] == "api"
    assert gateway["model"] == "claude-work"
    assert "session" not in gateway

"""#815 — canonical SeatKind + SeatDescriptor (backend half)."""

from __future__ import annotations

from swarm.core.seat_kind import (
    SEAT_KINDS,
    normalize_seat_kind,
    seat_descriptor,
    seat_kind_for_agent,
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

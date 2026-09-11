"""Issue #162 — named seats, matching tools, assigned project."""

from __future__ import annotations

import pytest

from swarm.core.agent_settings import reset_agent_settings_cache
from swarm.core.fleet_seats import (
    FleetSeatError,
    as_callables,
    bound_workdir,
    create_seat,
    invoke_named_tool,
    list_seats,
    named_tools,
    reset_fleet_seats_cache,
    tool_name_for,
)


@pytest.fixture
def seats_home(tmp_path, monkeypatch):
    store = tmp_path / "fleet_seats.json"
    settings = tmp_path / "agent_settings.json"
    monkeypatch.setenv("SWARM_FLEET_SEATS_PATH", str(store))
    monkeypatch.setenv("SWARM_AGENT_SETTINGS_PATH", str(settings))
    reset_fleet_seats_cache()
    reset_agent_settings_cache()
    yield tmp_path
    reset_fleet_seats_cache()
    reset_agent_settings_cache()


def _three(tmp_path):
    rows = []
    for ident, role in (
        ("prove162-grok", "cos"),
        ("prove162-pi", "engineer"),
        ("prove162-opencode", "skeptic"),
    ):
        workdir = tmp_path / "projects" / ident
        rows.append(create_seat(ident, workdir, role=role))
    return rows


def test_create_list_named_seats_match_fleet_pattern(seats_home):
    rows = _three(seats_home)
    listed = list_seats()
    assert [r["agent_id"] for r in listed] == [
        "prove162-grok",
        "prove162-opencode",
        "prove162-pi",
    ]
    for row in rows:
        assert row["tool_name"] == row["agent_id"]
        assert row["display"] == row["agent_id"]
        assert row["workdir"].endswith(row["agent_id"])
        assert bound_workdir(row["agent_id"]) == row["workdir"]


def test_short_software_dev_names_are_valid(seats_home, tmp_path):
    for ident in ("cos", "engineer", "skeptic"):
        row = create_seat(ident, tmp_path / ident)
        assert row["agent_id"] == ident
        assert row["tool_name"] == ident


def test_rejects_non_fleet_id(seats_home, tmp_path):
    with pytest.raises(FleetSeatError):
        create_seat("not a seat", tmp_path / "x")
    with pytest.raises(FleetSeatError):
        create_seat("solo", tmp_path / "x")


def test_named_tools_match_agent_ids(seats_home):
    _three(seats_home)
    tools = named_tools()
    ids = {row["agent_id"] for row in list_seats()}
    assert set(tools) == ids
    for ident in ids:
        assert tool_name_for(ident) == ident


def test_invoke_writes_only_in_assigned_project(seats_home):
    rows = _three(seats_home)
    results = []
    for row in rows:
        out = invoke_named_tool(row["agent_id"])
        assert out["ok"] is True
        assert out["tool_name"] == row["agent_id"]
        marker = (seats_home / "projects" / row["agent_id"] / "_fleet_seat_pass.txt")
        text = marker.read_text(encoding="utf-8")
        assert text.startswith("PASS ")
        assert row["agent_id"] in text
        results.append(out["evidence"])
    # Sibling project must not see another seat's marker.
    grok_dir = seats_home / "projects" / "prove162-grok"
    pi_marker = grok_dir / "_from_pi.txt"
    assert not pi_marker.exists()
    other = invoke_named_tool(
        "prove162-pi",
        path="../prove162-grok/stolen.txt",
        content="nope",
    )
    assert other["ok"] is False
    assert other["error"] == "workdir_escape"
    assert not (grok_dir / "stolen.txt").exists()
    assert len(results) == 3


def test_as_callables_are_named_after_seats(seats_home):
    _three(seats_home)
    fns = as_callables()
    names = {getattr(fn, "name") for fn in fns}
    assert names == {"prove162-grok", "prove162-pi", "prove162-opencode"}
    hit = next(fn for fn in fns if fn.name == "prove162-grok")
    out = hit()
    assert out["ok"] is True
    assert out["tool_name"] == "prove162-grok"

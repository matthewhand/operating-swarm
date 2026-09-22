"""REQ-156: example graph JSON enforces intended handoff edges."""

from __future__ import annotations

import json

import pytest

from swarm.core.handoff_graph import (
    DEMO_ROSTER_IDS,
    MODE_A_MEMBER_NAMES,
    MODE_B_FUNNY_NAMES,
    MODE_B_MEMBER_NAMES,
    PIPELINE_GRAPH_ID,
    SKEPTIC_LOOP_GRAPH_ID,
    assert_edges_match,
    build_agents,
    example_pack_dir,
    live_edges,
    load_demo_rosters,
    load_example_graph,
    load_example_roster,
    merge_demo_rosters,
    normalize_graph,
    seed_demo_rosters,
)
from swarm.core.team_rosters import normalize_roster

PIPELINE_EDGES = frozenset({("ba", "engineer"), ("engineer", "tester")})
PIPELINE_FORBIDDEN = frozenset(
    {
        ("ba", "tester"),
        ("engineer", "ba"),
        ("tester", "ba"),
        ("tester", "engineer"),
    }
)
SKEPTIC_EDGES = frozenset(
    {
        ("ba", "engineer"),
        ("engineer", "tester"),
        ("tester", "skeptic"),
        ("skeptic", "engineer"),
    }
)
SKEPTIC_FORBIDDEN = frozenset(
    {
        ("ba", "tester"),
        ("ba", "skeptic"),
        ("skeptic", "ba"),
        ("skeptic", "tester"),
    }
)


def test_example_pack_files_exist():
    pack = example_pack_dir()
    assert pack.is_dir()
    for name in (
        "sdlc-pipeline.json",
        "sdlc-skeptic-loop.json",
        "README.md",
        *{f"{rid}.json" for rid in DEMO_ROSTER_IDS},
    ):
        assert (pack / name).is_file(), name


def test_pipeline_declared_and_live_edges_match():
    graph = load_example_graph(PIPELINE_GRAPH_ID)
    assert graph.variant == "forced-sequence"
    assert graph.entry == "ba"
    assert graph.declared_edges() == PIPELINE_EDGES
    agents = build_agents(graph)
    assert set(agents) == {"ba", "engineer", "tester"}
    assert live_edges(agents) == PIPELINE_EDGES
    assert_edges_match(graph, agents)
    live = live_edges(agents)
    for forbidden in PIPELINE_FORBIDDEN:
        assert forbidden not in live
    assert graph.outgoing("tester") == ()
    assert graph.outgoing("ba") == ("engineer",)


def test_skeptic_loop_punt_back_to_engineer():
    graph = load_example_graph(SKEPTIC_LOOP_GRAPH_ID)
    assert graph.variant == "circular-skeptic"
    assert graph.declared_edges() == SKEPTIC_EDGES
    agents = build_agents(graph)
    assert "skeptic" in agents
    assert live_edges(agents) == SKEPTIC_EDGES
    assert_edges_match(graph, agents)
    live = live_edges(agents)
    for forbidden in SKEPTIC_FORBIDDEN:
        assert forbidden not in live
    assert ("skeptic", "engineer") in live


def test_cli_or_remote_cannot_be_edge_source():
    raw = {
        "id": "bad",
        "name": "Bad",
        "variant": "forced-sequence",
        "entry": "ba",
        "nodes": [
            {"id": "ba", "name": "BA", "kind": "api"},
            {"id": "grok-cli", "name": "Grok CLI", "kind": "cli"},
        ],
        "edges": [{"from": "grok-cli", "to": "ba", "channel": "handoff"}],
    }
    with pytest.raises(ValueError, match="kind=api"):
        normalize_graph(raw)


def test_unknown_edge_endpoint_rejected():
    raw = {
        "id": "bad",
        "name": "Bad",
        "variant": "forced-sequence",
        "entry": "ba",
        "nodes": [{"id": "ba", "name": "BA", "kind": "api"}],
        "edges": [{"from": "ba", "to": "ghost", "channel": "handoff"}],
    }
    with pytest.raises(ValueError, match="unknown node"):
        normalize_graph(raw)


def test_demo_rosters_normalize_and_span_kinds():
    rosters = {r["id"]: normalize_roster(r) for r in load_demo_rosters()}
    assert set(rosters) == set(DEMO_ROSTER_IDS)

    pipeline = rosters["demo-sdlc-pipeline"]
    assert [m["id"] for m in pipeline["members"]] == ["cos", "ba", "engineer", "tester"]
    assert all(m["kind"] == "api" for m in pipeline["members"])
    assert pipeline["wires"]["handoff"] is True
    assert pipeline["chief_of_staff_id"] == "cos"
    names = {m["id"]: m["name"] for m in pipeline["members"]}
    assert names["ba"] == MODE_B_MEMBER_NAMES["ba"]
    assert names["engineer"] == MODE_B_MEMBER_NAMES["engineer"]
    assert names["tester"] == MODE_B_MEMBER_NAMES["tester"]
    assert names["cos"] == MODE_B_MEMBER_NAMES["cos"]
    assert "LiteLLM API" not in names.values()

    loop = rosters["demo-sdlc-skeptic-loop"]
    roles = {m["id"]: m["role"] for m in loop["members"]}
    assert roles["skeptic"] == "skeptic"
    assert loop["chief_of_staff_id"] == "cos"
    loop_names = {m["id"]: m["name"] for m in loop["members"]}
    assert loop_names["skeptic"] == MODE_B_MEMBER_NAMES["skeptic"]
    assert loop_names["cos"] == MODE_B_MEMBER_NAMES["cos"]

    bridge = rosters["demo-bridge"]
    kinds = {m["id"]: m["kind"] for m in bridge["members"]}
    assert kinds == {
        "cos": "api",
        "grok-cli": "cli",
        "hermes-remote": "remote",
    }
    # #739/#979: the legacy member stamp is recovered to chief_of_staff_id
    # and demoted; authority lives at roster level.
    assert not any(m["role"] == "chief_of_staff" for m in bridge["members"])
    assert bridge["chief_of_staff_id"] == "cos"
    bridge_names = {m["id"]: m["name"] for m in bridge["members"]}
    assert bridge_names["cos"] == MODE_B_MEMBER_NAMES["cos"]
    assert bridge_names["grok-cli"] == MODE_A_MEMBER_NAMES["grok-cli"]
    assert bridge_names["hermes-remote"] == MODE_A_MEMBER_NAMES["hermes-remote"]

    kinds_roster = rosters["demo-harness-kinds"]
    labels = {m["id"]: m["kind"] for m in kinds_roster["members"]}
    assert labels["grok-cli"] == "cli"
    assert labels["antigravity-cli"] == "cli"
    assert labels["litellm-api"] == "api"
    assert labels["hermes-remote"] == "remote"
    assert labels["openmousbot-remote"] == "remote"
    kind_names = {m["id"]: m["name"] for m in kinds_roster["members"]}
    assert kind_names == MODE_A_MEMBER_NAMES
    assert "OMB" not in kind_names.values()
    assert "OpenMousBot Remote" in kind_names.values()
    assert kinds_roster.get("chief_of_staff_id") in (None, "")


def test_mode_b_funny_names_are_documented_alternates_not_seeded():
    seeded = {
        m["name"]
        for roster in load_demo_rosters()
        for m in roster["members"]
        if m.get("id") in MODE_B_FUNNY_NAMES
    }
    assert MODE_B_MEMBER_NAMES["engineer"] in seeded
    assert MODE_B_FUNNY_NAMES["engineer"] not in seeded
    assert MODE_B_FUNNY_NAMES["ba"] not in seeded


def test_example_json_has_no_secret_literals():
    pack = example_pack_dir()
    blob = ""
    for path in pack.glob("*.json"):
        blob += path.read_text(encoding="utf-8")
    lowered = blob.lower()
    for needle in ("sk-", "github_pat_", "ghp_", "bearer ", "xox"):
        assert needle not in lowered
    assert "10.0.0." not in blob


def test_seed_is_additive_and_skips_existing(tmp_path):
    dest = tmp_path / "team_rosters.json"
    dest.write_text(
        json.dumps({"keep-me": {"id": "keep-me", "name": "Keep", "members": []}}),
        encoding="utf-8",
    )
    first = seed_demo_rosters(dest, overwrite=False, dry_run=False)
    assert "keep-me" in first
    assert "demo-bridge" in first
    first["demo-bridge"] = {"id": "demo-bridge", "name": "CUSTOM"}
    dest.write_text(json.dumps(first), encoding="utf-8")
    second = seed_demo_rosters(dest, overwrite=False, dry_run=False)
    assert second["keep-me"]["id"] == "keep-me"
    assert second["demo-bridge"]["name"] == "CUSTOM"
    third = seed_demo_rosters(dest, overwrite=True, dry_run=False)
    assert third["demo-bridge"]["name"] == "Demo Bridge"
    assert "keep-me" in third


def test_merge_refuses_non_demo_id():
    with pytest.raises(ValueError, match="non-demo"):
        merge_demo_rosters({}, [{"id": "office", "name": "Office"}])


def test_load_example_roster_matches_filename():
    roster = load_example_roster("demo-bridge")
    assert roster["id"] == "demo-bridge"
    assert roster["wires"]["as_tool"] is True


def test_seed_script_cli_dry_run(tmp_path):
    import subprocess
    import sys

    from swarm.core.handoff_graph import repo_root

    dest = tmp_path / "cfg"
    dest.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/seed_req156_demo.py",
            "--config-dir",
            str(dest),
            "--dry-run",
        ],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "demo-bridge" in proc.stdout
    assert "dry-run" in proc.stdout
    assert not (dest / "team_rosters.json").exists()


def test_seed_demo_agents_script_reset_alias(tmp_path):
    import subprocess
    import sys

    from swarm.core.handoff_graph import repo_root

    dest = tmp_path / "cfg"
    dest.mkdir()
    dest.joinpath("team_rosters.json").write_text(
        json.dumps({"demo-bridge": {"id": "demo-bridge", "name": "CUSTOM", "members": []}}),
        encoding="utf-8",
    )
    proc = subprocess.run(
        [
            sys.executable,
            "scripts/seed_demo_agents.py",
            "--config-dir",
            str(dest),
            "--reset",
        ],
        cwd=repo_root(),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    written = json.loads((dest / "team_rosters.json").read_text(encoding="utf-8"))
    assert written["demo-bridge"]["name"] == "Demo Bridge"
    names = {m["id"]: m["name"] for m in written["demo-harness-kinds"]["members"]}
    assert names["openmousbot-remote"] == "OpenMousBot Remote"

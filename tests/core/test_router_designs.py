"""Tests for Swarm agent designer persistence."""

import json

import pytest

from swarm.core.router_designs import (
    delete_design,
    load_designs,
    upsert_design,
    validate_design,
)


@pytest.fixture
def designs_file(tmp_path, monkeypatch):
    path = tmp_path / "router_designs.json"
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(path))
    return path


def test_validate_personality_requires_instructions():
    with pytest.raises(ValueError, match="instructions"):
        validate_design({"kind": "personality", "name": "Echo"})


def test_validate_rejects_reserved_id():
    with pytest.raises(ValueError, match="reserved"):
        validate_design({
            "kind": "personality",
            "name": "Router",
            "agent_id": "router",
            "instructions": "hi",
        })


def test_validate_cli_rejects_unknown_and_omb():
    with pytest.raises(ValueError, match="catalog"):
        validate_design({"kind": "cli", "name": "OMB", "cli": "omb"})
    with pytest.raises(ValueError, match="catalog"):
        validate_design({"kind": "cli", "name": "Nope", "cli": "not-a-cli"})
    spec = validate_design({"kind": "cli", "name": "Agy", "cli": "agy"})
    assert spec["cli"] == "agy" and spec["group"] == "tools"
    assert spec["agent_type"] == "cli"


def test_upsert_personality_and_cli(designs_file):
    spec = upsert_design({
        "kind": "personality",
        "name": "Night Editor",
        "instructions": "Tighten prose.",
    })
    assert spec["agent_id"] == "night-editor"
    assert spec["kind"] == "personality"
    assert spec["agent_type"] == "api"

    cli = upsert_design({
        "kind": "cli",
        "name": "Grok greeter",
        "cli": "grok",
    })
    assert cli["group"] == "tools"
    stored = load_designs()
    ids = {a["agent_id"] for a in stored}
    assert ids == {"night-editor", "grok-greeter"}
    assert json.loads(designs_file.read_text())["agents"]


def test_kind_api_is_personality_or_swarm_from_personas():
    single = validate_design({
        "kind": "api",
        "name": "Night Editor",
        "instructions": "Tighten prose.",
    })
    assert single["kind"] == "personality"
    assert single["agent_type"] == "api"

    swarm = validate_design({
        "kind": "api",
        "name": "Desk",
        "personas": [
            {"name": "A", "instructions": "alpha"},
            {"name": "B", "instructions": "beta"},
        ],
    })
    assert swarm["kind"] == "swarm"
    assert swarm["agent_type"] == "api"
    assert len(swarm["personas"]) == 2


def test_upsert_swarm_needs_two_personas(designs_file):
    with pytest.raises(ValueError, match="two personas"):
        upsert_design({
            "kind": "swarm",
            "name": "Tiny",
            "personas": [{"name": "Only", "instructions": "solo"}],
        })
    spec = upsert_design({
        "kind": "swarm",
        "name": "Desk",
        "personas": [
            {"name": "A", "instructions": "alpha"},
            {"name": "B", "instructions": "beta"},
        ],
    })
    assert spec["kind"] == "swarm"
    assert len(spec["personas"]) == 2


def test_upsert_remote_team(designs_file):
    spec = upsert_design({
        "kind": "remote",
        "name": "Hermes",
        "framework": "hermes",
        "base_url": "http://198.51.100.36:9119/v1",
    })
    assert spec["kind"] == "remote"
    assert spec["group"] == "remote"
    assert spec["base_url"].startswith("http://")


def test_delete_design(designs_file):
    upsert_design({"kind": "cli", "name": "Temp", "cli": "claude"})
    assert delete_design("temp") is True
    assert load_designs() == []
    assert delete_design("temp") is False

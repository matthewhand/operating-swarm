"""Behaviour tests for the public-demo script engine (REQ-882 / #279)."""

from __future__ import annotations

from swarm.demo.engine import demo_body_for, iter_demo_frames, match_scenario
from swarm.demo.mode import demo_stream_delay_s, is_demo_mode
from swarm.demo.scenarios import DEMO_FALLBACK_NOTICE, DEMO_SCENARIOS, TOUR_PROMPT


def test_is_demo_mode_reads_truthy_env(monkeypatch):
    monkeypatch.delenv("SWARM_DEMO_MODE", raising=False)
    assert is_demo_mode() is False
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    assert is_demo_mode() is True
    monkeypatch.setenv("SWARM_DEMO_MODE", "false")
    assert is_demo_mode() is False


def test_pytest_stream_delay_defaults_to_zero():
    assert demo_stream_delay_s() == 0.0


def test_exact_chip_selects_sdlc():
    row = match_scenario("Build a REST API with the SDLC team")
    assert row.id == "sdlc"
    assert "Product Owner" in row.body
    assert "Skeptic" in row.body


def test_keyword_match_cli_and_remote():
    assert match_scenario("please run pytest in the git repo").id == "cli"
    assert match_scenario("can you ping hermes telemetry").id == "remote"


def test_unmatched_prompt_uses_fallback_notice():
    row = match_scenario("Write a poem about rust")
    assert row.id == "fallback"
    assert DEMO_FALLBACK_NOTICE in demo_body_for("Write a poem about rust")


def test_tour_prompt_is_exact():
    assert match_scenario(TOUR_PROMPT).id == "tour"


def test_iter_frames_emits_status_chunks_and_events():
    frames = list(iter_demo_frames("Simulate a CLI git refactor"))
    kinds = [f.kind for f in frames]
    assert kinds.count("status") >= 1
    assert "chunk" in kinds
    assert "json" in kinds
    body = "".join(f.text for f in frames if f.kind == "chunk")
    assert "pytest" in body
    assert "<script>" not in body


def test_catalog_covers_four_showcases():
    ids = {row.id for row in DEMO_SCENARIOS}
    assert {"sdlc", "cli", "remote", "team", "tour"} <= ids


def test_demo_mode_implies_anonymous_even_under_pytest(monkeypatch):
    from swarm.middleware import swarm_allow_anonymous

    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    monkeypatch.delenv("SWARM_ALLOW_ANONYMOUS", raising=False)
    assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=True) is True
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "0")
    assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=True) is False

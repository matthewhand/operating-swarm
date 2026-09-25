"""#1157 — designed personality seats must actually run a turn.

Live evidence: sending to the ``api-demo-litellm`` seat logged ``Blueprint ID
'api-demo-litellm' not found in available blueprint classes`` and the turn
died before any LLM call — the user message persisted with no assistant row.

Root cause: ``resolve_chat_blueprint_id`` remaps CLI designs (via the CLI
catalog) and the two starter seats, but designed personality/swarm agents
(``router_designs.json``) fall through as raw ids that match no blueprint
class. They are meant to run through the ``agent_router`` blueprint with a
direct target — that is where ``_attach_designed`` binds their real
openai-agents Agent objects.

Contract:
- ``designed_agent_kind(id)`` → the design's kind (or None).
- ``resolve_chat_blueprint_id`` routes personality/swarm designs to
  ``agent_router``; CLI designs keep the ``cli_agent`` remap; everything
  else unchanged.
- ``designed_seat_params(id)`` → ``{target_agent, routing_strategy: direct}``
  for those seats; ``get_blueprint_instance`` applies it (source-pinned).
"""

from __future__ import annotations

from swarm.core.agent_kind import resolve_chat_blueprint_id
from swarm.core.router_designs import designed_agent_kind, designed_seat_params


def _write_designs(tmp_path, monkeypatch, rows: list[dict]) -> None:
    """Hermetic designs file — the sandboxed test env never reads user config."""
    import json

    designs = tmp_path / "router_designs.json"
    designs.write_text(json.dumps({"agents": rows}), encoding="utf-8")
    monkeypatch.setenv("SWARM_ROUTER_DESIGNS", str(designs))


def test_personality_design_routes_to_agent_router(tmp_path, monkeypatch):
    _write_designs(tmp_path, monkeypatch, [{"agent_id": "api-demo-litellm", "kind": "personality"}])
    assert resolve_chat_blueprint_id("api-demo-litellm") == "agent_router"


def test_designed_agent_kind_reads_the_designs_file(tmp_path, monkeypatch):
    _write_designs(
        tmp_path,
        monkeypatch,
        [
            {"agent_id": "api-demo-litellm", "kind": "personality"},
            {"agent_id": "cli-demo-agy", "kind": "cli"},
        ],
    )
    assert designed_agent_kind("api-demo-litellm") == "personality"
    assert designed_agent_kind("cli-demo-agy") == "cli"
    assert designed_agent_kind("no-such-seat") is None
    assert designed_agent_kind("") is None


def test_cli_designs_keep_their_cli_agent_remap(tmp_path, monkeypatch):
    _write_designs(tmp_path, monkeypatch, [{"agent_id": "cli-demo-agy", "kind": "cli"}])
    assert resolve_chat_blueprint_id("cli-demo-agy") == "cli_agent"
    assert resolve_chat_blueprint_id("cli_agent") == "cli_agent"


def test_regular_blueprint_ids_unchanged(tmp_path, monkeypatch):
    _write_designs(tmp_path, monkeypatch, [])
    for raw in ("support", "chatbot", "software_dev", "moa", "agent_router"):
        assert resolve_chat_blueprint_id(raw) == raw


def test_designed_seat_params_direct(tmp_path, monkeypatch):
    _write_designs(tmp_path, monkeypatch, [{"agent_id": "api-demo-litellm", "kind": "personality"}])
    params = designed_seat_params("api-demo-litellm")
    assert params == {"target_agent": "api-demo-litellm", "routing_strategy": "direct"}


def test_designed_seat_params_empty_for_non_designs(tmp_path, monkeypatch):
    _write_designs(tmp_path, monkeypatch, [{"agent_id": "x", "kind": "personality"}])
    assert designed_seat_params("support") == {}
    assert designed_seat_params("cli-demo-agy") == {}


def test_get_blueprint_instance_applies_seat_params():
    # Source pin: the instance factory must feed designed_seat_params into
    # set_params for router-routed seats.
    from pathlib import Path

    utils = (
        Path(__file__).resolve().parents[2]
        / "src" / "swarm" / "views" / "utils.py"
    ).read_text(encoding="utf-8")
    assert "designed_seat_params" in utils, (
        "#1157: get_blueprint_instance must apply designed-seat params"
    )

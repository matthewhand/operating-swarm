"""Remote ask-user bridge: a paused remote send is elicited through the chat
ask-user UI, answered, and resumed by POSTing the client tool response.

Hermetic: a loopback HTTP server stands in for TrueForge; no LAN, no LLM.
"""

from __future__ import annotations

import json
import threading
import types
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import (
    RemoteHarnessBlueprint,
)
from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_ASK_USER_BRIDGE_ATTR,
    install_remote_ask_user_bridge,
    pending_question_from_result,
    remote_ask_user_enabled,
)
from swarm.remotes.registry import create_remote_adapter
from functools import partial


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    route_hits: dict[tuple[str, str], int] = {}
    received_bodies: list[tuple[str, str, Any]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        length = int(self.headers.get("Content-Length", 0))
        body = None
        if length > 0:
            raw = self.rfile.read(length).decode("utf-8")
            try:
                body = json.loads(raw)
            except Exception:
                body = raw
            self.received_bodies.append((method, path, body))
        entry = self.routes.get((method, path), (404, {"error": f"no route {method} {path}"}))
        if isinstance(entry, list):
            idx = self.route_hits.get((method, path), 0)
            status, payload = entry[min(idx, len(entry) - 1)]
            self.route_hits[(method, path)] = idx + 1
        else:
            status, payload = entry
        data = (
            json.dumps(payload).encode("utf-8")
            if not isinstance(payload, str)
            else payload.encode("utf-8")
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

@pytest.fixture
def tf_server():
    _Router.routes = {}
    _Router.route_hits = {}
    _Router.received_bodies = []
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield host, port, _Router
    server.shutdown()
    server.server_close()
    _Router.routes = {}
    _Router.route_hits = {}
    _Router.received_bodies = []


def _paused_routes() -> dict[tuple[str, str], Any]:
    """Create-session → paused ask turn → resumed done turn."""
    return {
        ("POST", "/api/v1/sessions"): (200, {"data": {"id": "sess-q-1"}}),
        ("POST", "/api/v1/sessions/sess-q-1/turns"): [
            (200, {"data": {"id": "turn-q-1", "state": "RUNNING"}}),
            (200, {"data": {"id": "turn-q-2", "state": "RUNNING"}}),
        ],
        ("GET", "/api/v1/sessions/sess-q-1/turns/turn-q-1"): (
            200,
            {"data": {"id": "turn-q-1", **_paused_ask_turn()}},
        ),
        ("GET", "/api/v1/sessions/sess-q-1/turns/turn-q-1/events"): (
            200,
            {"data": _ask_events()},
        ),
        ("GET", "/api/v1/sessions/sess-q-1/turns/turn-q-2"): (
            200,
            {"data": {"id": "turn-q-2", "state": "done"}},
        ),
        ("GET", "/api/v1/sessions/sess-q-1/turns/turn-q-2/events"): (
            200,
            {
                "data": [
                    {
                        "type": "model.message",
                        "content": "All done — I built it.",
                        "thread_id": "main",
                    }
                ]
            },
        ),
    }


def _paused_ask_turn(
    *,
    action_id: str = "01m3dwq1a5k22k6m9j6a72j359",
    tool_call_id: str = "chatcmpl-tool-adca5f7da2b141bd",
    thread_id: str = "main",
) -> dict[str, Any]:
    return {
        "state": {
            "status": "done",
            "output": None,
            "required_actions": [
                {
                    "id": action_id,
                    "type": "tool.response_required",
                    "thread_id": thread_id,
                    "tool_calls": [{"id": tool_call_id, "source_event_id": "evt-1"}],
                }
            ],
            "completed_at": "2026-09-26T03:39:03.366Z",
        }
    }


def _ask_events() -> list[Any]:
    tool_call_id = "chatcmpl-tool-adca5f7da2b141bd"
    return [
        {"type": "turn.created", "state": {"status": "running"}},
        {
            "id": "evt-1",
            "type": "model.message",
            "content": "Let me make sure I point my effort in the right direction.",
            "thread_id": "main",
            "tool_calls": [
                {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": "ask_user_question",
                        "arguments": json.dumps(
                            {
                                "question": "What would you like me to dig into?",
                                "options": [
                                    "Give me a tour",
                                    "Build something",
                                    "Something else",
                                ],
                            }
                        ),
                    },
                }
            ],
        },
        {
            "id": "tool-evt",
            "type": "tool.response_required",
            "thread_id": "main",
            "tool_calls": [{"id": tool_call_id, "source_event_id": "evt-1"}],
        },
    ]


def _cfg(host: str, port: int) -> dict[str, Any]:
    return {
        "agent_team": {"members": ["trueforge"]},
        "remotes": {
            "trueforge": {
                "base_url": f"http://{host}:{port}",
                "agent": "orchestrator",
            }
        },
    }


def _final(chunks: list[Any]) -> str | None:
    for chunk in chunks:
        msgs = chunk.get("messages") if isinstance(chunk, dict) else None
        if msgs and msgs[0].get("content"):
            return str(msgs[0]["content"])
    return None


def _tool_response_bodies(router) -> list[Any]:
    return [
        body
        for method, _path, body in router.received_bodies
        if method == "POST"
        and isinstance(body, dict)
        and isinstance(body.get("input"), list)
        and body["input"]
        and isinstance(body["input"][0], dict)
        and body["input"][0].get("type") == "user.tool_response"
    ]


# ---------------------------------------------------------------------------
# Capability gate
# ---------------------------------------------------------------------------


def test_only_capable_remotes_advertise_elicit_questions():
    assert remote_ask_user_enabled("trueforge") is True
    assert remote_ask_user_enabled("trueforge_secondary") is True
    assert remote_ask_user_enabled("hermes") is False
    assert remote_ask_user_enabled("") is False


def test_install_bridge_gates_on_capability():
    class _Bp:
        pass

    capable = _Bp()
    assert install_remote_ask_user_bridge(
        capable, remote_id="trueforge", elicit_fn="cb"
    ) is True
    assert getattr(capable, REMOTE_ASK_USER_BRIDGE_ATTR) == "cb"

    incapable = _Bp()
    assert install_remote_ask_user_bridge(
        incapable, remote_id="hermes", elicit_fn="cb"
    ) is False
    assert not hasattr(incapable, REMOTE_ASK_USER_BRIDGE_ATTR)

    assert install_remote_ask_user_bridge(
        _Bp(), remote_id="trueforge", elicit_fn=None
    ) is False


def test_consumer_gate_matches_capability():
    from swarm.consumers import DjangoChatConsumer

    fake = types.SimpleNamespace(elicit_user_question="cb")
    assert DjangoChatConsumer._remote_ask_user_bridge(fake, {"remote": "trueforge"}) == "cb"
    assert DjangoChatConsumer._remote_ask_user_bridge(fake, {"name": "trueforge"}) == "cb"
    assert DjangoChatConsumer._remote_ask_user_bridge(fake, {"remote": "hermes"}) is None
    assert DjangoChatConsumer._remote_ask_user_bridge(fake, None) is None


# ---------------------------------------------------------------------------
# Adapter-level resume: the exact wire body
# ---------------------------------------------------------------------------


def test_trueforge_adapter_resume_posts_user_tool_response_body(tf_server, monkeypatch):
    host, port, router = tf_server
    router.routes = _paused_routes()
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = _cfg(host, port)

    paused = remotes_core.operate("trueforge", "send", prompt="interesting", config=cfg)
    assert paused.ok is True
    assert paused.data["awaiting_input"] is True

    spec = remotes_core.load_remote("trueforge", cfg)
    adapter = create_remote_adapter(spec)
    assert adapter is not None
    pending = adapter.pending_question(paused)
    assert pending is not None
    assert pending["question"]["ask"] == "What would you like me to dig into?"
    assert pending["question"]["choices"] == [
        "Give me a tour",
        "Build something",
        "Something else",
    ]

    resumed = adapter.resume_with_answer(
        paused.data["session_id"],
        pending["pending_action"],
        "Build something",
        180.0,
    )
    assert resumed.ok is True
    assert resumed.detail == "All done — I built it."
    assert _tool_response_bodies(router) == [
        {
            "input": [
                {
                    "type": "user.tool_response",
                    "thread_id": "main",
                    "tool_call_id": "chatcmpl-tool-adca5f7da2b141bd",
                    "content": "Build something",
                }
            ],
            "stream": False,
            "previous_turn_id": "turn-q-1",
        }
    ]


# ---------------------------------------------------------------------------
# Blueprint end-to-end: pause → elicit → resume → final answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_blueprint_elicits_and_resumes_paused_remote_turn(tf_server, monkeypatch):
    host, port, router = tf_server
    router.routes = _paused_routes()
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = _cfg(host, port)
    monkeypatch.setattr(remotes_core, "load_raw_config", lambda *_args, **_kwargs: (cfg, None))

    bp = RemoteHarnessBlueprint(config=cfg)
    bp.set_params({"op": "send", "name": "trueforge", "prompt": "do the thing"})

    asked: list[dict[str, Any]] = []

    async def bridge(question: dict[str, Any]) -> str:
        asked.append(question)
        return "Build something"

    setattr(bp, REMOTE_ASK_USER_BRIDGE_ATTR, bridge)

    chunks = [chunk async for chunk in bp.run([{"role": "user", "content": ""}])]
    assert _final(chunks) == "All done — I built it."

    assert asked and asked[0]["ask"] == "What would you like me to dig into?"
    assert asked[0]["choices"] == ["Give me a tour", "Build something", "Something else"]
    assert _tool_response_bodies(router) and (
        _tool_response_bodies(router)[0]["input"][0]["content"] == "Build something"
    )


@pytest.mark.asyncio
async def test_blueprint_without_bridge_returns_lead_in_without_hanging(
    tf_server, monkeypatch
):
    """No bridge → the pause renders honestly; never blocks on a future."""
    import asyncio

    host, port, router = tf_server
    router.routes = _paused_routes()
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    cfg = _cfg(host, port)
    monkeypatch.setattr(remotes_core, "load_raw_config", lambda *_args, **_kwargs: (cfg, None))

    bp = RemoteHarnessBlueprint(config=cfg)
    bp.set_params({"op": "send", "name": "trueforge", "prompt": "do the thing"})

    chunks = await asyncio.wait_for(
        _collect(bp.run([{"role": "user", "content": ""}])), timeout=10
    )
    body = _final(chunks) or ""
    # The lead-in and the pending question surface; nothing is fabricated.
    assert "What would you like me to dig into?" in body
    # No question was answered, so the tool response was never POSTed.
    assert _tool_response_bodies(router) == []
    turn_posts = [
        body
        for method, path, body in router.received_bodies
        if method == "POST" and path.endswith("/turns")
    ]
    assert len(turn_posts) == 1


async def _collect(gen):
    return [chunk async for chunk in gen]


# ---------------------------------------------------------------------------
# Generic convention helper
# ---------------------------------------------------------------------------


def test_pending_question_from_result_reads_shared_convention():
    result = remotes_core.OperateResult(
        remote="trueforge",
        op="send",
        ok=True,
        detail="lead-in",
        data={
            "session_id": "sess-1",
            "awaiting_input": True,
            "pending_question": {"id": "q", "ask": "Where?", "choices": ["a"], "other": "Other"},
            "pending_action": {"tool_call_id": "tc-1", "thread_id": "main", "previous_turn_id": "t-1"},
        },
    )
    pending = pending_question_from_result(result)
    assert pending is not None
    assert pending["session_id"] == "sess-1"
    assert pending["question"]["ask"] == "Where?"
    assert pending["pending_action"]["tool_call_id"] == "tc-1"

    assert pending_question_from_result(
        remotes_core.OperateResult(remote="x", op="send", ok=True, detail="done")
    ) is None

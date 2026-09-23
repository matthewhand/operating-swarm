"""Issue #125 — OpenMousBot follow-up bot texts after the first polled reply."""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from queue import Queue

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate
from swarm.core import chat_store, omb_session_watch, remotes as remotes_core
from swarm.core.omb_session_watch import (
    OmbSessionMonitor,
    followup_from_sse,
    parse_sse_block,
)


@pytest.fixture(autouse=True)
def _reset_omb_watch(monkeypatch):
    omb_session_watch.reset_monitor_for_tests()
    monkeypatch.setattr(remotes_core, "_OMB_REPLY_TIMEOUT_S", 0.4)
    monkeypatch.setattr(remotes_core, "_OMB_POLL_INTERVAL_S", 0.01)
    monkeypatch.setattr(omb_session_watch, "QUIET_IDLE_SECONDS", 2.0)
    monkeypatch.setattr(omb_session_watch, "POLL_FALLBACK_SECONDS", 0.05)
    yield
    omb_session_watch.reset_monitor_for_tests()


def _bot_text(msg_id: str, text: str, **extra) -> dict:
    row = {
        "id": msg_id,
        "role": "bot",
        "kind": "text",
        "text": text,
    }
    row.update(extra)
    return row


def _sse_message(thread_id: str, msg: dict) -> dict:
    return {"kind": "message", "threadId": thread_id, "message": msg, "seq": 1}


def test_parse_sse_block_json_data_and_comments():
    block = 'id: ab:12\n: keepalive\ndata: {"kind":"message","threadId":"th-1"}\n'
    parsed = parse_sse_block(block)
    assert parsed == {"kind": "message", "threadId": "th-1"}
    assert parse_sse_block(": keepalive\n") is None
    assert parse_sse_block('data: {"kind":"ping"}')["kind"] == "ping"


def test_followup_from_sse_skips_first_reply_and_non_bot():
    a = _bot_text("a1", "alpha")
    b = _bot_text("b1", "bravo")
    seen = {"u1", "a1"}
    assert followup_from_sse(_sse_message("th-1", a), thread_id="th-1", seen_ids=seen) is None
    got = followup_from_sse(_sse_message("th-1", b), thread_id="th-1", seen_ids=seen)
    assert got == {"id": "b1", "text": "bravo"}
    assert (
        followup_from_sse(_sse_message("other", b), thread_id="th-1", seen_ids=seen) is None
    )
    user = {"id": "u2", "role": "user", "kind": "text", "text": "hi"}
    assert followup_from_sse(_sse_message("th-1", user), thread_id="th-1", seen_ids=seen) is None
    activity = {"id": "x", "role": "bot", "kind": "activity", "text": "working"}
    assert followup_from_sse(_sse_message("th-1", activity), thread_id="th-1", seen_ids=seen) is None


def _seed_transcript(user_key="u1", agent_id="omb", conversation_id="c1"):
    chat_store.save(
        user_key,
        agent_id,
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "alpha"},
        ],
        conversation_id=conversation_id,
        session_id=conversation_id,
    )
    return conversation_id


def test_ingest_b_and_c_appends_assistant_turns(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    sid = _seed_transcript()
    monitor = OmbSessionMonitor()
    track = monitor.watch_thread(
        user_key="u1",
        agent_id="omb",
        conversation_id="c1",
        spec=remotes_core.RemoteSpec(
            id="omb",
            title="OpenMousBot",
            host_label="test",
            base_url="http://127.0.0.1:9",
        ),
        bot_id="bot-9",
        thread_id="th-1",
        seen_ids={"u1", "a1"},
        start_worker=False,
    )
    assert track is not None
    monitor.ingest_sse(_sse_message("th-1", _bot_text("b1", "bravo")))
    monitor.ingest_sse(_sse_message("th-1", _bot_text("c1", "charlie")))
    monitor.ingest_sse(_sse_message("th-1", _bot_text("b1", "bravo")))  # dedup
    record = chat_store.load("u1", "omb", conversation_id="c1", session_id=sid)
    texts = [m.get("content") for m in (record or {}).get("messages") or []]
    assert texts == ["hello", "alpha", "bravo", "charlie"]
    blob = json.dumps(record)
    assert "accepted the turn" not in blob
    assert "79b5852c" not in blob


def test_first_only_poll_is_not_enough_for_b_and_c(http_router_factory, tmp_path, monkeypatch):
    """Operate returns A; B and C arrive later on SSE and must land in the store."""
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    host, port, ctrl = http_router_factory()
    user = {"id": "u1", "role": "user", "kind": "text", "text": "hello"}
    a = _bot_text("a1", "alpha", turnTerminal=True)
    state = {"n": 0}

    def bots():
        state["n"] += 1
        return 200, {
            "bots": [
                {
                    "id": "bot-9",
                    "name": "waveshare",
                    "threadId": "th-1",
                    "busy": False,
                    "activity": "idle",
                    "messages": [user, a],
                }
            ]
        }

    def thread_msgs():
        return 200, {"messages": [user, a]}

    ctrl.routes = {
        ("GET", "/api/bots"): bots,
        ("GET", "/api/threads/th-1/messages"): thread_msgs,
        ("POST", "/api/bots/bot-9/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1", "role": "user", "text": "hello"}},
        ),
    }
    cfg = {
        "llm": {},
        "remotes": {"omb": {"base_url": f"http://{host}:{port}", "api_key": "omb-secret"}},
    }
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target="bot-9", config=cfg
    )
    assert sent.ok is True
    assert sent.data["text"] == "alpha"
    assert sent.data["message_id"] == "a1"
    assert sent.data["thread_id"] == "th-1"
    blob = json.dumps(sent.as_dict())
    assert "accepted the turn" not in blob
    assert "OpenMousBot accepted" not in sent.detail
    rendered = _render_operate(sent)
    assert rendered == "alpha"
    assert "bot-9" not in rendered

    sid = _seed_transcript()
    spec = remotes_core.load_remote("omb", cfg)
    monitor = OmbSessionMonitor()
    monitor.watch_thread(
        user_key="u1",
        agent_id="omb",
        conversation_id="c1",
        spec=spec,
        bot_id="bot-9",
        thread_id="th-1",
        seen_ids={"u1", sent.data["message_id"]},
        start_worker=False,
    )
    monitor.ingest_sse(_sse_message("th-1", _bot_text("b1", "bravo")))
    monitor.ingest_sse(_sse_message("th-1", _bot_text("c1", "charlie")))
    record = chat_store.load("u1", "omb", conversation_id="c1", session_id=sid)
    texts = [m.get("content") for m in (record or {}).get("messages") or []]
    assert texts == ["hello", "alpha", "bravo", "charlie"]


def test_sse_subscribe_delivers_followups(tmp_path, monkeypatch):
    monkeypatch.setenv("SWARM_CHAT_DIR", str(tmp_path))
    extra = [
        _sse_message("th-1", _bot_text("b1", "bravo")),
        _sse_message("th-1", _bot_text("c1", "charlie")),
    ]
    release = threading.Event()
    hold = threading.Event()

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            path = self.path.split("?", 1)[0]
            if path == "/api/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                hello = json.dumps({"kind": "hello", "cursor": "s:0", "resumed": False})
                self.wfile.write(f"data: {hello}\n\n".encode())
                self.wfile.flush()
                hold.set()
                release.wait(2)
                for i, payload in enumerate(extra, start=1):
                    frame = f"id: s:{i}\ndata: {json.dumps(payload)}\n\n"
                    self.wfile.write(frame.encode())
                    self.wfile.flush()
                time.sleep(0.4)
                return
            if path == "/api/threads/th-1/messages":
                body = {
                    "messages": [
                        {"id": "u1", "role": "user", "kind": "text", "text": "hello"},
                        _bot_text("a1", "alpha", turnTerminal=True),
                    ]
                }
                raw = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *args) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    monitor = OmbSessionMonitor()
    try:
        sid = _seed_transcript()
        spec = remotes_core.RemoteSpec(
            id="omb",
            title="OpenMousBot",
            host_label="test",
            base_url=f"http://{host}:{port}",
            api_key="omb-secret",
        )
        monitor.watch_thread(
            user_key="u1",
            agent_id="omb",
            conversation_id="c1",
            spec=spec,
            bot_id="bot-9",
            thread_id="th-1",
            seen_ids={"u1", "a1"},
        )
        assert hold.wait(2)
        release.set()
        deadline = time.monotonic() + 3
        texts: list[str] = []
        while time.monotonic() < deadline:
            record = chat_store.load("u1", "omb", conversation_id="c1", session_id=sid)
            texts = [m.get("content") for m in (record or {}).get("messages") or []]
            if texts == ["hello", "alpha", "bravo", "charlie"]:
                break
            time.sleep(0.05)
        assert texts == ["hello", "alpha", "bravo", "charlie"]
    finally:
        release.set()
        monitor.close()
        server.shutdown()
        omb_session_watch.reset_monitor_for_tests()


def test_unwatch_and_quiet_window_drop_track():
    monitor = OmbSessionMonitor()
    spec = remotes_core.RemoteSpec(
        id="omb", title="OpenMousBot", host_label="t", base_url="http://127.0.0.1:9"
    )
    monitor.watch_thread(
        user_key="u1",
        agent_id="omb",
        conversation_id="c1",
        spec=spec,
        bot_id="bot-9",
        thread_id="th-1",
        seen_ids={"a1"},
        start_worker=False,
    )
    assert monitor.track_count() == 1
    monitor.unwatch_conversation("u1", "c1")
    assert monitor.track_count() == 0

    monitor.watch_thread(
        user_key="u1",
        agent_id="omb",
        conversation_id="c1",
        spec=spec,
        bot_id="bot-9",
        thread_id="th-1",
        seen_ids={"a1"},
        start_worker=False,
    )
    track = next(iter(monitor.tracks()))
    track.last_change = time.monotonic() - 120
    monitor.prune_idle()
    assert monitor.track_count() == 0


def test_publish_queues_followup_for_live_consumer():
    monitor = OmbSessionMonitor()
    spec = remotes_core.RemoteSpec(
        id="omb", title="OpenMousBot", host_label="t", base_url="http://127.0.0.1:9"
    )
    q: Queue = Queue()
    monitor.register_consumer("u1", q)
    monitor.watch_thread(
        user_key="u1",
        agent_id="omb",
        conversation_id="c1",
        spec=spec,
        bot_id="bot-9",
        thread_id="th-1",
        seen_ids={"a1"},
        start_worker=False,
    )
    monitor.ingest_sse(_sse_message("th-1", _bot_text("b1", "bravo")))
    payload = q.get_nowait()
    assert payload["type"] == "omb_followup"
    assert payload["text"] == "bravo"
    assert payload["conversation_id"] == "c1"


def test_poll_timeout_is_named_error_not_uuid_ack(http_router_factory):
    host, port, ctrl = http_router_factory()
    ctrl.routes = {
        ("GET", "/api/bots"): (
            200,
            {
                "bots": [
                    {
                        "id": "bot-9",
                        "name": "waveshare",
                        "threadId": "th-1",
                        "busy": True,
                        "activity": "working",
                        "messages": [
                            {"id": "u1", "role": "user", "kind": "text", "text": "hello"},
                        ],
                    }
                ]
            },
        ),
        ("GET", "/api/threads/th-1/messages"): (
            200,
            {"messages": [{"id": "u1", "role": "user", "kind": "text", "text": "hello"}]},
        ),
        ("POST", "/api/bots/bot-9/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1"}},
        ),
    }
    cfg = {
        "llm": {},
        "remotes": {"omb": {"base_url": f"http://{host}:{port}", "api_key": "omb-secret"}},
    }
    sent = remotes_core.operate("omb", "send", prompt="hello", target="bot-9", config=cfg)
    assert sent.ok is False
    assert "timed out" in sent.detail
    assert "accepted the turn" not in sent.detail
    assert "accepted the turn" not in json.dumps(sent.as_dict())


@pytest.fixture
def http_router_factory():
    """JSON router used by remotes operate tests (no SSE)."""

    class _Router(BaseHTTPRequestHandler):
        routes: dict = {}
        posted: list = []

        def _handle(self, method: str) -> None:
            key = (method, self.path.split("?", 1)[0])
            if method == "POST":
                try:
                    length = int(self.headers.get("Content-Length") or 0)
                except ValueError:
                    length = 0
                raw = self.rfile.read(length) if length else b""
                type(self).posted.append((key[1], raw.decode("utf-8", "replace")))
            status_body = type(self).routes.get(key, (404, {"error": "no route"}))
            if callable(status_body):
                status_body = status_body()
            status, body = status_body
            payload = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload)

        def do_GET(self) -> None:  # noqa: N802
            self._handle("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._handle("POST")

        def log_message(self, *args) -> None:
            pass

    servers: list[HTTPServer] = []

    def factory():
        _Router.routes = {}
        _Router.posted = []
        server = HTTPServer(("127.0.0.1", 0), _Router)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        servers.append(server)
        return "127.0.0.1", server.server_address[1], _Router

    yield factory
    for server in servers:
        server.shutdown()

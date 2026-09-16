"""Issue #301 — OpenMousBot send polls for the real reply after HTTP 202."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import _render_operate
from swarm.core import remotes as remotes_core

WAVESHARE_ID = "79b5852c-9ae8-4972-a662-80054be9ea5f"
_ACK = "accepted the turn"


def _fast_poll(monkeypatch) -> None:
    monkeypatch.setattr(remotes_core, "_OMB_REPLY_TIMEOUT_S", 0.35)
    monkeypatch.setattr(remotes_core, "_OMB_POLL_INTERVAL_S", 0.01)


def _cfg(host: str, port: int) -> dict:
    return {
        "llm": {},
        "remotes": {"omb": {"base_url": f"http://{host}:{port}", "api_key": "omb-secret"}},
    }


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


@pytest.fixture
def omb_http():
    _Router.routes = {}
    _Router.posted = []
    server = HTTPServer(("127.0.0.1", 0), _Router)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "127.0.0.1", server.server_address[1], _Router
    server.shutdown()
    _Router.routes = {}
    _Router.posted = []


def test_req301_202_then_assistant_text_is_the_chat_reply(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    user = {"id": "u1", "role": "user", "kind": "text", "text": "hello"}
    reply = {
        "id": "a1",
        "role": "bot",
        "kind": "text",
        "text": "waveshare first reply",
        "turnTerminal": True,
    }
    bot = {
        "id": WAVESHARE_ID,
        "name": "waveshare",
        "threadId": "th-1",
        "busy": False,
        "activity": "waiting-on-you",
        "messages": [user, reply],
    }
    router.routes = {
        ("GET", "/api/bots"): (200, {"bots": [bot]}),
        ("POST", f"/api/bots/{WAVESHARE_ID}/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1", "role": "user", "text": "hello"}},
        ),
        ("GET", "/api/threads/th-1/messages"): (200, {"messages": [user, reply]}),
        ("POST", "/api/bots"): (500, {"error": "do not mint"}),
    }
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=WAVESHARE_ID, config=_cfg(host, port)
    )
    assert sent.ok is True
    assert sent.http_status == 202
    assert sent.data["text"] == "waveshare first reply"
    assert sent.data["bot_id"] == WAVESHARE_ID
    blob = json.dumps(sent.as_dict())
    assert _ACK not in blob
    rendered = _render_operate(sent)
    assert rendered == "waveshare first reply"
    assert WAVESHARE_ID not in rendered
    assert _ACK not in rendered


def test_req301_delayed_reply_is_waited_for(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    user = {"id": "u1", "role": "user", "kind": "text", "text": "hello"}
    reply = {
        "id": "a1",
        "role": "bot",
        "kind": "text",
        "text": "arrived after poll",
        "turnTerminal": True,
    }
    state = {"n": 0}

    def thread_msgs():
        state["n"] += 1
        if state["n"] < 3:
            return 200, {"messages": [user]}
        return 200, {"messages": [user, reply]}

    def bots():
        messages = [user, reply] if state["n"] >= 3 else [user]
        return 200, {
            "bots": [
                {
                    "id": WAVESHARE_ID,
                    "name": "waveshare",
                    "threadId": "th-1",
                    "busy": state["n"] < 3,
                    "activity": "working" if state["n"] < 3 else "waiting-on-you",
                    "messages": messages,
                }
            ]
        }

    router.routes = {
        ("GET", "/api/bots"): bots,
        ("GET", "/api/threads/th-1/messages"): thread_msgs,
        ("POST", f"/api/bots/{WAVESHARE_ID}/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1"}},
        ),
        ("POST", "/api/bots"): (500, {"error": "do not mint"}),
    }
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=WAVESHARE_ID, config=_cfg(host, port)
    )
    assert sent.ok is True
    assert sent.data["text"] == "arrived after poll"
    assert _render_operate(sent) == "arrived after poll"


def test_req301_timeout_is_named_error_not_uuid_ack(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    router.routes = {
        ("GET", "/api/bots"): (
            200,
            {
                "bots": [
                    {
                        "id": WAVESHARE_ID,
                        "name": "waveshare",
                        "threadId": "th-1",
                        "busy": True,
                        "activity": "working",
                        "messages": [{"id": "u1", "role": "user", "kind": "text", "text": "hello"}],
                    }
                ]
            },
        ),
        ("GET", "/api/threads/th-1/messages"): (
            200,
            {"messages": [{"id": "u1", "role": "user", "kind": "text", "text": "hello"}]},
        ),
        ("POST", f"/api/bots/{WAVESHARE_ID}/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1"}},
        ),
        ("POST", "/api/bots"): (500, {"error": "do not mint"}),
    }
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=WAVESHARE_ID, config=_cfg(host, port)
    )
    assert sent.ok is False
    assert "timed out" in sent.detail
    assert _ACK not in sent.detail
    blob = json.dumps(sent.as_dict())
    assert _ACK not in blob
    rendered = _render_operate(sent)
    assert "timed out" in rendered
    assert _ACK not in rendered
    assert WAVESHARE_ID not in rendered


def test_req301_waveshare_target_id_is_not_replaced_by_minted_bot(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    user = {"id": "u1", "role": "user", "kind": "text", "text": "hello"}
    reply = {
        "id": "a1",
        "role": "bot",
        "kind": "text",
        "text": "stay on waveshare",
        "turnTerminal": True,
    }
    router.routes = {
        ("GET", "/api/bots"): (
            200,
            {
                "bots": [
                    {
                        "id": WAVESHARE_ID,
                        "name": "waveshare",
                        "threadId": "th-1",
                        "busy": False,
                        "activity": "waiting-on-you",
                        "messages": [user, reply],
                    }
                ]
            },
        ),
        ("POST", f"/api/bots/{WAVESHARE_ID}/messages"): (
            202,
            {"ok": True, "threadId": "th-1", "message": {"id": "u1"}},
        ),
        ("GET", "/api/threads/th-1/messages"): (200, {"messages": [user, reply]}),
        ("POST", "/api/bots"): (201, {"bot": {"id": "open-swarm", "name": "open-swarm"}}),
    }
    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=WAVESHARE_ID, config=_cfg(host, port)
    )
    assert sent.ok is True
    assert sent.data["bot_id"] == WAVESHARE_ID
    assert sent.data["bot_id"] != "open-swarm"
    create_posts = [path for path, _ in router.posted if path.rstrip("/") == "/api/bots"]
    assert create_posts == []
    message_posts = [path for path, _ in router.posted if path == f"/api/bots/{WAVESHARE_ID}/messages"]
    assert message_posts
    assert "open-swarm" not in json.dumps(sent.as_dict())

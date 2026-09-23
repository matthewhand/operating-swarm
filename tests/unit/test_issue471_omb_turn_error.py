"""Issue #471 — an OMB turn that fails on the remote must name its cause.

Observed live: the bot's turn ended with a non-text activity row

    {"role": "bot", "kind": "activity",
     "tool": {"name": "error: Internal error", "ok": false}}

while `operate(send)` polled for the full budget and reported
`OpenMousBot reply timed out`. The cause was on the thread the whole time.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remotes import OMB_TURN_ERROR_PREFIX, _omb_turn_error

BOT_ID = "3c2ffac9-7797-484b-8628-1679350c90a1"
REMOTES_SRC = Path(remotes_core.__file__)


def _user_row() -> dict:
    return {"id": "u1", "role": "user", "kind": "text", "text": "hello"}


def _error_row(name: str = "error: Internal error") -> dict:
    return {"id": "b-err", "role": "bot", "kind": "activity", "tool": {"name": name, "ok": False}}


def _reply_row(text: str = "ok then") -> dict:
    return {"id": "a1", "role": "bot", "kind": "text", "text": text, "turnTerminal": True}


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

    def _handle(self, method: str) -> None:
        key = (method, self.path.split("?", 1)[0])
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
    server = HTTPServer(("127.0.0.1", 0), _Router)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "127.0.0.1", server.server_address[1], _Router
    server.shutdown()
    _Router.routes = {}


def _routes(router, rows) -> None:
    bot = {
        "id": BOT_ID,
        "name": "hide-qa-alpha",
        "threadId": "th-471",
        "busy": False,
        "activity": "waiting-on-you",
        "messages": rows,
    }
    router.routes = {
        ("GET", "/api/bots"): (200, {"bots": [bot]}),
        ("GET", "/api/threads/th-471/messages"): (200, {"messages": rows}),
        ("POST", f"/api/bots/{BOT_ID}/messages"): (
            202,
            {"ok": True, "threadId": "th-471", "message": {"id": "u1", "role": "user"}},
        ),
        ("POST", "/api/bots"): (500, {"error": "do not mint"}),
    }


def test_issue471_remote_error_is_named_instead_of_timing_out(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    _routes(router, [_user_row(), _error_row()])

    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=BOT_ID, config=_cfg(host, port)
    )

    assert sent.ok is False
    assert "Internal error" in sent.detail
    assert "timed out" not in sent.detail.lower()
    assert sent.gap == "omb_turn_error"
    blob = json.dumps(sent.as_dict())
    assert "omb_reply_timeout" not in blob


def test_issue471_previous_turn_error_is_not_attributed_to_this_one(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    _routes(router, [_error_row("error: Previous failure"), _user_row()])

    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=BOT_ID, config=_cfg(host, port)
    )

    assert sent.ok is False
    # Not this turn's failure: the settled no-reply path reports the honest
    # "waiting for operator input" instead of adopting the old error row.
    assert sent.gap != "omb_turn_error"
    assert "Previous failure" not in sent.detail


def test_issue471_a_real_reply_still_wins_over_an_error_row(omb_http, monkeypatch):
    host, port, router = omb_http
    _fast_poll(monkeypatch)
    _routes(router, [_user_row(), _error_row(), _reply_row("recovered answer")])

    sent = remotes_core.operate(
        "omb", "send", prompt="hello", target=BOT_ID, config=_cfg(host, port)
    )

    assert sent.ok is True
    assert sent.data["text"] == "recovered answer"


def test_issue471_turn_error_helper_shapes():
    assert _omb_turn_error([_user_row(), _error_row()], after_id="u1") == "Internal error"
    # Named without the "error:" prefix.
    assert _omb_turn_error([_user_row(), _error_row("timeout")], after_id="u1") == "timeout"
    # Successful activity rows and plain text are not failures.
    assert _omb_turn_error([_user_row()], after_id="u1") == ""
    assert (
        _omb_turn_error(
            [_user_row(), {"id": "b2", "role": "bot", "kind": "activity", "tool": {"name": "read_file", "ok": True}}],
            after_id="u1",
        )
        == ""
    )
    # Newest failure wins; history before the turn is ignored.
    assert (
        _omb_turn_error([_user_row(), _error_row("first"), _error_row("second")], after_id="u1")
        == "second"
    )
    assert _omb_turn_error([_error_row("old"), _user_row()], after_id="u1") == ""
    assert OMB_TURN_ERROR_PREFIX.startswith("OpenMousBot turn failed")


def test_issue471_the_single_omb_poll_loop_consults_the_helper():
    """The OMB poll loop must consult the turn-error helper.

    This began as ``>= 2``: when #471 was fixed the poll loop was duplicated in
    remotes.py, so a fix applied to one copy was a no-op. #475/#477 deleted the
    duplicated block, leaving exactly one loop — and a ``>= 2`` assertion would
    now demand the duplication the dedupe exists to remove. Pin the single call
    site instead, so re-introducing a second copy fails here too.
    """
    # #812 slice 5: the poll loop moved verbatim into remote_impls/omb.py;
    # counting across both files keeps the exactly-one-call-site doctrine.
    text = "\n".join(
        (
            REMOTES_SRC.read_text(encoding="utf-8"),
            (REMOTES_SRC.parent / "remote_impls" / "omb.py").read_text(encoding="utf-8"),
        )
    )
    assert text.count("_omb_turn_error(messages, after_id=after_id, prompt=prompt)") == 1
    assert text.count("if turn_error:") == 1

"""#1191 — nested-swarm chat handoff survives a keyless CSRF-enforcing child.

Bearer-with-valid-token keeps working; without a token, the adapter performs
the browser-equivalent CSRF dance (GET / → csrftoken cookie → POST with
cookie + X-CSRFToken + Referer) and retries once. A dance that still fails
surfaces the child's answer honestly.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.core import remotes as R
from swarm.core.remote_impls import swarm_kind


class _Child(BaseHTTPRequestHandler):
    """open-swarm child: GET endpoints open, POST /v1/chat/completions CSRF-guarded."""

    server_version = "child-swarm"

    def _json(self, status: int, body: dict | list) -> None:
        payload = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/health":
            self._json(200, {"status": "ok"})
        elif path == "/v1/blueprints/" or path == "/v1/blueprints":
            self._json(
                200,
                {"object": "list", "data": [{"id": "support", "object": "blueprint"}]},
            )
        elif path == "/":
            token = "dance-token-123"
            self.send_response(200)
            self.send_header("Set-Cookie", f"csrftoken={token}; Path=/")
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html></html>")
        else:
            self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path not in ("/v1/chat/completions/", "/v1/chat/completions"):
            self._json(404, {"detail": "not found"})
            return
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            self._json(
                200,
                {
                    "id": "chatcmpl-x",
                    "choices": [{"message": {"role": "assistant", "content": "BEARER-OK"}}],
                },
            )
            return
        token = self.headers.get("X-CSRFToken", "")
        cookie = self.headers.get("Cookie", "")
        referer = self.headers.get("Referer", "")
        if token == "dance-token-123" and "csrftoken=dance-token-123" in cookie and referer:
            self._json(
                200,
                {
                    "id": "chatcmpl-d",
                    "choices": [{"message": {"role": "assistant", "content": "DANCE-OK"}}],
                },
            )
            return
        self._json(403, {"detail": "CSRF Failed: CSRF cookie not set."})

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def child_server():
    server = HTTPServer(("127.0.0.1", 0), _Child)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    yield f"http://{host}:{port}"
    server.shutdown()


def _spec(base: str, *, api_key: str = "") -> R.RemoteSpec:
    return R.RemoteSpec(
        id="child-swarm",
        title="Child",
        host_label="remote-swarm",
        base_url=base,
        api_key=api_key,
        kind="swarm",
    )


def test_bearer_send_unchanged(child_server):
    """A token-bearing spec POSTs directly — no dance, no cookie jar."""
    result = swarm_kind._swarm_send(
        _spec(child_server, api_key="shared-secret"), "hi", target="support", timeout=5
    )
    assert result.ok is True, result.detail
    assert "BEARER-OK" in json.dumps(result.data.get("response"))


def test_keyless_send_performs_csrf_dance(child_server):
    result = swarm_kind._swarm_send(_spec(child_server), "hi", target="support", timeout=8)
    assert result.ok is True, result.detail
    text = result.data.get("response") or ""
    assert "DANCE-OK" in json.dumps(text)


def test_keyless_send_auto_picks_first_blueprint(child_server):
    result = swarm_kind._swarm_send(_spec(child_server), "hi", target="", timeout=8)
    assert result.ok is True, result.detail
    assert result.data.get("model") == "support"


def test_dance_failure_surfaces_child_answer(child_server, monkeypatch):
    def broken_dance(*_a, **_k):
        return R.HttpResult(status=403, body={"detail": "CSRF Failed: CSRF cookie not set."}, text="{}")

    monkeypatch.setattr(swarm_kind, "_swarm_csrf_dance_post", broken_dance)
    result = swarm_kind._swarm_send(_spec(child_server), "hi", target="support", timeout=8)
    assert result.ok is False
    assert "CSRF" in result.detail

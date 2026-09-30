"""#1187 — AnythingLLM sends resolve a session automatically when the caller
gives none, instead of demanding the user pass `session_id` by hand.

Resolution order (deterministic, honest):

1. The remote's wired ``agent`` (Settings → Remotes, the #1159 per-remote
   wiring) — a workspace slug or ``workspace:thread``. Wired beats auto.
2. The first workspace from GET /api/v1/workspaces (the list the UI would
   show the user) — main workspace chat, keyed by ``sessionId``.
3. No workspaces visible (or the gateway is down) → the original honest
   refusal, verbatim. Nothing is minted, ever.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.core import remotes as remotes_core
from tests.core.test_anythingllm_remote import _WORKSPACES, _cfg
from functools import partial


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], tuple[int, dict | list | str]] = {}
    #: Every ``(method, path)`` this fake actually *served*, in order.
    #:
    #: ``routes`` is the test's own routing table, so it can say nothing about
    #: what the impl under test did — the test authors the table, then asserts
    #: against it. ``served`` is the record of the requests that arrived. The
    #: "nothing is minted" claims below are only meaningful against this list.
    #: (Same idea as ``test_octop_remote``'s ``seen_auth``.)
    served: list[tuple[str, str]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        type(self).served.append((method, path))
        key = (method, path)
        status, body = self.routes.get(key, (404, {"error": "no route"}))
        payload = json.dumps(body).encode("utf-8") if not isinstance(body, str) else body.encode()
        self.send_response(status)
        ctype = "application/json"
        if isinstance(body, str) and body.lstrip().startswith("data:"):
            ctype = "text/event-stream"
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(payload)

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
def http_router():
    server = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    host, port = "127.0.0.1", server.server_address[1]
    _Router.served = []  # fresh request log per test
    yield host, port, _Router
    server.shutdown()
    server.server_close()
    _Router.routes = {}
    _Router.served = []


def test_send_without_session_auto_picks_first_workspace(http_router):
    """No session/target → the first workspace answers; nothing minted."""
    host, port, router = http_router
    router.routes = {
        ("GET", "/api/v1/workspaces"): (200, _WORKSPACES),
        ("POST", "/api/v1/workspace/teamstinky/stream-chat"): (
            200,
            "data: " + json.dumps({"textResponse": "PING-OK"}) + "\ndata: [DONE]\n",
        ),
    }
    result = remotes_core.operate(
        "anythingllm", "send", prompt="hi", config=_cfg(host, port)
    )
    assert result.ok is True, result.detail
    assert "TeamStinky" in result.detail
    assert result.data.get("response") == "PING-OK"
    # The chat landed in the workspace the list exposes — nothing minted.
    assert ("POST", "/api/v1/workspace/teamstinky/stream-chat") in router.routes

    # --- "nothing minted", asserted against what the impl actually sent ---
    #
    # The previous line here was
    #   assert not any("thread" in path for (_m, path) in router.routes ...) or True
    # `or` returns its first operand, so the trailing `True` made it
    # unconditionally true. It could not fail, and it could not have caught a
    # minted thread even without the `or`: `router.routes` is the routing table
    # this test itself wrote three lines above, so it never contained a thread
    # path in the first place. The claim was unfailable twice over.
    #
    # `_Router.served` is the log of requests that actually arrived, so these
    # fail the moment the resolve path starts addressing or creating a thread.
    served = list(_Router.served)
    assert served, "the impl made no HTTP request at all, so this proves nothing"

    # 1. The workspace came from the list the UI would show the user.
    assert ("GET", "/api/v1/workspaces") in served, (
        f"the auto-pick did not read the workspace list; served={served}"
    )

    # 2. The only mutating call is the stream-chat into the listed workspace.
    #    Anything else — a thread create, a session write — is a mint.
    writes = [(m, p) for (m, p) in served if m in ("POST", "PUT", "PATCH", "DELETE")]
    assert writes == [("POST", "/api/v1/workspace/teamstinky/stream-chat")], (
        f"unexpected mutating calls while resolving a session: {writes}"
    )

    # 3. No thread was addressed at all, and none of the thread slugs the
    #    list exposed was ever put in a URL.
    workspace_paths = [p for (_m, p) in served if "workspace" in p]
    assert not any("/thread/" in p for p in workspace_paths), (
        f"the resolve path addressed a thread instead of the workspace: {workspace_paths}"
    )
    listed_thread_slugs = [
        thread["slug"]
        for workspace in _WORKSPACES["workspaces"]
        for thread in workspace.get("threads", [])
    ]
    assert listed_thread_slugs, "fixture drift: _WORKSPACES declares no threads to avoid"
    for slug in listed_thread_slugs:
        assert not any(slug in p for (_m, p) in served), (
            f"thread {slug} was addressed; the caller gave no session so no thread "
            f"may be chosen or created. served={served}"
        )


def test_send_prefers_wired_agent_over_auto_pick(http_router):
    """A wired agent (spec.agent) wins over first-workspace auto-pick."""
    host, port, router = http_router
    router.routes = {
        ("GET", "/api/v1/workspaces"): (200, _WORKSPACES),
        ("POST", "/api/v1/workspace/empty-ws/stream-chat"): (
            200,
            "data: " + json.dumps({"textResponse": "WIRED-OK"}) + "\ndata: [DONE]\n",
        ),
    }
    result = remotes_core.operate(
        "anythingllm", "send", prompt="hi", config=_cfg(host, port, agent="empty-ws")
    )
    assert result.ok is True, result.detail
    assert result.data.get("response") == "WIRED-OK"
    assert "empty-ws" in result.detail


def test_send_wired_agent_thread_form(http_router):
    """A wired agent may be workspace:thread — the thread form is honored."""
    host, port, router = http_router
    router.routes = {
        ("POST", "/api/v1/workspace/teamstinky/thread/onboarding/stream-chat"): (
            200,
            "data: " + json.dumps({"textResponse": "THREAD-OK"}) + "\ndata: [DONE]\n",
        ),
    }
    result = remotes_core.operate(
        "anythingllm",
        "send",
        prompt="hi",
        config=_cfg(host, port, agent="teamstinky:onboarding"),
    )
    assert result.ok is True, result.detail
    assert result.data.get("response") == "THREAD-OK"


def test_send_no_workspaces_still_honest(http_router):
    """Gateway up but zero workspaces → the original refusal, verbatim."""
    host, port, router = http_router
    router.routes = {("GET", "/api/v1/workspaces"): (200, {"workspaces": []})}
    result = remotes_core.operate(
        "anythingllm", "send", prompt="hi", config=_cfg(host, port)
    )
    assert result.ok is False
    assert "Pick an AnythingLLM workspace or thread" in result.detail
    assert "does not mint" in result.detail

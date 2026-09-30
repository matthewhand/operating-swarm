"""#1358 — the TrueForge navbar catalog (agents + sessions), TrueForge-only.

``remotes_core.trueforge_catalog`` feeds the navbar Agent / Session pickers.
It must list only the named TrueForge instance's agents and sessions, never
another provider's rows and never the default inference profile, and must
degrade to an honest empty catalog when the endpoint is down.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

from swarm.core import remotes as remotes_core
from functools import partial


class _TrueForgeRouter(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        entry = self.routes.get((method, path), (404, {"error": "not found"}))
        status, body = entry
        payload = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

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

def _tf_server():
    _TrueForgeRouter.routes = {}
    server = HTTPServer(("127.0.0.1", 0), _TrueForgeRouter)
    thread = threading.Thread(target=partial(server.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    return server, server.server_address[1], _TrueForgeRouter


def _cfg(base_url: str) -> dict[str, Any]:
    return {"remotes": {"trueforge": {"base_url": base_url}}}


def test_trueforge_catalog_happy_path(monkeypatch):
    """GET /api/v1/agents + /sessions → normalized agents + sessions."""
    server, port, router = _tf_server()
    router.routes = {
        ("GET", "/api/v1/agents"): (
            200,
            {"data": [{"id": "agent-1", "name": "orchestrator"}, {"id": "agent-2", "name": "coder"}]},
        ),
        ("GET", "/api/v1/sessions"): (
            200,
            {
                "data": [
                    {
                        "id": "sess-9",
                        "agent": {"type": "agent", "id": "agent-1", "name": "orchestrator"},
                        "title": "refactor the parser",
                        "created_at": "2026-09-21T10:00:00Z",
                        "updated_at": "2026-09-22T08:30:00Z",
                    },
                    {"id": "sess-4", "agent": "coder"},
                ]
            },
        ),
    }
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    try:
        catalog = remotes_core.trueforge_catalog("trueforge", config=_cfg(f"http://127.0.0.1:{port}"))
    finally:
        server.shutdown()
        server.server_close()

    assert catalog["object"] == "trueforge.catalog"
    assert catalog["kind"] == "trueforge"
    assert catalog["remote"] == "trueforge"
    assert catalog["ok"] is True
    assert catalog["rows_are"] == "agents"
    assert catalog["resume_key"] == "session_id"
    assert [row["id"] for row in catalog["agents"]] == ["agent-1", "agent-2"]
    assert catalog["agents"][0]["label"] == "orchestrator"
    assert [row["id"] for row in catalog["sessions"]] == ["sess-9", "sess-4"]
    assert catalog["sessions"][0]["title"] == "refactor the parser"
    assert catalog["sessions"][0]["agent"] == "orchestrator"
    assert catalog["sessions"][0]["updated_at"] == "2026-09-22T08:30:00Z"
    # The agent rows are agents, never presented as resumable sessions.
    assert {row["id"] for row in catalog["sessions"]}.isdisjoint({"agent-1", "agent-2"})


def test_trueforge_catalog_endpoint_down_degrades(monkeypatch):
    """A down endpoint yields an honest empty catalog — never a raise."""
    server, port, router = _tf_server()
    router.routes = {("GET", "/api/v1/agents"): (503, {"error": "unavailable"})}
    monkeypatch.delenv("TRUEFORGE_BASE_URL", raising=False)
    try:
        catalog = remotes_core.trueforge_catalog("trueforge", config=_cfg(f"http://127.0.0.1:{port}"))
    finally:
        server.shutdown()
        server.server_close()

    assert catalog["ok"] is False
    assert catalog["agents"] == []
    assert catalog["sessions"] == []
    assert catalog["detail"]
    assert catalog["kind"] == "trueforge"


def test_trueforge_catalog_refuses_foreign_remote():
    """A non-TrueForge remote is refused — never fans out to another provider."""
    cfg = {"remotes": {"hermes": {"base_url": "http://192.0.2.10:8642"}}}
    catalog = remotes_core.trueforge_catalog("hermes", config=cfg)
    assert catalog["ok"] is False
    assert catalog["error"] == "not_trueforge"
    assert catalog["agents"] == []
    assert catalog["sessions"] == []
    assert "not a TrueForge remote" in catalog["detail"]


def test_trueforge_catalog_unconfigured_degrades_quietly():
    """Unconfigured TrueForge → empty catalog with an honest detail, no raise."""
    catalog = remotes_core.trueforge_catalog("trueforge", config={"llm": {}, "remotes": {}})
    assert catalog["ok"] is False
    assert catalog["agents"] == []
    assert catalog["sessions"] == []


def test_trueforge_catalog_blank_id_is_rejected():
    catalog = remotes_core.trueforge_catalog("", config={"remotes": {}})
    assert catalog["ok"] is False
    assert catalog["agents"] == []
    assert catalog["sessions"] == []
    assert "remote id" in catalog["detail"]

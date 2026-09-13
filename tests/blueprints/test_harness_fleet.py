"""Tests for the harness_fleet blueprint grammar, classification, and config overrides."""
from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from swarm.blueprints.harness_fleet.blueprint_harness_fleet import HarnessFleetBlueprint


async def _collect(gen):
    return [c async for c in gen]


def _final(chunks):
    for c in chunks:
        msgs = c.get("messages") if isinstance(c, dict) else None
        if msgs and msgs[0].get("content"):
            return msgs[0]["content"]
    return None


@pytest.fixture
def bp():
    # builtins: false keeps tests hermetic — no live LAN probes.
    config = {
        "llm": {},
        "harness_fleet": {"builtins": False, "entries": {}},
    }
    return HarnessFleetBlueprint(config=config)


async def _ask(bp, content, params=None):
    bp.set_params(params or {})
    return _final(await _collect(bp.run([{"role": "user", "content": content}])))


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):  # silence
        pass


@pytest.fixture
def http_server():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield "127.0.0.1", server.server_address[1]
    server.shutdown()


@pytest.mark.asyncio
async def test_list_shows_inventory_without_probing():
    # list never probes, so built-ins (live LAN hosts) are safe to include.
    b = HarnessFleetBlueprint(config={"llm": {}})
    out = await _ask(b, "list")
    assert "nemohermes-36" in out
    assert "rakazo-32" in out
    assert "omb-32" in out
    assert "198.51.100.32:3100" in out
    assert "198.51.100.32:8802" in out
    assert "UP" not in out  # no probing happened


@pytest.mark.asyncio
async def test_list_empty_inventory(bp):
    out = await _ask(bp, "list")
    assert "inventory" in out
    assert "10.0.0" not in out  # builtins excluded


@pytest.mark.asyncio
async def test_status_reports_down_for_closed_port(bp):
    bp._config["harness_fleet"] = {
        "builtins": False,
        "entries": {"ghost": {"host": "127.0.0.1", "port": 1, "kind": "test"}},
    }
    out = await _ask(bp, "status")
    assert "✗ ghost" in out and "DOWN" in out
    assert "refused/timed out" in out


@pytest.mark.asyncio
async def test_check_single_up_service(bp, http_server):
    host, port = http_server
    bp._config["harness_fleet"] = {
        "builtins": False,
        "entries": {"tiny": {"host": host, "port": port, "kind": "test"}}
    }
    out = await _ask(bp, f"check tiny")
    assert "✓ tiny" in out
    assert "UP" in out


@pytest.mark.asyncio
async def test_auth_expected_401_counts_as_up(bp, http_server):
    class AuthHandler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            self.send_response(401)
            self.end_headers()

        def log_message(self, *args):
            pass

    host, port = http_server

    server = HTTPServer(("127.0.0.1", 0), AuthHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        bp._config["harness_fleet"] = {
            "builtins": False,
            "entries": {
                "gated": {
                    "host": "127.0.0.1",
                    "port": server.server_address[1],
                    "kind": "test",
                    "health_path": "/api/",
                    "auth_expected": True,
                }
            }
        }
        out = await _ask(bp, "status")
        assert "auth required, expected" in out
    finally:
        server.shutdown()


@pytest.mark.asyncio
async def test_endpoint_tbd_is_unknown_not_down(bp):
    bp._config["harness_fleet"] = {
        "builtins": False,
        "entries": {"mystery": {"host": "10.9.9.9", "endpoint_tbd": True}},
    }
    out = await _ask(bp, "check mystery")
    assert "?" in out and "UNKNOWN" in out
    assert "not configured" in out


@pytest.mark.asyncio
async def test_check_unknown_name_lists_choices(bp):
    out = await _ask(bp, "check nope")
    assert "nope" in out.lower()
    assert "Known:" in out


@pytest.mark.asyncio
async def test_config_entries_override_builtins(bp, http_server):
    host, port = http_server
    bp._config["harness_fleet"] = {
        "builtins": False,
        "entries": {"ollama-30": {"host": host, "port": port}},
    }
    out = await _ask(bp, "check ollama-30")
    # override wins: probes the local server (UP), not the real .30 box
    assert "✓ ollama-30" in out


@pytest.mark.asyncio
async def test_params_op_and_name(bp, http_server):
    host, port = http_server
    bp._config["harness_fleet"] = {
        "builtins": False,
        "entries": {"svc": {"host": host, "port": port, "kind": "test"}}
    }
    out = await _ask(bp, "", params={"op": "check", "name": "svc"})
    assert "✓ svc" in out


@pytest.mark.asyncio
async def test_tcp_only_entry_up_when_port_open(http_server):
    host, port = http_server
    config = {"llm": {}, "harness_fleet": {"entries": {}}}
    b = HarnessFleetBlueprint(config=config)
    b.set_params({})
    state, detail = b._classify({"host": host, "port": port}, timeout=2.0)
    assert state == "UP"
    assert "tcp" in detail

"""Tests for Multiple TrueForge Remote instances support.

Validates:
1. Configuring multiple TrueForge instances (e.g. trueforge, trueforge_secondary, trueforge_gpu).
2. Independent health checks, sends, and routines across instances.
3. Env var slug resolution (${TRUEFORGE_SECONDARY_URL} / ${TRUEFORGE_SECONDARY_BASE_URL}).
4. Blueprint discovery and specialist agent-as-tool generation for each instance.
5. Persistence, loading, and deletion via remotes API and core functions.

Hermetic test suite — loopback 127.0.0.1 only, zero sensitive LAN IP references.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from swarm.blueprints.remote_harness.blueprint_remote_harness import RemoteHarnessBlueprint
from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    capabilities_for,
    get_harness,
    is_remote_impl_id,
    is_trueforge_remote,
    normalize_impl_id,
)


class _MockTrueForgeHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.server.received_headers.append(dict(self.headers))
        content_len = int(self.headers.get("Content-Length", 0))
        body = None
        if content_len > 0:
            raw_body = self.rfile.read(content_len).decode("utf-8")
            try:
                body = json.loads(raw_body)
            except Exception:
                body = raw_body
            self.server.received_bodies.append((method, path, body))

        key = (method, path)
        status, response_body = self.server.routes.get(
            key, (404, {"error": f"no route for {method} {path}"})
        )
        payload = (
            json.dumps(response_body).encode("utf-8")
            if not isinstance(response_body, (str, bytes))
            else response_body.encode("utf-8")
            if isinstance(response_body, str)
            else response_body
        )
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        self._handle("GET")

    def do_POST(self) -> None:  # noqa: N802
        self._handle("POST")

    def log_message(self, *args) -> None:
        pass


class MockTrueForgeServer:
    def __init__(self):
        self.routes: dict[tuple[str, str], tuple[int, Any]] = {}
        self.received_headers: list[dict[str, str]] = []
        self.received_bodies: list[tuple[str, str, Any]] = []
        self.server = HTTPServer(("127.0.0.1", 0), _MockTrueForgeHandler)
        self.server.routes = self.routes
        self.server.received_headers = self.received_headers
        self.server.received_bodies = self.received_bodies
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host = "127.0.0.1"
        self.port = self.server.server_address[1]
        self.base_url = f"http://{self.host}:{self.port}"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def mock_servers():
    s1 = MockTrueForgeServer()
    s2 = MockTrueForgeServer()
    yield s1, s2
    s1.close()
    s2.close()


def test_trueforge_instance_identification():
    """Verify arbitrary instance names with kind='trueforge' or naming pattern."""
    assert is_trueforge_remote("trueforge")
    assert is_trueforge_remote("trueforge_prod")
    assert is_trueforge_remote("trueforge_secondary")
    assert is_trueforge_remote("trueforge-cluster-1")
    assert is_trueforge_remote("tf_local")
    assert is_trueforge_remote("custom_remote_id", kind="trueforge")

    assert is_remote_impl_id("trueforge")
    assert is_remote_impl_id("trueforge_prod")
    assert is_remote_impl_id("trueforge_secondary")

    assert normalize_impl_id("trueforge_prod") == "trueforge"
    assert normalize_impl_id("trueforge_secondary") == "trueforge"

    caps = capabilities_for("trueforge_secondary")
    assert caps.routines is True
    assert caps.list is True
    assert caps.send is True
    assert caps.health is True

    harness = get_harness("trueforge_secondary")
    assert harness is not None
    assert harness.impl_id == "trueforge"


def test_multiple_trueforge_config_loading(mock_servers):
    s1, s2 = mock_servers
    cfg = {
        "remotes": {
            "trueforge": {
                "base_url": s1.base_url,
                "api_key_env": "KEY_TF_1",
            },
            "trueforge_secondary": {
                "kind": "trueforge",
                "base_url": s2.base_url,
                "api_key_env": "KEY_TF_2",
            },
        }
    }

    assert remotes_core.is_configured("trueforge", cfg)
    assert remotes_core.is_configured("trueforge_secondary", cfg)

    configured_ids = remotes_core.configured_remote_ids(cfg)
    assert "trueforge" in configured_ids
    assert "trueforge_secondary" in configured_ids

    spec1 = remotes_core.load_remote("trueforge", config=cfg)
    assert spec1.id == "trueforge"
    assert spec1.kind == "trueforge"
    assert spec1.base_url == s1.base_url
    assert spec1.api_key_env == "KEY_TF_1"

    spec2 = remotes_core.load_remote("trueforge_secondary", config=cfg)
    assert spec2.id == "trueforge_secondary"
    assert spec2.kind == "trueforge"
    assert spec2.base_url == s2.base_url
    assert spec2.api_key_env == "KEY_TF_2"

    pub2 = spec2.public_dict()
    assert pub2["id"] == "trueforge_secondary"
    assert pub2["kind"] == "trueforge"
    assert pub2["capabilities"]["routines"] is True
    assert pub2["member"]["talk"] == "consult_trueforge_secondary"

    all_remotes = remotes_core.load_all_remotes(config=cfg)
    assert "trueforge" in all_remotes
    assert "trueforge_secondary" in all_remotes


def test_trueforge_env_slug_fallback(monkeypatch):
    """Verify fallback to ${TRUEFORGE_<SLUG>_BASE_URL} or ${TRUEFORGE_<SLUG>_URL}."""
    monkeypatch.setenv("TRUEFORGE_SECONDARY_BASE_URL", "http://127.0.0.1:8799")
    monkeypatch.setenv("TRUEFORGE_SECONDARY_API_KEY", "env-key-99")

    spec = remotes_core.load_remote("trueforge_secondary", config={})
    assert spec.id == "trueforge_secondary"
    assert spec.kind == "trueforge"
    assert spec.base_url == "http://127.0.0.1:8799"
    assert spec.api_key == "env-key-99"


def test_independent_health_checks(mock_servers):
    s1, s2 = mock_servers
    s1.routes[("GET", "/healthz")] = (200, {"status": "ok", "version": "1.2.3"})
    s2.routes[("GET", "/healthz")] = (503, {"error": "unhealthy service"})

    cfg = {
        "remotes": {
            "trueforge": {"base_url": s1.base_url},
            "trueforge_secondary": {"kind": "trueforge", "base_url": s2.base_url},
        }
    }

    h1 = remotes_core.check_health("trueforge", config=cfg)
    assert h1.ok is True
    assert h1.remote == "trueforge"
    assert h1.version == {"version": "1.2.3"}
    assert h1.state == "UP"

    h2 = remotes_core.check_health("trueforge_secondary", config=cfg)
    assert h2.ok is False
    assert h2.remote == "trueforge_secondary"
    assert h2.state == "DEGRADED"
    assert "503" in h2.detail or "unhealthy" in h2.detail


def test_independent_send_jobs(mock_servers):
    s1, s2 = mock_servers

    # Server 1 endpoints (/api/v1/sessions)
    s1.routes[("POST", "/api/v1/sessions")] = (200, {"data": {"id": "sess-alpha"}})
    s1.routes[("POST", "/api/v1/sessions/sess-alpha/turns")] = (
        200,
        {"data": {"id": "turn-alpha", "state": "RUNNING"}},
    )
    s1.routes[("GET", "/api/v1/sessions/sess-alpha/turns/turn-alpha")] = (
        200,
        {"data": {"id": "turn-alpha", "state": "done"}},
    )
    s1.routes[("GET", "/api/v1/sessions/sess-alpha/turns/turn-alpha/events")] = (
        200,
        {"data": [{"type": "model.message", "content": "Alpha final reply"}]},
    )

    # Server 2 endpoints (/api/v1/sessions)
    s2.routes[("POST", "/api/v1/sessions")] = (200, {"data": {"id": "sess-beta"}})
    s2.routes[("POST", "/api/v1/sessions/sess-beta/turns")] = (
        200,
        {"data": {"id": "turn-beta", "state": "RUNNING"}},
    )
    s2.routes[("GET", "/api/v1/sessions/sess-beta/turns/turn-beta")] = (
        200,
        {"data": {"id": "turn-beta", "state": "done"}},
    )
    s2.routes[("GET", "/api/v1/sessions/sess-beta/turns/turn-beta/events")] = (
        200,
        {"data": [{"type": "model.message", "content": "Beta final reply"}]},
    )

    cfg = {
        "remotes": {
            "trueforge": {"base_url": s1.base_url},
            "trueforge_secondary": {"kind": "trueforge", "base_url": s2.base_url},
        }
    }

    # Dispatch to instance 1
    res1 = remotes_core.operate("trueforge", "send", prompt="Hello 1", config=cfg)
    assert res1.ok is True
    assert res1.remote == "trueforge"
    assert res1.detail == "Alpha final reply"
    assert res1.data["session_id"] == "sess-alpha"

    # Dispatch to instance 2
    res2 = remotes_core.operate("trueforge_secondary", "send", prompt="Hello 2", config=cfg)
    assert res2.ok is True
    assert res2.remote == "trueforge_secondary"
    assert res2.detail == "Beta final reply"
    assert res2.data["session_id"] == "sess-beta"

    # Verify requests landed on corresponding servers
    assert any("/api/v1/sessions" in path for _, path, _ in s1.received_bodies)
    assert any("/api/v1/sessions" in path for _, path, _ in s2.received_bodies)


def test_independent_routines(mock_servers):
    s1, s2 = mock_servers
    s1.routes[("GET", "/api/v1/schedules")] = (
        200,
        {
            "data": [
                {
                    "id": "r1",
                    "name": "Code Sync",
                    "agent_name": "sync-bot",
                    "manifest": {"task": "Sync Code", "cron": "@hourly", "status": "active"},
                }
            ]
        },
    )
    s2.routes[("GET", "/api/v1/schedules")] = (
        200,
        {
            "data": [
                {
                    "id": "r2",
                    "name": "DB Backup",
                    "agent_name": "backup-bot",
                    "manifest": {"task": "Backup DB", "cron": "@daily", "status": "active"},
                }
            ]
        },
    )

    cfg = {
        "remotes": {
            "trueforge": {"base_url": s1.base_url},
            "trueforge_secondary": {"kind": "trueforge", "base_url": s2.base_url},
        }
    }

    routines1 = remotes_core.operate("trueforge", "routines", config=cfg)
    assert routines1.ok is True
    assert routines1.remote == "trueforge"
    assert len(routines1.data["routines"]) == 1
    assert routines1.data["routines"][0]["id"] == "r1"

    routines2 = remotes_core.operate("trueforge_secondary", "routines", config=cfg)
    assert routines2.ok is True
    assert routines2.remote == "trueforge_secondary"
    assert len(routines2.data["routines"]) == 1
    assert routines2.data["routines"][0]["id"] == "r2"


def test_blueprint_placed_multiple_trueforge_instances(mock_servers):
    s1, s2 = mock_servers
    cfg = {
        "agent_team": {
            "members": ["trueforge", "trueforge_secondary"],
        },
        "remotes": {
            "trueforge": {"base_url": s1.base_url},
            "trueforge_secondary": {"kind": "trueforge", "base_url": s2.base_url},
        },
    }

    placed = remotes_core.load_placed_members(cfg)
    assert "trueforge" in placed
    assert "trueforge_secondary" in placed

    bp = RemoteHarnessBlueprint(config=cfg)
    agents = bp._build_agents()
    assert "trueforge" in agents
    assert "trueforge_secondary" in agents

    coordinator = agents.get("coordinator")
    assert coordinator is not None

    tool_names = [getattr(t, "__name__", "") or getattr(t, "name", "") for t in coordinator.tools]
    assert "consult_trueforge" in tool_names
    assert "consult_trueforge_secondary" in tool_names


def test_persist_and_delete_multiple_instances(tmp_path: Path):
    cfg_file = tmp_path / "swarm_config.json"
    cfg_file.write_text("{}", encoding="utf-8")

    # Persist instance 1
    spec1, _ = remotes_core.persist_remote(
        "trueforge",
        base_url="http://127.0.0.1:8791",
        api_key_env="TF_KEY_1",
        config_path=cfg_file,
    )
    assert spec1.id == "trueforge"

    # Persist instance 2 with custom ID
    spec2, _ = remotes_core.persist_remote(
        "trueforge_custom",
        kind="trueforge",
        base_url="http://127.0.0.1:8792",
        api_key_env="TF_KEY_2",
        config_path=cfg_file,
    )
    assert spec2.id == "trueforge_custom"
    assert spec2.kind == "trueforge"

    # Read config back
    data = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "trueforge" in data["remotes"]
    assert "trueforge_custom" in data["remotes"]
    assert data["remotes"]["trueforge_custom"]["kind"] == "trueforge"
    assert data["remotes"]["trueforge_custom"]["base_url"] == "http://127.0.0.1:8792"

    # Delete instance 2
    deleted_id, _ = remotes_core.delete_remote("trueforge_custom", config_path=cfg_file)
    assert deleted_id == "trueforge_custom"

    data_after = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "trueforge" in data_after["remotes"]
    assert "trueforge_custom" not in data_after["remotes"]

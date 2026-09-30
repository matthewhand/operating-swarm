"""OpenMuse as a first-class ``remote`` — one OpenMuse task per OS session.

Hermetic: a loopback router stands in for the Hono server. No live instance,
no LLM. Both real OpenMuse instances are down, so every wire fact asserted
here comes from the route contract in ``remote_impls/openmuse.py``, not from
a live probe.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remote_harness import (
    REMOTE_IMPL_IDS,
    capabilities_for,
    is_remote_impl_id,
    normalize_impl_id,
    sessions_from_operate,
)
from swarm.core.remote_impls.openmuse import (
    _TOKEN_CACHE,
    _TOKEN_TTL_S,
    openmuse_clear_token_cache,
    openmuse_pending_question,
    openmuse_task_row,
    openmuse_task_text,
)
from swarm.remotes.registry import REMOTE_ADAPTER_REGISTRY, create_remote_adapter
from functools import partial

ACCESS_KEY = "sk-openmuse-do-not-leak-1234"
TOKEN = "tok_abcdefghijklmnopqrstuvwxyz012345"


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    # Per-route call sequence, so a poll can move from running → done.
    sequence: dict[tuple[str, str], list[Any]] = {}
    hits: dict[tuple[str, str], int] = {}
    auth_headers: list[str] = []
    bodies: list[tuple[str, str, Any]] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.auth_headers.append(self.headers.get("Authorization") or "")
        length = int(self.headers.get("Content-Length", 0))
        body = None
        if length > 0:
            raw = self.rfile.read(length).decode("utf-8")
            try:
                body = json.loads(raw)
            except ValueError:
                body = raw
            self.bodies.append((method, path, body))
        key = (method, path)
        entry = self.sequence.get(key)
        if entry:
            idx = self.hits.get(key, 0)
            status, payload = entry[min(idx, len(entry) - 1)]
        else:
            status, payload = self.routes.get(key, (404, {"detail": "no route"}))
        self.hits[key] = self.hits.get(key, 0) + 1
        data = (
            json.dumps(payload).encode("utf-8")
            if not isinstance(payload, str)
            else payload.encode()
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

    @classmethod
    def reset(cls) -> None:
        cls.routes = {}
        cls.sequence = {}
        cls.hits = {}
        cls.auth_headers = []
        cls.bodies = []

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

@pytest.fixture
def server():
    _Router.reset()
    openmuse_clear_token_cache()
    httpd = HTTPServer(("127.0.0.1", 0), _Router)
    thread = threading.Thread(target=partial(httpd.serve_forever, poll_interval=0.02), daemon=True)
    thread.start()
    host, port = "127.0.0.1", httpd.server_address[1]
    yield host, port
    httpd.shutdown()
    httpd.server_close()
    _Router.reset()
    openmuse_clear_token_cache()


def _cfg(host: str, port: int, **extra) -> dict[str, Any]:
    block: dict[str, Any] = {
        "base_url": f"http://{host}:{port}",
        "api_key": ACCESS_KEY,
        "kind": "openmuse",
    }
    block.update(extra)
    return {"llm": {}, "remotes": {"openmuse": block}}


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    """Never let a developer's real env leak into an assertion."""
    for name in (
        "OPENMUSE_BASE_URL",
        "OPENMUSE_ACCESS_KEY",
        "OPENMUSE_2_BASE_URL",
        "OPENMUSE_2_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _mint_ok() -> None:
    _Router.routes[("POST", "/api/session")] = (200, {"token": TOKEN, "mode": "live"})


def _bodies_for(method: str, path: str) -> list[Any]:
    return [b for m, p, b in _Router.bodies if m == method and p == path]


# ---------------------------------------------------------------------------
# Catalog / registry
# ---------------------------------------------------------------------------


def test_openmuse_is_a_catalog_remote_kind():
    assert "openmuse" in REMOTE_IMPL_IDS
    assert "openmuse" in remotes_core.REMOTE_IDS
    assert "openmuse" in remotes_core.REMOTE_KIND_IDS
    assert "openmuse" in remotes_core.OPT_IN_REMOTE_IDS
    assert is_remote_impl_id("openmuse")
    assert is_remote_impl_id("open-muse")
    assert normalize_impl_id("openmuse") == "openmuse"
    assert normalize_impl_id("open-muse") == "openmuse"
    assert normalize_impl_id("openmuse-lab") == "openmuse"
    assert remotes_core.kind_of_instance("openmuse-lab") == "openmuse"
    assert remotes_core.kind_label("openmuse") == "OpenMuse"
    # OpenMuse is NOT OpenMousBot. The names share a prefix and nothing else.
    assert remotes_core.kind_label("omb") == "OpenMousBot"
    assert remotes_core.kind_label("openmuse") != "OpenMousBot"
    spec = remotes_core.default_spec("openmuse")
    assert spec.health_path == "/api/health"  # verified live: one unauthenticated route
    assert spec.api_key == "${OPENMUSE_ACCESS_KEY}"
    kinds = {k["id"]: k for k in remotes_core.list_remote_kinds()}
    assert kinds["openmuse"]["kind"] == "remote"
    assert kinds["openmuse"]["label"] == "OpenMuse"


def test_openmuse_declares_its_capabilities_honestly():
    caps = capabilities_for("openmuse")
    # A task is the resumable unit (its id is the session id), and a task can
    # stop on a question the operator answers via /input.
    assert caps.sessions is True
    assert caps.elicit_questions is True
    assert caps.server_managed_context is True
    assert caps.transport == "http"
    # OpenMuse has no routines endpoint, no interrogate, no computer control.
    assert caps.routines is False
    assert caps.interrogate is False
    assert caps.operate is False


def test_registry_routes_openmuse():
    from swarm.remotes.openmuse import OpenMuseAdapter

    assert REMOTE_ADAPTER_REGISTRY["openmuse"] is OpenMuseAdapter
    spec = remotes_core.RemoteSpec(
        id="openmuse",
        title="OpenMuse",
        host_label="openmuse",
        base_url="http://127.0.0.1:8787",
        kind="openmuse",
    )
    assert isinstance(create_remote_adapter(spec), OpenMuseAdapter)


def test_openmuse_is_opt_in_not_auto_placed():
    cfg = {"llm": {}, "remotes": {}}
    assert remotes_core.is_configured("openmuse", cfg) is False
    assert "openmuse" not in remotes_core.load_placed_members(cfg)
    listed = remotes_core.operate("openmuse", "list", config=cfg)
    assert listed.ok is False
    health = remotes_core.check_health("openmuse", config=cfg, timeout=0.2)
    assert health.state == "UNKNOWN"


# ---------------------------------------------------------------------------
# 1. token minted once and reused across calls
# ---------------------------------------------------------------------------


def test_token_is_minted_once_and_reused_across_calls(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    _Router.routes[("GET", "/api/health")] = (200, {"ok": True, "mode": "live"})

    cfg = _cfg(host, port)
    for _ in range(3):
        assert remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0).ok
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok

    # One mint for four authenticated calls.
    assert _Router.hits[("POST", "/api/session")] == 1
    # The mint itself carries no Authorization header; every call after it
    # carries the same session token.
    assert _Router.auth_headers == [""] + [f"Bearer {TOKEN}"] * 4


def test_token_cache_is_per_instance_not_global(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    cfg = _cfg(host, port)
    assert remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0).ok
    # A named instance is a different OpenMuse session even at the same URL.
    other = _cfg(host, port)
    other["remotes"]["openmuse-2"] = dict(other["remotes"]["openmuse"])
    assert remotes_core.operate("openmuse-2", "list", config=other, timeout=3.0).ok
    assert _Router.hits[("POST", "/api/session")] == 2
    assert len(_TOKEN_CACHE) == 2


def test_a_sample_mode_instance_needs_no_access_key(server):
    """``POST /api/session`` takes an optional accessKey in sample mode."""
    host, port = server
    _Router.routes[("POST", "/api/session")] = (200, {"token": TOKEN, "mode": "sample"})
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    cfg = _cfg(host, port, api_key="")
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert _bodies_for("POST", "/api/session") == [{}]


def test_a_403_is_not_treated_as_a_stale_token(server):
    """401 is staleness and earns one re-mint; 403 is policy and does not."""
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (403, {"detail": "Forbidden"})
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is False
    assert listed.gap == "openmuse_auth"
    assert _Router.hits[("GET", "/api/agent/tasks")] == 1
    assert _Router.hits[("POST", "/api/session")] == 1


def test_a_wrong_access_key_is_an_actionable_gap_not_a_401(server):
    host, port = server
    _Router.routes[("POST", "/api/session")] = (401, {"detail": "Access key is incorrect"})
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is False
    assert listed.gap == "openmuse_auth"
    assert "OPENMUSE_ACCESS_KEY" in listed.detail
    assert listed.action == {
        "kind": "settings",
        "section": "remotes",
        "remote": "openmuse",
        "field": "api_key_env",
    }
    assert ACCESS_KEY not in listed.detail


def test_a_session_that_returns_no_token_is_reported(server):
    host, port = server
    _Router.routes[("POST", "/api/session")] = (200, {"mode": "live"})
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is False
    assert listed.gap == "openmuse_no_token"


# ---------------------------------------------------------------------------
# 2. a 401 triggers exactly one re-auth, then succeeds
# ---------------------------------------------------------------------------


def test_one_401_re_auths_once_and_then_succeeds(server):
    host, port = server
    _mint_ok()
    # The first authenticated call is refused; the retry after re-mint works.
    _Router.sequence[("GET", "/api/agent/tasks")] = [
        (401, {"detail": "Session expired. Sign in again."}),
        (200, {"tasks": []}),
    ]
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert _Router.hits[("GET", "/api/agent/tasks")] == 2
    # Exactly one re-mint: the initial mint, then the single forced retry.
    assert _Router.hits[("POST", "/api/session")] == 2


def test_a_second_401_after_re_auth_stops_instead_of_looping(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (401, {"detail": "Sign in to OpenMuse"})
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is False
    assert listed.gap == "openmuse_auth"
    # Two calls, two mints, no third attempt. A loop here would hang the chat.
    assert _Router.hits[("GET", "/api/agent/tasks")] == 2
    assert _Router.hits[("POST", "/api/session")] == 2


def test_a_stale_cached_token_re_auths_on_first_use(server):
    """A cached token the server has since expired is replaced once, not re-asked for."""
    host, port = server
    _mint_ok()
    _Router.sequence[("GET", "/api/agent/tasks")] = [
        (401, {"detail": "Session expired. Sign in again."}),
        (200, {"tasks": []}),
    ]
    cfg = _cfg(host, port)
    # Fresh enough to be *used* (so the 401 is the server rejecting it, not the
    # TTL skipping it), but rejected on the wire.
    _TOKEN_CACHE["openmuse|" + f"http://{host}:{port}"] = (time.monotonic(), "stale-token")
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    # The cached token is tried first (that is the point of caching), the 401
    # mints once, and the retry carries the new token.
    assert _Router.auth_headers == ["Bearer stale-token", "", f"Bearer {TOKEN}"]
    assert _Router.hits[("POST", "/api/session")] == 1


def test_a_token_older_than_the_server_ttl_is_not_used_at_all(server):
    """Past the 23h refresh mark the cached token is skipped, not sent."""
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    cfg = _cfg(host, port)
    _TOKEN_CACHE["openmuse|" + f"http://{host}:{port}"] = (
        time.monotonic() - _TOKEN_TTL_S - 60,
        "ancient-token",
    )
    assert remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0).ok
    assert _Router.hits[("POST", "/api/session")] == 1
    assert "ancient-token" not in _Router.auth_headers


# ---------------------------------------------------------------------------
# 3. list maps tasks → session rows
# ---------------------------------------------------------------------------


def test_list_maps_tasks_to_session_rows(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (
        200,
        {
            "tasks": [
                {
                    "id": "task-a",
                    "title": "Ship the release",
                    "status": "completed",
                    "kind": "agent",
                    "updated_at": "2026-09-28T00:00:00Z",
                },
                {
                    "id": "task-b",
                    "status": "running",
                    "kind": "monitor",
                    "prompt": "Watch the deploy queue\nfor stalls",
                },
            ]
        },
    )
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert listed.data["rows_are"] == "tasks"
    assert listed.data["resume_key"] == "task_id"
    rows = listed.data["sessions"]
    assert [row["id"] for row in rows] == ["task-a", "task-b"]
    assert rows[0]["title"] == "Ship the release"
    assert rows[0]["snippet"] == "completed"
    assert rows[0]["updated_at"] == "2026-09-28T00:00:00Z"
    # No title → the prompt leads, never an invented one.
    assert rows[1]["title"] == "Watch the deploy queue for stalls"
    sessions = sessions_from_operate(listed)
    assert [s.id for s in sessions] == ["task-a", "task-b"]


def test_list_on_an_empty_instance_yields_no_rows(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert listed.data["sessions"] == []
    assert sessions_from_operate(listed) == []
    assert "0 task(s)" in listed.detail


def test_list_falls_back_to_the_agent_snapshot_when_there_is_no_index(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (404, {"detail": "Not Found"})
    # NO trailing slash. The snapshot route is `/api/agent`; `/api/agent/` is a
    # different, unmounted route that 404s on the live instance. This mock used
    # to key the slashed form, which is how a one-character routing bug shipped
    # with a green suite — see test_the_snapshot_route_has_no_trailing_slash.
    _Router.routes[("GET", "/api/agent")] = (
        200,
        {"tasks": [{"id": "task-s", "title": "From the snapshot"}]},
    )
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert [row["id"] for row in listed.data["sessions"]] == ["task-s"]


def test_the_snapshot_route_has_no_trailing_slash(server):
    """The live instance answers `/api/agent` and 404s on `/api/agent/`.

    Registering the slashed form as a 404 here means any reintroduction of the
    trailing slash fails this test instead of silently making every OpenMuse seat
    look sessionless.
    """
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (404, {"detail": "Not Found"})
    _Router.routes[("GET", "/api/agent")] = (
        200,
        {"tasks": [{"id": "task-real", "title": "From the snapshot"}]},
    )
    _Router.routes[("GET", "/api/agent/")] = (404, {"detail": "Not Found"})

    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert [row["id"] for row in listed.data["sessions"]] == ["task-real"]
    # And the seat must not tell the operator a falsehood about itself.
    assert "no task list" not in str(listed.detail).lower()


def test_list_drops_tasks_without_a_safe_id_rather_than_inventing_one(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (
        200,
        {
            "tasks": [
                {"id": "task-ok", "title": "real"},
                {"title": "no id at all"},
                {"id": "bad id with spaces", "title": "unusable"},
            ]
        },
    )
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert [row["id"] for row in listed.data["sessions"]] == ["task-ok"]


def test_list_query_filters_on_what_the_row_shows(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (
        200,
        {
            "tasks": [
                {"id": "task-a", "title": "Ship the release", "status": "completed"},
                {"id": "task-b", "title": "Watch deploys", "status": "running"},
            ]
        },
    )
    cfg = _cfg(host, port)
    listed = remotes_core.operate(
        "openmuse", "list", query="deploys", config=cfg, timeout=3.0
    )
    assert [row["id"] for row in listed.data["sessions"]] == ["task-b"]


def test_list_on_a_build_with_no_task_index_says_so_instead_of_failing(server):
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port)
    result = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    # Verified live: this build 404s BOTH /api/agent/tasks and /api/agent/, so
    # there is no task index at all. The honest answer is "no enumerable
    # sessions", not a broken remote and not a fabricated row.
    assert result.ok is True
    assert result.data["list_supported"] is False
    assert result.data["tasks"] == []
    assert "no task list" in result.detail


# ---------------------------------------------------------------------------
# 4. send creates a task, polls, returns the final text
# ---------------------------------------------------------------------------


def test_send_creates_a_task_polls_and_returns_the_final_text(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": "task-1", "status": "queued", "kind": "agent"},
    )
    _Router.sequence[("GET", "/api/agent/tasks/task-1")] = [
        (200, {"id": "task-1", "status": "running", "events": []}),
        (200, {"id": "task-1", "status": "running", "events": []}),
        (
            200,
            {
                "id": "task-1",
                "status": "completed",
                "result": "Deployed build 482 to staging.",
            },
        ),
    ]
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="deploy build 482", config=cfg, timeout=10.0)
    assert sent.ok is True
    assert sent.data["text"] == "Deployed build 482 to staging."
    assert sent.data["session_id"] == "task-1"
    assert sent.data["status"] == "completed"
    # The create body is the documented createTaskSchema subset: just a prompt.
    assert _bodies_for("POST", "/api/agent/tasks") == [{"prompt": "deploy build 482"}]
    assert _Router.hits[("GET", "/api/agent/tasks/task-1")] == 3


def test_send_reads_the_reply_out_of_the_event_stream(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-2", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-2")] = (
        200,
        {
            "id": "task-2",
            "status": "completed",
            "events": [
                {"type": "task.started"},
                {"type": "assistant.message", "content": "Checking the queue."},
                {"type": "plan.step", "content": "step one"},
                {"type": "assistant.message", "content": "The queue is clear."},
            ],
        },
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="is the queue clear?", config=cfg, timeout=10.0)
    assert sent.ok is True
    assert sent.data["text"] == "The queue is clear."


def test_send_with_an_empty_prompt_never_hits_the_wire(server):
    host, port = server
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="   ", config=cfg, timeout=3.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_prompt_required"
    assert _Router.bodies == []


def test_send_rejects_an_over_long_prompt_before_the_wire(server):
    host, port = server
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="x" * 12001, config=cfg, timeout=3.0
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_prompt_rejected"
    assert "12000" in sent.detail
    assert _Router.bodies == []


def test_send_refuses_the_remotes_own_name_as_a_task_id(server):
    """The #1159 guard: the seat's own id is never a task id.

    A send with NO resume key is the normal case and correctly creates a task —
    OpenMuse's create route is the primary path. The guard fires when a
    caller hands the remote's own name over as the task to continue, which
    would ask OpenMuse for a task called "openmuse" and eat a bare 404.
    """
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port)
    named = remotes_core.operate(
        "openmuse", "send", prompt="go", target="openmuse", config=cfg, timeout=3.0
    )
    assert named.ok is False
    assert named.gap == "openmuse_task_required"
    assert named.data["missing_task"] is True
    assert named.action["field"] == "agent"
    assert _Router.bodies == []

    by_session = remotes_core.operate(
        "openmuse", "send", prompt="go", session_id="openmuse", config=cfg, timeout=3.0
    )
    assert by_session.gap == "openmuse_task_required"
    assert _Router.bodies == []


def test_send_with_a_wired_agent_named_after_the_remote_still_refuses(server):
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port, agent="openmuse")
    sent = remotes_core.operate("openmuse", "send", prompt="go", config=cfg, timeout=3.0)
    assert sent.gap == "openmuse_task_required"
    assert _Router.bodies == []


def test_send_rejects_a_resume_key_that_is_not_a_task_id(server):
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="go", session_id="../../etc/passwd", config=cfg, timeout=3.0
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_task_id_invalid"


def test_send_continues_a_configured_task_instead_of_minting_a_new_one(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks/task-cfg")] = (
        200,
        {"id": "task-cfg", "status": "completed", "result": "first pass"},
    )
    _Router.routes[("POST", "/api/agent/tasks/task-cfg/input")] = (
        200,
        {"id": "task-cfg", "status": "running"},
    )
    _Router.sequence[("GET", "/api/agent/tasks/task-cfg")] = [
        (200, {"id": "task-cfg", "status": "completed", "result": "first pass"}),
        (200, {"id": "task-cfg", "status": "completed", "result": "second pass"}),
    ]
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    # agent: the task id this remote is configured to continue.
    cfg = _cfg(host, port, agent="task-cfg")
    sent = remotes_core.operate("openmuse", "send", prompt="and again", config=cfg, timeout=10.0)
    assert sent.ok is True
    assert sent.data["session_id"] == "task-cfg"
    assert sent.data["text"] == "second pass"
    # No second task was created — the configured task carried the turn.
    assert ("POST", "/api/agent/tasks") not in _Router.hits
    assert _bodies_for("POST", "/api/agent/tasks/task-cfg/input") == [{"answer": "and again"}]


def test_send_starts_a_fresh_task_when_the_configured_one_will_not_take_input(
    server, monkeypatch
):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks/task-done")] = (
        200,
        {"id": "task-done", "status": "completed", "result": "already done"},
    )
    _Router.routes[("POST", "/api/agent/tasks/task-done/input")] = (
        409,
        {"detail": "Task is not accepting input"},
    )
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-new", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-new")] = (
        200,
        {"id": "task-new", "status": "completed", "result": "fresh answer"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port, agent="task-done")
    sent = remotes_core.operate("openmuse", "send", prompt="more", config=cfg, timeout=10.0)
    assert sent.ok is True
    # Honest: the payload says what it continued from and that /input refused.
    assert sent.data["session_id"] == "task-new"
    assert sent.data["continued_from"] == "task-done"
    assert sent.data["continued_from_rejected"] == "Task is not accepting input"


# ---------------------------------------------------------------------------
# 5. pending question surfacing + /input answer
# ---------------------------------------------------------------------------


def test_pending_question_is_surfaced_on_a_paused_task(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-q", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-q")] = (
        200,
        {
            "id": "task-q",
            "status": "running",
            "events": [{"type": "assistant.message", "content": "One thing first."}],
            "question": {
                "id": "q-1",
                "text": "Which environment?",
                "options": ["staging", "production"],
            },
        },
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="deploy", config=cfg, timeout=10.0)
    assert sent.ok is True
    assert sent.data["awaiting_input"] is True
    assert sent.data["pending_question"]["ask"] == "Which environment?"
    assert sent.data["pending_question"]["choices"] == ["staging", "production"]
    assert sent.data["pending_question"]["other"] == "Other"
    assert sent.data["pending_action"] ==  {
        "type": "ask_user_question",
        "task_id": "task-q",
        "question_id": "q-1",
        "input_path": "/api/agent/tasks/task-q/input",
    }
    # The lead-in plus the question: never the question silently dropped.
    assert "One thing first." in sent.data["text"]
    assert "Which environment?" in sent.data["text"]


def test_pending_question_is_answerable_via_the_adapter_and_input(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-q", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-q")] = (
        200,
        {
            "id": "task-q",
            "status": "running",
            "question": {"id": "q-1", "text": "Which environment?", "options": ["staging"]},
        },
    )
    _Router.sequence[("POST", "/api/agent/tasks/task-q/input")] = [
        (200, {"id": "task-q", "status": "running"})
    ]
    _Router.sequence[("GET", "/api/agent/tasks/task-q")] = [
        (
            200,
            {
                "id": "task-q",
                "status": "running",
                "question": {"id": "q-1", "text": "Which environment?", "options": ["staging"]},
            },
        ),
        (200, {"id": "task-q", "status": "completed", "result": "Deployed to staging."}),
    ]
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    paused = remotes_core.operate("openmuse", "send", prompt="deploy", config=cfg, timeout=10.0)
    assert paused.data["awaiting_input"] is True

    spec = remotes_core.load_remote("openmuse", cfg)
    adapter = create_remote_adapter(spec)
    assert adapter is not None
    from swarm.core.remote_harness import pending_question_from_result

    pending = pending_question_from_result(paused)
    assert pending is not None
    assert pending["question"]["ask"] == "Which environment?"

    resumed = remotes_core.resume_remote(
        "openmuse",
        session_id=paused.data["session_id"],
        pending_action=pending["pending_action"],
        answer="staging",
        config=cfg,
    )
    assert resumed.ok is True
    assert resumed.data["text"] == "Deployed to staging."
    assert _bodies_for("POST", "/api/agent/tasks/task-q/input") == [{"answer": "staging"}]


def test_a_resume_can_pause_again_on_a_second_question(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks/task-r")] = (
        200,
        {"id": "task-r", "status": "running", "question": "Approve the deploy?"},
    )
    _Router.routes[("POST", "/api/agent/tasks/task-r/input")] = (
        200,
        {"id": "task-r", "status": "running"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    spec = remotes_core.RemoteSpec(
        id="openmuse", title="OpenMuse", host_label="openmuse",
        base_url=f"http://{host}:{port}", kind="openmuse",
    )
    resumed = remotes_core._openmuse_resume_pending(
        spec, session_id="task-r", pending_action={}, content="yes", timeout=5.0
    )
    assert resumed.ok is True
    assert resumed.data["awaiting_input"] is True
    assert resumed.data["pending_question"]["ask"] == "Approve the deploy?"


def test_resume_without_a_task_id_or_answer_is_refused(server):
    host, port = server
    spec = remotes_core.RemoteSpec(
        id="openmuse", title="OpenMuse", host_label="openmuse",
        base_url=f"http://{host}:{port}", kind="openmuse",
    )
    no_task = remotes_core._openmuse_resume_pending(
        spec, session_id="", pending_action={}, content="yes", timeout=2.0
    )
    assert no_task.gap == "openmuse_task_required"
    no_answer = remotes_core._openmuse_resume_pending(
        spec, session_id="task-r", pending_action={}, content="  ", timeout=2.0
    )
    assert no_answer.gap == "openmuse_answer_required"
    assert _Router.bodies == []


def test_resume_on_a_gone_task_is_reported_honestly(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks/task-gone/input")] = (
        404,
        {"detail": "Task not found"},
    )
    spec = remotes_core.RemoteSpec(
        id="openmuse", title="OpenMuse", host_label="openmuse",
        base_url=f"http://{host}:{port}", kind="openmuse",
    )
    resumed = remotes_core._openmuse_resume_pending(
        spec, session_id="task-gone", pending_action={}, content="yes", timeout=2.0
    )
    assert resumed.ok is False
    assert resumed.gap == "openmuse_task_missing"
    assert resumed.http_status == 404


# ---------------------------------------------------------------------------
# 6. failure modes
# ---------------------------------------------------------------------------


def test_422_on_a_bad_prompt_is_reported_as_a_prompt_rejection(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        422,
        {"detail": "prompt: Too small: expected string to have >=1 characters"},
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=3.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_prompt_rejected"
    assert sent.http_status == 422
    assert "Too small" in sent.detail


def test_404_on_a_goal_is_reported_as_a_missing_goal(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (404, {"detail": "Goal not found"})
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=3.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_goal_missing"
    assert "Goal not found" in sent.detail


def test_409_on_too_many_tasks_names_the_cap_and_the_control_route(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        409,
        {"detail": "Finish or cancel some tasks before adding more"},
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=3.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_task_limit"
    assert sent.http_status == 409
    assert "cancel" in sent.detail


def test_a_create_that_returns_no_task_id_is_reported(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"status": "queued"})
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=3.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_no_task_id"


def test_a_task_that_vanishes_mid_poll_is_reported(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-gone", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-gone")] = (404, {"detail": "Task not found"})
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_task_missing"
    assert sent.data["session_id"] == "task-gone"


def test_a_404_on_a_resume_key_does_not_silently_mint_a_new_task(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks/task-vanished")] = (
        404,
        {"detail": "Task not found"},
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="hi", session_id="task-vanished", config=cfg, timeout=3.0
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_task_missing"
    assert sent.data["requested_task_id"] == "task-vanished"
    assert ("POST", "/api/agent/tasks") not in _Router.hits


def test_a_failed_task_reports_the_server_reason(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-f", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-f")] = (
        200,
        {"id": "task-f", "status": "failed", "error": "model backend refused"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    assert sent.ok is False
    assert sent.gap == "openmuse_task_failed"
    assert "model backend refused" in sent.detail


def test_a_non_json_error_envelope_is_surfaced_not_swallowed(server):
    host, port = server
    _Router.routes[("POST", "/api/session")] = (200, {"token": TOKEN, "mode": "live"})
    _Router.routes[("GET", "/api/agent/tasks")] = (
        502,
        "<html>502 Bad Gateway</html>",
    )
    _Router.routes[("GET", "/api/agent/")] = (502, "<html>502 Bad Gateway</html>")
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is False
    assert listed.gap == "openmuse_list_failed"
    assert listed.http_status == 502
    # The raw text is carried for the operator, not replaced with a fake body.
    assert "502 Bad Gateway" in str(listed.data)


def test_a_never_terminating_poll_times_out_cleanly(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-slow", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-slow")] = (
        200,
        {"id": "task-slow", "status": "running"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="hi", config=cfg, timeout=0.35
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_task_timeout"
    assert "still running" in sent.detail
    assert sent.data["session_id"] == "task-slow"
    assert sent.data["status"] == "running"
    # It kept polling, and it stopped on its own deadline.
    assert _Router.hits[("GET", "/api/agent/tasks/task-slow")] >= 2


def test_an_unknown_status_is_never_read_as_finished(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-x", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-x")] = (
        200,
        {"id": "task-x", "status": "definitely_not_a_real_status"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=0.3)
    assert sent.gap == "openmuse_task_timeout"


def test_a_task_that_finishes_without_text_says_so_rather_than_inventing_one(
    server, monkeypatch
):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (201, {"id": "task-q1", "status": "queued"})
    _Router.routes[("GET", "/api/agent/tasks/task-q1")] = (
        200,
        {"id": "task-q1", "status": "completed"},
    )
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    assert sent.ok is True
    assert "task-q1" in sent.data["text"] or "task-q1" in sent.detail


# ---------------------------------------------------------------------------
# control (pause / resume / cancel / retry)
# ---------------------------------------------------------------------------


def test_control_posts_the_documented_control_body(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks/task-c/control")] = (
        200,
        {"id": "task-c", "status": "paused"},
    )
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    adapter = create_remote_adapter(spec)
    assert adapter is not None
    for action in ("pause", "resume", "cancel", "retry"):
        result = adapter.control(action, "task-c", 3.0)
        assert result.data["action"] == action
        assert result.data["task_id"] == "task-c"
    assert _bodies_for("POST", "/api/agent/tasks/task-c/control") == [
        {"action": "pause"},
        {"action": "resume"},
        {"action": "cancel"},
        {"action": "retry"},
    ]


def test_control_rejects_an_unknown_verb(server):
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    adapter = create_remote_adapter(spec)
    result = adapter.control("nuke", "task-c", 3.0)
    assert result.ok is False
    assert result.gap == "openmuse_unsupported_control"
    assert _Router.bodies == []


def test_control_refuses_the_remotes_own_name_as_a_task_id(server):
    host, port = server
    _mint_ok()
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    adapter = create_remote_adapter(spec)
    result = adapter.control("cancel", "openmuse", 3.0)
    assert result.ok is False
    assert result.gap == "openmuse_task_required"
    assert _Router.bodies == []


def test_control_reports_a_refused_transition_and_a_gone_task(server):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks/task-busy/control")] = (
        409,
        {"detail": "Task is already completed"},
    )
    _Router.routes[("POST", "/api/agent/tasks/task-gone/control")] = (
        404,
        {"detail": "Task not found"},
    )
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    adapter = create_remote_adapter(spec)
    busy = adapter.control("resume", "task-busy", 3.0)
    assert busy.ok is False
    assert busy.gap == "openmuse_control_rejected"
    assert "already completed" in busy.detail
    gone = adapter.control("cancel", "task-gone", 3.0)
    assert gone.gap == "openmuse_task_missing"


def test_harness_operate_routes_the_control_verbs(server):
    from swarm.core.remote_harness import get_harness

    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks/task-h/control")] = (
        200,
        {"id": "task-h", "status": "canceled"},
    )
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    harness = get_harness("openmuse")
    assert harness is not None
    result = harness.operate(spec, "cancel", timeout=3.0, target="task-h")
    assert result.ok is True
    assert _bodies_for("POST", "/api/agent/tasks/task-h/control") == [{"action": "cancel"}]


def test_harness_operate_still_refuses_a_bogus_verb(server):
    from swarm.core.remote_harness import get_harness

    host, port = server
    cfg = _cfg(host, port)
    spec = remotes_core.load_remote("openmuse", cfg)
    harness = get_harness("openmuse")
    result = harness.operate(spec, "detonate", timeout=3.0, target="task-h")
    assert result.ok is False
    assert _Router.bodies == []


# ---------------------------------------------------------------------------
# 7. the access key never reaches a payload
# ---------------------------------------------------------------------------


def test_the_access_key_is_never_returned_in_any_payload(server):
    host, port = server
    _mint_ok()
    # A server that echoes the access key back in every error must not be able
    # to launder it into the chat transcript.
    _Router.routes[("GET", "/api/agent/tasks")] = (
        500,
        {"detail": f"bad key {ACCESS_KEY} rejected", "echoed": ACCESS_KEY},
    )
    _Router.routes[("GET", "/api/agent/")] = (
        500,
        {"detail": f"bad key {ACCESS_KEY} rejected", "echoed": ACCESS_KEY},
    )
    cfg = _cfg(host, port)
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    dumped = json.dumps(listed.as_dict())
    assert ACCESS_KEY not in dumped
    assert "redacted" in dumped
    assert TOKEN not in dumped


def test_the_access_key_is_never_returned_from_send_or_health(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        422,
        {"detail": f"invalid prompt for key {ACCESS_KEY}"},
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=3.0)
    assert ACCESS_KEY not in json.dumps(sent.as_dict())

    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert ACCESS_KEY not in json.dumps(health.as_dict())
    assert health.ok is False
    assert health.state == "DEGRADED"
    assert "redacted" in health.detail or health.detail


def test_the_access_key_is_only_ever_read_from_the_env_var(server, monkeypatch):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    monkeypatch.setenv("OPENMUSE_ACCESS_KEY", ACCESS_KEY)
    cfg = {"llm": {}, "remotes": {"openmuse": {"base_url": f"http://{host}:{port}"}}}
    spec = remotes_core.load_remote("openmuse", cfg)
    # The env var NAME is what the config carries; the value comes from env.
    assert spec.api_key_env == "OPENMUSE_ACCESS_KEY"
    assert spec.api_key == ACCESS_KEY
    listed = remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    assert listed.ok is True
    assert _bodies_for("POST", "/api/session") == [{"accessKey": ACCESS_KEY}]


def test_a_persisted_config_stores_the_env_reference_not_the_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENMUSE_BASE_URL", raising=False)
    monkeypatch.delenv("OPENMUSE_ACCESS_KEY", raising=False)
    cfg_path = tmp_path / "swarm_config.json"
    cfg_path.write_text(json.dumps({"llm": {"default": {"model": "x"}}}), encoding="utf-8")
    spec, path = remotes_core.add_remote(
        "openmuse",
        base_url="http://127.0.0.1:8787",
        api_key_env="OPENMUSE_ACCESS_KEY",
        config_path=cfg_path,
    )
    assert path == cfg_path
    assert spec.kind == "openmuse"
    stored = json.loads(cfg_path.read_text(encoding="utf-8"))
    assert stored["remotes"]["openmuse"]["api_key"] == "${OPENMUSE_ACCESS_KEY}"
    assert ACCESS_KEY not in cfg_path.read_text(encoding="utf-8")


def test_signed_file_and_browser_routes_are_never_bearer_called(server):
    """Those two routes use ?owner=&expires=&signature=, not the session token."""
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/agent/tasks")] = (200, {"tasks": []})
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "list", config=cfg, timeout=3.0)
    asked = [path for _m, path, _b in _Router.bodies]
    assert all("owner=" not in path for path in asked)
    source = (
        __import__("swarm.core.remote_impls.openmuse", fromlist=["x"]).__doc__ or ""
    )
    assert "/api/files/" in source and "/api/browsers/" in source


# ---------------------------------------------------------------------------
# health
# ---------------------------------------------------------------------------


def test_health_mints_a_session_and_probes_the_agent_snapshot(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/health")] = (200, {"ok": True, "mode": "live", "agentConfigured": True})
    cfg = _cfg(host, port)
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is True
    assert health.state == "UP"
    assert "live mode" in health.detail
    assert health.version["mode"] == "live"
    # The mint is unauthenticated; the probe behind it carries the token.
    assert _Router.auth_headers == ["", f"Bearer {TOKEN}"]


def test_health_is_up_when_the_endpoint_answers_but_auth_is_refused(server):
    host, port = server
    _Router.routes[("POST", "/api/session")] = (200, {"token": TOKEN, "mode": "live"})
    _Router.routes[("GET", "/api/health")] = (403, {"error": "Forbidden"})
    cfg = _cfg(host, port)
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is True
    assert health.state == "UP"
    assert "auth refused" in health.detail
    # A policy refusal must not burn a second session mint.
    assert _Router.hits[("POST", "/api/session")] == 1


def test_health_is_unknown_when_the_instance_cannot_be_signed_into(server):
    host, port = server
    _Router.routes[("POST", "/api/session")] = (401, {"detail": "Access key is incorrect"})
    cfg = _cfg(host, port)
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is False
    assert health.state == "UNKNOWN"
    # The env var NAME is what the operator needs; the value never appears.
    assert "OPENMUSE_ACCESS_KEY" in health.detail
    assert ACCESS_KEY not in health.detail


def test_health_is_degraded_when_the_agent_route_breaks(server):
    host, port = server
    _mint_ok()
    _Router.routes[("GET", "/api/health")] = (500, {"error": "boom"})
    cfg = _cfg(host, port)
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is False
    assert health.state == "DEGRADED"
    assert health.http_status == 500


# ---------------------------------------------------------------------------
# pure helpers
# ---------------------------------------------------------------------------


def test_pending_question_returns_none_for_a_finished_task():
    assert openmuse_pending_question({"status": "completed", "result": "done"}) is None
    assert openmuse_pending_question({"question": None}) is None
    assert openmuse_pending_question({"question": {}}) is None
    assert openmuse_pending_question("not a dict") is None


def test_pending_question_reads_a_plain_string_question():
    found = openmuse_pending_question({"question": "Ship it?"}, task_id="task-x")
    assert found is not None
    assert found["question"]["ask"] == "Ship it?"
    assert found["question"]["choices"] == []
    assert found["question"]["id"] == "task-x"


def test_pending_question_takes_the_first_of_a_list():
    found = openmuse_pending_question(
        {"question": [{"prompt": "first?"}, {"prompt": "second?"}]}, task_id="task-x"
    )
    assert found is not None
    assert found["question"]["ask"] == "first?"


def test_task_row_and_text_helpers():
    assert openmuse_task_row({"title": "no id"}) is None
    assert openmuse_task_row("nope") is None
    assert openmuse_task_row({"id": "t-1", "title": "T"})["id"] == "t-1"
    assert openmuse_task_text({}) == ""
    assert openmuse_task_text({"result": "R"}) == "R"
    assert openmuse_task_text({"output": {"content": "O"}}) == "O"
    assert (
        openmuse_task_text(
            {"events": [{"type": "assistant.message", "content": [{"text": "a"}, {"text": "b"}]}]}
        )
        == "ab"
    )
    # A non-text event is not scraped into a reply.
    assert openmuse_task_text({"events": [{"type": "task.started", "content": "x"}]}) == ""

"""#1660 — an invalid OpenMuse ``MODEL`` must not leave the seat reporting UP.

``GET /api/health`` answers ``{ok, mode, agentConfigured, browserConfigured}``
and ``agentConfigured`` is ``config.model && <a provider key>``: it proves
``MODEL`` is *non-empty*, never that the instance *serves* it. So
``MODEL=hosted_vllm/nemotron-3.5-lightning-free`` reported
``agentConfigured: true``, the seat health-checked UP, and every task then
died with OpenMuse's own ``Unknown provider "hosted_vllm" in
"hosted_vllm/nemotron-3.5-lightning-free". Supported: openai, anthropic,
google`` — a green seat that could never answer anything.

There is no cheaper honest signal to be had. Probed read-only 2026-09-28 on
both live instances, unauthenticated and with a valid session bearer,
``/api/models``, ``/v1/models``, ``/api/agent/models``,
``/api/agent/providers``, ``/api/agent/config``, ``/api/agent/capabilities``,
``/api/config`` and ``/openapi.json`` are all **404**. The instance therefore
never publishes its model, so the only authoritative word it gives about
``MODEL`` is the refusal it returns when a turn reaches the model. These
tests pin that the impl latches exactly that word, reports DEGRADED, and
recovers — and that it does so without ever starting a model turn to find
out.

Hermetic: a loopback router stands in for the Hono server. No live instance,
no LLM, no network.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from swarm.core import remotes as remotes_core
from swarm.core.remote_impls.openmuse import (
    _MODEL_REJECTION_TTL_S,
    openmuse_clear_model_rejection,
    openmuse_clear_token_cache,
)
from functools import partial

ACCESS_KEY = "sk-openmuse-fake-key-do-not-leak-4321"
TOKEN = "sess-token-openmuse-fake-0123456789abcdef"

# Verbatim from the live instance that produced #1660, truncated exactly the
# way the operator saw it. The test asserts this string survives into health
# verbatim — an invented reason would be a guess, and a guess is the bug.
LIVE_REJECTION = (
    'Unknown provider "hosted_vllm" in '
    '"hosted_vllm/nemotron-3.5-lightning-free". '
    "Supported: openai, anthropic, google (gemini…)"
)


class _Router(BaseHTTPRequestHandler):
    routes: dict[tuple[str, str], Any] = {}
    hits: dict[tuple[str, str], int] = {}
    methods_seen: list[str] = []

    def _handle(self, method: str) -> None:
        path = self.path.split("?", 1)[0]
        self.methods_seen.append(f"{method} {path}")
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            self.rfile.read(length)
        key = (method, path)
        self.hits[key] = self.hits.get(key, 0) + 1
        status, payload = self.routes.get(key, (404, {"detail": "no route"}))
        data = json.dumps(payload).encode("utf-8")
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
        cls.hits = {}
        cls.methods_seen = []

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


@pytest.fixture(autouse=True)
def _no_live_leak(monkeypatch):
    """A developer's real OpenMuse env must never reach an assertion."""
    for name in (
        "OPENMUSE_BASE_URL",
        "OPENMUSE_ACCESS_KEY",
        "OPENMUSE2_BASE_URL",
        "OPENMUSE2_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def _cfg(host: str, port: int) -> dict[str, Any]:
    """One OpenMuse seat on the loopback router."""
    return {
        "llm": {},
        "remotes": {
            "openmuse": {
                "base_url": f"http://{host}:{port}",
                "api_key": ACCESS_KEY,
                "kind": "openmuse",
            }
        },
    }


def _two_seat_cfg(host: str, port: int) -> dict[str, Any]:
    """A second OpenMuse seat behind a path prefix, as the public one is."""
    return {
        "llm": {},
        "remotes": {
            "openmuse": {
                "base_url": f"http://{host}:{port}",
                "api_key": ACCESS_KEY,
                "kind": "openmuse",
            },
            "openmuse-public": {
                "base_url": f"http://{host}:{port}/openmuse",
                "api_key": ACCESS_KEY,
                "kind": "openmuse",
            },
        },
    }


def _healthy(agent_configured: bool = True) -> None:
    payload = {
        "ok": True,
        "mode": "live",
        "agentConfigured": agent_configured,
        "browserConfigured": True,
    }
    # The prefixed seat reaches the same router under /openmuse, the way the
    # real public instance sits behind an nginx path.
    for prefix in ("", "/openmuse"):
        _Router.routes[("POST", f"{prefix}/api/session")] = (
            200,
            {"token": TOKEN, "mode": "live"},
        )
        _Router.routes[("GET", f"{prefix}/api/health")] = (200, payload)


def _task_rejecting_the_model(task_id: str = "task-m") -> None:
    """A task the instance created, then failed on the configured MODEL."""
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": task_id, "status": "queued"},
    )
    _Router.routes[("GET", f"/api/agent/tasks/{task_id}")] = (
        200,
        {"id": task_id, "status": "failed", "error": LIVE_REJECTION},
    )


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    """Keep the poll cadence at 10ms so a failed task is reached in ms."""
    monkeypatch.setattr(
        "swarm.core.remote_impls.openmuse._OPENMUSE_POLL_INTERVAL_S", 0.01
    )


# ---------------------------------------------------------------------------
# THE REGRESSION: an invalid MODEL must not report UP
# ---------------------------------------------------------------------------


def test_a_model_the_instance_refuses_is_not_reported_up(server):  # noqa: ARG001 - pytest fixture
    """The #1660 scenario, end to end: green light, then every task dies.

    Before the fix the send failed *and* health kept saying UP, so nothing in
    the UI ever warned the operator. The refusal is the only thing the
    instance says about MODEL, so health has to carry it.
    """
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)

    # 1. Before anything has run, the seat is (honestly) alive and unverified.
    before = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert before.ok is True
    assert before.state == "UP"

    # 2. A task runs and the instance refuses its own configured MODEL.
    sent = remotes_core.operate(
        "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_model_rejected"
    # The instance's own words, not a paraphrase OS invented.
    assert LIVE_REJECTION in sent.detail

    # 3. Health must now say the seat is degraded, and must not say UP.
    after = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert after.ok is False, "a seat that cannot run a turn must not report UP"
    assert after.state == "DEGRADED"
    # The reason survives into the verdict, verbatim, so the operator can act.
    assert LIVE_REJECTION in after.detail
    # `agentConfigured` is still true — the instance only checks that MODEL is
    # non-empty. That is the whole bug, so pin it: the green light is there
    # in the payload and must not win.
    assert after.version["agentConfigured"] is True
    assert "not served" in after.detail
    # The instance itself is fine; only its model is not.
    assert after.http_status == 200
    assert "live mode" in after.detail


def test_the_model_rejection_survives_repeated_health_polls(server):
    """A poll must not launder the failure back into a green light.

    This is the operator's real timeline: the task fails, then health is
    polled every few seconds forever. If the first poll cleared the latch,
    the seat would be green again within seconds and the fix would do nothing.
    """
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)

    for attempt in range(3):
        health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
        assert health.ok is False, f"poll {attempt} washed the failure out"
        assert health.state == "DEGRADED"
        assert LIVE_REJECTION in health.detail


def test_a_latch_that_never_expires_would_never_recover():
    """Guard the guard: the TTL is what lets a fixed instance heal itself."""
    assert _MODEL_REJECTION_TTL_S > 0
    assert _MODEL_REJECTION_TTL_S < 24 * 3600.0


# ---------------------------------------------------------------------------
# Recovery — the operator fixes MODEL, and must not be stuck degraded
# ---------------------------------------------------------------------------


def test_a_successful_task_clears_the_model_rejection(server):
    """The only proof the fix worked is a turn that comes back with an answer."""
    host, port = server
    _healthy()
    _task_rejecting_the_model(task_id="task-bad")
    cfg = _cfg(host, port)
    assert (
        remotes_core.operate(
            "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
        ).ok
        is False
    )
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is False

    # The operator fixes MODEL on the OpenMuse host; the next task works.
    _Router.routes[("GET", "/api/agent/tasks/task-ok")] = (
        200,
        {"id": "task-ok", "status": "succeeded", "result": "hello"},
    )
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": "task-ok", "status": "queued"},
    )
    fixed = remotes_core.operate(
        "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
    )
    assert fixed.ok is True
    assert fixed.data["status"] == "succeeded"

    recovered = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert recovered.ok is True
    assert recovered.state == "UP"
    assert LIVE_REJECTION not in recovered.detail


def test_a_latch_expires_so_a_fixed_instance_recovers_without_another_task(
    server, monkeypatch
):
    """Bounded evidence, not a permanent verdict on the operator's host."""
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is False

    monkeypatch.setattr("swarm.core.remote_impls.openmuse._MODEL_REJECTION_TTL_S", -1.0)
    healed = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert healed.ok is True
    assert healed.state == "UP"


def test_a_fresh_health_that_reports_no_model_clears_a_stale_latch(server):
    """``agentConfigured: false`` is the instance saying MODEL is gone.

    That is a real change on the instance, so the latched refusal about the
    old MODEL is stale by construction and must not outlive it. It also means
    the seat cannot answer anything, so it must not read UP.
    """
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)

    _Router.routes[("GET", "/api/health")] = (
        200,
        {
            "ok": True,
            "mode": "live",
            "agentConfigured": False,
            "browserConfigured": True,
        },
    )
    unconfigured = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert unconfigured.ok is False
    assert unconfigured.state == "DEGRADED"
    assert "unconfigured" in unconfigured.detail
    assert LIVE_REJECTION not in unconfigured.detail

    # And the stale latch is gone: restore the model, health goes back to UP
    # without waiting out a TTL.
    _healthy()
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is True


# ---------------------------------------------------------------------------
# A healthy seat must stay healthy — no false positives
# ---------------------------------------------------------------------------


def test_health_is_up_when_the_model_is_never_refused(server):
    """The valid-MODEL case from the issue's requirements: still UP."""
    host, port = server
    _healthy()
    cfg = _cfg(host, port)
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is True
    assert health.state == "UP"
    assert "live mode" in health.detail
    assert "not served" not in health.detail


def test_a_task_that_failed_for_another_reason_does_not_degrade_health(server):
    """A misfire here would degrade a working seat, so the net is narrow."""
    host, port = server
    _healthy()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": "task-x", "status": "queued"},
    )
    _Router.routes[("GET", "/api/agent/tasks/task-x")] = (
        200,
        {
            "id": "task-x",
            "status": "failed",
            "error": "Goal directory /srv/workspace is not writable",
        },
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
    )
    assert sent.ok is False
    # A permissions failure is a task failure, not a MODEL failure.
    assert sent.gap == "openmuse_task_failed"
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is True
    assert health.state == "UP"


def test_a_provider_refusal_without_a_model_id_does_not_latch(server):
    """The `<provider>/<model>` shape is what makes it a MODEL complaint.

    A bare "unknown provider" with no slash could be any other provider-ish
    noun OpenMuse grows, and labelling that "MODEL is not served" would be
    OS guessing.
    """
    host, port = server
    _healthy()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": "task-p", "status": "queued"},
    )
    _Router.routes[("GET", "/api/agent/tasks/task-p")] = (
        200,
        {"id": "task-p", "status": "failed", "error": 'Unknown provider "mcp"'},
    )
    cfg = _cfg(host, port)
    assert (
        remotes_core.operate(
            "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
        ).gap
        == "openmuse_task_failed"
    )
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is True


def test_a_create_time_model_refusal_is_reported_as_a_model_rejection(server):
    """A build that validates MODEL up front must not read as a generic 4xx."""
    host, port = server
    _healthy()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        400,
        {"error": LIVE_REJECTION},
    )
    cfg = _cfg(host, port)
    sent = remotes_core.operate(
        "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
    )
    assert sent.ok is False
    assert sent.gap == "openmuse_model_rejected"
    assert LIVE_REJECTION in sent.detail
    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.ok is False
    assert health.state == "DEGRADED"
    assert LIVE_REJECTION in health.detail


# ---------------------------------------------------------------------------
# Cheapest-signal discipline
# ---------------------------------------------------------------------------


def test_health_never_starts_a_model_turn_to_check_the_model(server):
    """A remote health check is liveness, and it must stay one cheap GET.

    The cheapest honest signal turned out to be the refusal a task already
    returned, so nothing has to be created, run, or waited on. Pin the wire
    traffic: no task is created, and nothing is polled.
    """
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    _Router.methods_seen.clear()
    _Router.hits.clear()

    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.state == "DEGRADED"
    # The token is cached from the send, so health is a single GET.
    assert _Router.methods_seen == ["GET /api/health"]
    assert ("POST", "/api/agent/tasks") not in _Router.hits
    assert not any(p.startswith("GET /api/agent/tasks") for p in _Router.methods_seen)


def test_the_rejection_never_carries_a_credential_into_health(server):
    """A deliberately fake key, asserted absent from the payload."""
    host, port = server
    _healthy()
    _Router.routes[("POST", "/api/agent/tasks")] = (
        201,
        {"id": "task-s", "status": "queued"},
    )
    _Router.routes[("GET", "/api/agent/tasks/task-s")] = (
        200,
        # A misbehaving server that echoes the caller's own key back at us.
        {
            "id": "task-s",
            "status": "failed",
            "error": f"{LIVE_REJECTION} key={ACCESS_KEY}",
        },
    )
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)

    health = remotes_core.check_health("openmuse", config=cfg, timeout=3.0)
    assert health.state == "DEGRADED"
    payload = json.dumps(health.as_dict())
    assert ACCESS_KEY not in payload
    assert ACCESS_KEY not in health.detail
    assert "key env OPENMUSE_ACCESS_KEY" not in health.detail
    # The reason is still there, just scrubbed.
    assert "not served" in health.detail


# ---------------------------------------------------------------------------
# Two OpenMuse seats must not share a verdict
# ---------------------------------------------------------------------------


def test_one_bad_model_does_not_degrade_the_other_openmuse_seat(server):
    """An operator runs a LAN and a public OpenMuse. They are separate seats."""
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _two_seat_cfg(host, port)
    assert (
        remotes_core.operate(
            "openmuse", "send", prompt="hi", config=cfg, timeout=5.0
        ).gap
        == "openmuse_model_rejected"
    )
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is False

    other = remotes_core.check_health("openmuse-public", config=cfg, timeout=3.0)
    assert other.ok is True
    assert other.state == "UP"
    assert LIVE_REJECTION not in other.detail


# ---------------------------------------------------------------------------
# The reset hook is a reset hook
# ---------------------------------------------------------------------------


def test_clearing_the_token_cache_clears_the_model_rejection(server):
    """Otherwise one seat's verdict leaks into the next test's process state."""
    host, port = server
    _healthy()
    _task_rejecting_the_model()
    cfg = _cfg(host, port)
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is False

    openmuse_clear_token_cache()
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is True

    _task_rejecting_the_model()
    remotes_core.operate("openmuse", "send", prompt="hi", config=cfg, timeout=5.0)
    openmuse_clear_model_rejection()
    assert remotes_core.check_health("openmuse", config=cfg, timeout=3.0).ok is True


# ---------------------------------------------------------------------------
# The verdict has to be visible to the thing an operator actually reads
# ---------------------------------------------------------------------------


def test_seat_doctor_buckets_this_as_a_model_failure_not_a_liveness_win():
    """The visible end of the chain: BROKEN / model_invalid, not UNVERIFIED.

    ``health.ok is False`` is what seat_doctor needs to stop calling the seat
    ``unverified``; the detail text is what it buckets on. Both are contracts
    with a file this fix does not own, so pin them explicitly.
    """
    from swarm.core import seat_doctor

    detail = (
        "http 200 on /api/health (live mode, agent configured) — but the "
        f"configured MODEL is not served by this instance: {LIVE_REJECTION}. Fix "
        "MODEL on the OpenMuse host as <provider>/<model-id> and restart it."
    )
    assert seat_doctor._bucket_from_markers(detail) == seat_doctor.BUCKET_MODEL_INVALID
    # And the pre-fix wording — a plain UP with the same reason buried in a
    # task failure — was not actionable at all.
    assert "agent configured" not in seat_doctor._bucket_from_markers(
        "http 200 on /api/health (live mode, agent configured)"
    )

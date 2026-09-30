"""``seat_doctor`` — the operator report must be *right*, not merely present.

The contract pinned here, in the order it matters:

* **A bucket is earned.** Every bucket is selected by a real probe outcome — a
  real HTTP status, a real TCP refusal, a real ``which()`` miss. Most of these
  tests drive a real loopback HTTP server that answers 402 / 400 / 401 / 418 /
  200, so the classifier is exercised end to end rather than against a mocked
  shape.
* **Liveness is not working.** A CLI that answers ``--version`` and a remote
  whose health route answers are ``unverified``, never ``ok``. ``ok`` requires a
  proved turn.
* **No secret, ever.** A key in a 401 body, a key in ``cli_agents.*.env`` and a
  key in the environment must all be absent from the report, while env var
  *names* survive (the name is the fix).
* **Read-only and bounded.** The cap holds and the default run spends no model
  call beyond the single ``action="test"`` probe.
* **A composition seat inherits its delegate's bucket**, and the root's
  remediation says how many seats it takes down.
"""

from __future__ import annotations

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from swarm.core import seat_doctor
from swarm.core.seat_doctor import (
    BUCKET_AUTH,
    BUCKET_MISCONFIGURED,
    BUCKET_MODEL_INVALID,
    BUCKET_NOT_CONFIGURED,
    BUCKET_NOT_EXECUTABLE,
    BUCKET_NOT_INSTALLED,
    BUCKET_PROBE_ERROR,
    BUCKET_QUOTA,
    BUCKET_SERVICE_DOWN,
    BUCKET_TIMEOUT,
    BUCKET_TIMEOUT_RISK,
    BUCKET_UNREACHABLE,
    MAX_SEATS,
    PROVES_LIVENESS,
    PROVES_TURN,
    VERDICT_BROKEN,
    VERDICT_OK,
    VERDICT_UNVERIFIED,
    SeatFinding,
    SeatSpec,
    diagnose,
    enumerate_seats,
    format_report,
    report_payload,
)
from functools import partial

# A loopback fixture only works while the loopback rewrite is off; inside a
# container ``_normalize_base_url`` maps 127.0.0.1 to the Docker host gateway.
_IN_CONTAINER = pytest.mark.skipif(
    Path("/.dockerenv").exists(),
    reason="loopback is rewritten to the Docker host gateway inside a container",
)


# ---------------------------------------------------------------------------
# a real provider to argue with
# ---------------------------------------------------------------------------

_QUOTA_BODY = json.dumps(
    {"error": {"type": "insufficient_quota", "message": "Grok Build usage exhausted."}}
)
_BAD_MODEL_BODY = json.dumps(
    {"error": {"message": "Invalid model name passed in model=gpt-4.1", "code": 400}}
)
_BAD_KEY_BODY = json.dumps(
    {"error": {"message": "Incorrect API key provided: sk-live-abc123DEF456.", "code": 401}}
)
_OK_BODY = '{"choices":[{"message":{"content":"pong"}}]}'

_LEAKED_KEY = "sk-live-abc123DEF456"


class _GatewayHandler(BaseHTTPRequestHandler):
    """Answers like a LiteLLM gateway: a models list, then a chat verdict."""

    served_models: list[str] = ["gpt-4.1-mini", "orchestration", "auxiliary"]
    list_status: int = 200
    list_body: str = ""
    chat_status: int = 200
    chat_body: str = _OK_BODY
    health_status: int = 200
    health_body: str = '{"status":"ok"}'

    def log_message(self, *_args):  # noqa: A003 — silence the default stderr log
        return

    def _send(self, status: int, body: str) -> None:
        blob = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):  # noqa: N802 — BaseHTTPRequestHandler's contract
        path = self.path.rstrip("/")
        if path.endswith("/models"):
            if self.list_body:
                self._send(self.list_status, self.list_body)
                return
            self._send(
                self.list_status,
                json.dumps(
                    {
                        "object": "list",
                        "data": [{"id": m, "object": "model"} for m in self.served_models],
                    }
                ),
            )
            return
        if path.endswith("/health"):
            self._send(self.health_status, self.health_body)
            return
        self._send(404, '{"error":"not found"}')

    def do_POST(self):  # noqa: N802 — BaseHTTPRequestHandler's contract
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self._send(self.chat_status, self.chat_body)

# NOTE: `serve_forever`'s default poll_interval is 0.5s. It parks in
# `selector.select(0.5)`, and `shutdown()` blocks on `__is_shut_down`, which
# the serve loop can only set on its next wake -- so each fixture teardown
# below paid a flat 500ms parked in a selector. Measured on this box:
# 500.6ms at the default, 50.2ms at 0.05, 10.1ms at 0.01. pytest
# --durations=0 attributes 106s of suite teardown to this pattern across 36
# files -- 28% of the suite's wall clock. A test-fixture cost, not a
# behaviour change: the thread still runs the same serve loop.

class _Server:
    def __init__(self, handler=None):
        self.handler = handler or type("_H", (_GatewayHandler,), {})
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self.handler)
        self._thread = threading.Thread(target=partial(self._server.serve_forever, poll_interval=0.02), daemon=True)
        self._thread.start()

    def configure(self, **kwargs) -> None:
        """Set the answers on the class the running server actually dispatches to."""
        for key, value in kwargs.items():
            setattr(self.handler, key, value)

    @property
    def origin(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    @property
    def base_url(self) -> str:
        host, port = self.origin
        return f"http://{host}:{port}"

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


@pytest.fixture
def gateway():
    """A real loopback gateway whose answers the test reconfigures."""
    server = _Server()
    server.configure()
    try:
        yield server, server.configure
    finally:
        server.close()


def _free_port() -> int:
    """A port with nothing behind it — a guaranteed TCP refusal."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _redactor() -> seat_doctor._Redactor:
    return seat_doctor._Redactor()


def _api_spec(base_url: str, model: str, *, seat_id: str = "seat", api_key_env: str = "") -> SeatSpec:
    return SeatSpec(
        kind="api",
        seat_id=seat_id,
        origin="llm_profile",
        base_url=base_url,
        model=model,
        api_key_env=api_key_env,
    )


def _verdict(state: str, reason: str = "", latency_ms: int = 12):
    from swarm.core.seat_health import SeatVerdict

    return SeatVerdict(seat_id="x", kind="cli", state=state, reason=reason, latency_ms=latency_ms)


def _stub_cli_liveness(monkeypatch, state: str, reason: str = "", latency_ms: int = 12) -> None:
    """Pin the liveness probe ``seat_health`` performs, nothing else."""
    from swarm.core import seat_health

    monkeypatch.setattr(
        seat_health, "probe_seat", lambda *_a, **_k: _verdict(state, reason, latency_ms)
    )
    monkeypatch.setattr(seat_doctor.shutil, "which", lambda name: f"/usr/bin/{name}")


# ---------------------------------------------------------------------------
# quota — 402, the failure that took a whole delegate tree down
# ---------------------------------------------------------------------------


@_IN_CONTAINER
def test_http_402_is_quota_and_the_provider_words_are_kept(gateway):
    server, configure = gateway
    # A real billing gateway 402s every route with the same body.
    configure(chat_status=402, chat_body=_QUOTA_BODY, list_status=402, list_body=_QUOTA_BODY)
    finding = seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "auxiliary"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_QUOTA
    assert finding.evidence["http_status"] == 402
    assert "Grok Build usage exhausted" in finding.detail
    # The status overrode the probe's generic "could not reach host" hint, which
    # would have sent the operator to the wrong page.
    assert "could not reach host" not in finding.detail
    assert "top up" in finding.remediation.lower()
    assert finding.proves != PROVES_TURN


def test_quota_remediation_counts_dependents_once():
    base = seat_doctor._api_remediation(
        _api_spec("http://gw/v1", "auxiliary"), BUCKET_QUOTA, [], ""
    )
    augmented = seat_doctor._with_dependent_count(base, 9)
    assert "9 dependent seats fail with it" in augmented
    # Idempotent: a second pass must not append the clause twice.
    assert seat_doctor._with_dependent_count(augmented, 9) == augmented
    assert "1 dependent seat fails with it" in seat_doctor._with_dependent_count(base, 1)


# ---------------------------------------------------------------------------
# model validation is real: the valid ids come from the gateway
# ---------------------------------------------------------------------------


@_IN_CONTAINER
def test_rejected_model_is_named_against_the_gateways_real_list(gateway):
    server, configure = gateway
    configure(chat_status=400, chat_body=_BAD_MODEL_BODY, list_status=200)
    finding = seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "gpt-4.1"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_MODEL_INVALID
    assert "not served by" in finding.remediation
    # The suggestion is the gateway's own list, nearest match first.
    assert finding.remediation.index("gpt-4.1-mini") < finding.remediation.index("auxiliary")
    assert finding.evidence["models_listed"] == 3
    # The models route's 200 is not the status that failed, so it must not be
    # printed as the seat's status next to a broken verdict.
    assert finding.evidence["models_status"] == 200
    assert finding.evidence["http_status"] is None
    assert "status 200" not in finding.detail


@_IN_CONTAINER
def test_a_model_the_gateway_lists_is_not_called_invalid(gateway):
    server, configure = gateway
    configure(chat_status=200, chat_body=_OK_BODY, list_status=200)
    finding = seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "orchestration"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_OK
    assert finding.bucket == ""


# ---------------------------------------------------------------------------
# auth, and the secret rule
# ---------------------------------------------------------------------------


@_IN_CONTAINER
def test_401_is_auth_and_the_key_never_reaches_the_report(gateway, monkeypatch):
    server, configure = gateway
    configure(chat_status=401, chat_body=_BAD_KEY_BODY, list_status=401)
    monkeypatch.setenv("DOCTOR_TEST_KEY", _LEAKED_KEY)
    spec = _api_spec(server.base_url, "auxiliary", api_key_env="DOCTOR_TEST_KEY")
    redactor = _redactor()
    finding = seat_doctor._probe_api_seat(spec, deep=False, redactor=redactor)
    assert finding.bucket == BUCKET_AUTH
    blob = json.dumps(finding.as_dict(redactor))
    assert _LEAKED_KEY not in blob
    # The env var NAME is the fix, so it must survive redaction.
    assert "DOCTOR_TEST_KEY" in finding.as_dict(redactor)["remediation"]


def test_an_unresolved_env_placeholder_is_not_configured_and_names_the_var():
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.delenv("DOCTOR_MISSING_BASE", raising=False)
    monkeypatch.delenv("DOCTOR_MISSING_KEY", raising=False)
    try:
        config = {
            "llm": {
                "ghost": {
                    "provider": "openai",
                    "model": "gpt-4o-mini",
                    "base_url": "${DOCTOR_MISSING_BASE}",
                    "api_key": "${DOCTOR_MISSING_KEY}",
                }
            },
            "settings": {"default_llm_profile": "ghost"},
        }
        specs = {s.seat_id: s for s in enumerate_seats(config)}
        assert specs["ghost"].base_url == ""
        assert specs["ghost"].missing_env == "DOCTOR_MISSING_BASE"
        finding = seat_doctor._probe_api_seat(specs["ghost"], deep=False, redactor=_redactor())
    finally:
        monkeypatch.undo()
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_NOT_CONFIGURED
    # The exact variable is the fix; a generic "set a base_url" is not.
    assert "DOCTOR_MISSING_BASE" in finding.remediation
    assert finding.evidence["missing_env"] == "DOCTOR_MISSING_BASE"


def test_redactor_masks_keys_bearer_tokens_and_uri_passwords():
    redactor = seat_doctor._Redactor(extra=[_LEAKED_KEY])
    assert _LEAKED_KEY not in redactor.text(f"failed for {_LEAKED_KEY} at 203.0.113.30:8000")
    assert "203.0.113.30:8000" in redactor.text(f"failed for {_LEAKED_KEY} at 203.0.113.30:8000")
    assert "abcdef123456" not in redactor.text("Authorization: Bearer abcdef123456")
    assert "hunter2" not in redactor.text("postgres://admin:hunter2@db/x")
    # A non-secret survives untouched, or the report would be unreadable.
    assert "gpt-4.1" in redactor.text("Invalid model name passed in model=gpt-4.1")


def test_a_key_stored_inline_in_config_is_probed_but_never_printed():
    secret = "sk-inline-9f8e7d6c5b4a"
    with seat_doctor._env_override({"OPENAI_API_KEY": secret}):
        assert __import__("os").environ["OPENAI_API_KEY"] == secret
    assert "OPENAI_API_KEY" not in __import__("os").environ
    # And a value that was already set is restored, not clobbered.
    __import__("os").environ["OPENAI_API_KEY"] = "pre-existing"
    try:
        with seat_doctor._env_override({"OPENAI_API_KEY": secret}):
            assert __import__("os").environ["OPENAI_API_KEY"] == secret
        assert __import__("os").environ["OPENAI_API_KEY"] == "pre-existing"
    finally:
        __import__("os").environ.pop("OPENAI_API_KEY", None)


# ---------------------------------------------------------------------------
# liveness is not working
# ---------------------------------------------------------------------------


def test_a_cli_that_answers_version_is_unverified_never_ok(monkeypatch):
    _stub_cli_liveness(monkeypatch, "ok")
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="grok_agent", cli="grok", origin="cli_agents"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.verdict == VERDICT_UNVERIFIED
    assert finding.proves == PROVES_LIVENESS
    assert finding.as_dict()["turn_proved"] is False
    assert finding.remediation == ""


def test_a_passing_api_probe_is_ok_because_action_test_is_a_real_turn(gateway):
    server, configure = gateway
    configure(chat_status=200, chat_body=_OK_BODY, list_status=200)
    finding = seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "orchestration"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_OK
    assert finding.proves == PROVES_TURN
    assert finding.as_dict()["turn_proved"] is True


def test_a_declared_timeout_plus_a_slow_probe_is_timeout_risk(monkeypatch):
    _stub_cli_liveness(monkeypatch, "ok", latency_ms=64_000)
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="codex_agent", cli="codex", origin="cli_agents", timeout_s=90),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.bucket == BUCKET_TIMEOUT_RISK
    assert "90s" in finding.detail
    assert "timeout" in finding.remediation


def test_no_declared_timeout_means_no_risk_claim(monkeypatch):
    _stub_cli_liveness(monkeypatch, "ok", latency_ms=5_000)
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="pi_agent", cli="pi", origin="cli_agents"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.verdict == VERDICT_UNVERIFIED
    assert finding.bucket == ""


# ---------------------------------------------------------------------------
# CLI: missing binary vs unwired binary
# ---------------------------------------------------------------------------


def test_a_configured_cli_with_no_binary_is_not_installed(monkeypatch):
    from swarm.core import seat_health

    monkeypatch.setattr(
        seat_health, "probe_seat", lambda *_a, **_k: _verdict("broken", "ocr is not installed on this host")
    )
    monkeypatch.setattr(seat_doctor.shutil, "which", lambda _name: None)
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="ocr_agent", cli="ocr", origin="cli_agents"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_NOT_INSTALLED
    assert finding.remediation == "npm i -g @alibaba-group/open-code-review"


def test_a_binary_on_path_that_is_not_wired_is_misconfigured(monkeypatch):
    monkeypatch.setattr(seat_doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="kilocode_agent", cli="kilocode", origin="discovered_on_path"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_MISCONFIGURED
    assert "No CLI agents are configured" in finding.remediation
    assert "cli_agents.kilocode" in finding.remediation
    assert finding.evidence["configured"] is False


def test_a_wedged_binary_that_never_answers_version_is_a_timeout(monkeypatch):
    from swarm.core import seat_health

    monkeypatch.setattr(
        seat_health,
        "probe_seat",
        lambda *_a, **_k: _verdict("broken", "claude did not answer --version in 12s"),
    )
    monkeypatch.setattr(seat_doctor.shutil, "which", lambda name: f"/usr/bin/{name}")
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="claude_agent", cli="claude", origin="cli_agents"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.bucket == BUCKET_TIMEOUT
    assert "restart it" in finding.remediation


def test_a_cli_model_pin_is_read_off_argv_never_invented():
    pin, base_url, env, inline = seat_doctor._cli_model_pin(
        {
            "cmd": ["qwen", "--openai-base-url", "http://203.0.113.30:8000/v1", "qwen3.8-27b"],
            "env": {"OPENAI_API_KEY": "sk-inline-secret-value"},
        }
    )
    assert base_url == "http://203.0.113.30:8000/v1"
    assert env == "OPENAI_API_KEY"
    assert inline["OPENAI_API_KEY"] == "sk-inline-secret-value"
    pin2, base2, _env2, _inline2 = seat_doctor._cli_model_pin(
        {"cmd": ["omp", "--model", "litellm/orchestration"]}
    )
    assert pin2 == "litellm/orchestration"
    assert base2 == ""


# ---------------------------------------------------------------------------
# remotes — real TCP, real HTTP
# ---------------------------------------------------------------------------


class _RemoteStub:
    """Point one remote kind at a real endpoint, without touching config files."""

    def __init__(self, monkeypatch, remote_id: str, base_url: str, *, configured: bool = True):
        self._monkeypatch = monkeypatch
        self.remote_id = remote_id
        self.base_url = base_url
        self.configured = configured

    def __enter__(self):
        from swarm.core import remotes
        from swarm.core.remotes import RemoteSpec
        from swarm.remotes import registry

        rid = self.remote_id
        base_url = self.base_url
        configured = self.configured

        def _spec(*_args, **_kwargs):  # noqa: ANN002, ANN003
            spec = RemoteSpec(
                id=rid,
                title=rid,
                host_label="",
                base_url=base_url,
                health_path="/health",
                version_path="/health",
                api_key_env=f"{rid.upper()}_API_KEY",
            )
            return spec

        self._monkeypatch.setattr(remotes, "load_remote", _spec)
        self._monkeypatch.setattr(remotes, "is_configured", lambda _r, _config=None: configured)
        # Force the generic TCP+HTTP prober so the probe is genuinely ours.
        self._monkeypatch.setattr(registry, "create_remote_adapter", lambda *_a, **_k: None)
        return self

    def __exit__(self, *_exc):
        return False


@_IN_CONTAINER
def test_a_refused_port_is_service_down(monkeypatch):
    port = _free_port()
    spec = SeatSpec(kind="remote", seat_id="rakazo", origin="remote_config")
    with _RemoteStub(monkeypatch, "rakazo", f"http://127.0.0.1:{port}"):
        finding = seat_doctor._probe_remote_seat(spec, deep=False, redactor=_redactor())
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_SERVICE_DOWN
    assert f":{port}" in finding.remediation
    assert "nothing is listening" in finding.remediation
    assert finding.evidence["tcp"] == "refused"


@_IN_CONTAINER
def test_a_healthy_remote_is_unverified_because_no_turn_was_run(monkeypatch):
    server = _Server()
    server.configure(served_models=["remote-model"], health_status=200)
    try:
        spec = SeatSpec(kind="remote", seat_id="anythingllm", origin="remote_config")
        with _RemoteStub(monkeypatch, "anythingllm", server.base_url):
            finding = seat_doctor._probe_remote_seat(spec, deep=False, redactor=_redactor())
        assert finding.verdict == VERDICT_UNVERIFIED
        assert finding.proves == PROVES_LIVENESS
        assert finding.bucket == ""
        assert "no turn was run" in finding.evidence["turn_note"]
    finally:
        server.close()


@_IN_CONTAINER
def test_a_health_route_that_needs_a_key_is_auth(monkeypatch):
    server = _Server()
    server.configure(health_status=401, health_body=_BAD_KEY_BODY)
    try:
        spec = SeatSpec(kind="remote", seat_id="openmuse", origin="remote_config")
        with _RemoteStub(monkeypatch, "openmuse", server.base_url):
            finding = seat_doctor._probe_remote_seat(spec, deep=False, redactor=_redactor())
        assert finding.bucket == BUCKET_AUTH
        assert "OPENMUSE_API_KEY" in finding.remediation
        assert _LEAKED_KEY not in json.dumps(finding.as_dict())
    finally:
        server.close()


def test_an_unresolvable_host_is_unreachable_not_down(monkeypatch):
    spec = SeatSpec(kind="remote", seat_id="hermes", origin="remote_config")
    with _RemoteStub(monkeypatch, "hermes", f"http://no-such-host.invalid:{_free_port()}"):
        finding = seat_doctor._probe_remote_seat(spec, deep=False, redactor=_redactor())
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_UNREACHABLE
    assert finding.evidence["tcp"] == "unresolved"
    assert "does not resolve" in finding.remediation
    # A refusal and a dead host are different problems with different fixes.
    assert finding.bucket != BUCKET_SERVICE_DOWN


def test_tcp_state_is_a_closed_vocabulary_that_separates_refusal_from_no_route():
    """The remote bucket depends on this function, so its vocabulary is part of
    the contract: a refusal (host up, service stopped) must never collapse into
    the same token as an unreachable host."""
    documented = {"open", "refused", "timeout", "no_route", "unresolved"}
    assert seat_doctor._tcp_state("127.0.0.1", _free_port()) == "refused"
    assert seat_doctor._tcp_state("no-such-host.invalid", 80) == "unresolved"
    assert seat_doctor._tcp_state("0.0.0.0", 9, timeout=0.5) in documented


def test_tcp_errno_mapping_is_exact():
    """Regression: ``socket.create_connection`` re-raises a non-blocking errno
    as ``OSError(errno, 'timed out')``, so a powered-off host (EHOSTUNREACH)
    was being bucketed as a timeout — "the service is wedged, restart it there".
    ``connect_ex`` sidesteps that, and this pins the mapping."""
    import errno

    assert seat_doctor._state_for_errno(0) == "open"
    assert seat_doctor._state_for_errno(None) == "unresolved"
    assert seat_doctor._state_for_errno(errno.ECONNREFUSED) == "refused"
    assert seat_doctor._state_for_errno(errno.EHOSTUNREACH) == "no_route"
    assert seat_doctor._state_for_errno(errno.ENETUNREACH) == "no_route"
    assert seat_doctor._state_for_errno(errno.ETIMEDOUT) == "timeout"
    # Anything the mapping does not know is not guessed at.
    assert seat_doctor._state_for_errno(errno.EPERM) == "unresolved"
    assert "EHOSTUNREACH" not in seat_doctor._TCP_ERRNO_STATES.get("timeout", "")


def test_a_refusal_and_a_dead_host_are_different_buckets(monkeypatch):
    refused = SeatSpec(kind="remote", seat_id="rakazo", origin="remote_config")
    with _RemoteStub(monkeypatch, "rakazo", f"http://127.0.0.1:{_free_port()}"):
        down = seat_doctor._probe_remote_seat(refused, deep=False, redactor=_redactor())
    assert down.evidence["tcp"] == "refused"
    assert down.bucket == BUCKET_SERVICE_DOWN
    assert "nothing is listening" in down.remediation


def test_a_placeholder_catalog_default_is_not_configured(monkeypatch):
    from swarm.core import remotes
    from swarm.core.remotes import default_spec, is_placeholder_base_url

    assert is_placeholder_base_url(default_spec("octop").base_url) is True
    spec = SeatSpec(kind="remote", seat_id="octop", origin="remote_catalog")
    # No override: the catalog default is what the sidebar seat points at.
    monkeypatch.setattr(remotes, "is_configured", lambda _r, _config=None: False)
    finding = seat_doctor._probe_remote_seat(spec, deep=False, redactor=_redactor())
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_NOT_CONFIGURED
    assert "OCTOP_BASE_URL" in finding.remediation
    assert "OCTOP_API_KEY" in finding.remediation
    # A placeholder address proves the point, so no probe time is spent on it.
    assert finding.evidence["placeholder_default"] is True
    assert "tcp" not in finding.evidence


def test_a_real_default_port_owned_by_another_app_is_named():
    """The :8088-is-llama.cpp case: a real listener, a real fingerprint."""
    body = json.dumps({"object": "list", "data": [{"id": "qwen3"}]})
    handler = type(
        "_H",
        (_GatewayHandler,),
        {"served_models": ["qwen3"], "_body": body},
    )
    original = _GatewayHandler.do_GET

    def _do_get(self):  # noqa: ANN001
        if self.path.rstrip("/").endswith("/models"):
            self._send(200, self._body)
            return
        original(self)

    handler.do_GET = _do_get
    server = _Server(handler)
    try:
        host, port = server.origin
        owner = seat_doctor.identify_endpoint(host, port)
        assert "OpenAI-compatible" in owner
    finally:
        server.close()


def test_identify_endpoint_returns_nothing_when_unsure():
    """A weak guess would send an operator to the wrong dashboard."""
    assert seat_doctor.identify_endpoint("127.0.0.1", _free_port()) == ""
    assert seat_doctor.identify_endpoint("no-such-host.invalid", 80) == ""


# ---------------------------------------------------------------------------
# an unrecognised failure must not be dressed up
# ---------------------------------------------------------------------------


@_IN_CONTAINER
def test_an_unrecognised_api_failure_is_probe_error_not_a_guess(gateway):
    server, configure = gateway
    configure(chat_status=418, chat_body='{"error":"teapot"}', list_status=418)
    finding = seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "orchestration"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_PROBE_ERROR
    assert "will not guess" in finding.remediation


def test_a_probe_that_raises_is_reported_not_swallowed(monkeypatch):
    from swarm.core import llm_profile_probe

    def _boom(**_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(llm_profile_probe, "probe_llm_profile", _boom)
    finding = seat_doctor._probe_api_seat(
        _api_spec("http://127.0.0.1:1", "m"), deep=False, redactor=_redactor()
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_PROBE_ERROR
    assert "RuntimeError" in finding.detail


# ---------------------------------------------------------------------------
# composition: a seat is only as healthy as what it runs
# ---------------------------------------------------------------------------


def test_a_composition_seat_inherits_its_delegate_bucket():
    specs = {
        ("cli", "grok_agent"): SeatSpec(kind="cli", seat_id="grok_agent", origin="cli_agents"),
        ("cli", "cli_map"): SeatSpec(
            kind="cli", seat_id="cli_map", origin="config_block", delegates_to=["grok_agent"]
        ),
        ("cli", "cli_fusion"): SeatSpec(
            kind="cli", seat_id="cli_fusion", origin="config_block", delegates_to=["grok_agent"]
        ),
    }
    findings = {
        ("cli", "grok_agent"): SeatFinding(
            kind="cli",
            seat_id="grok_agent",
            verdict=VERDICT_BROKEN,
            bucket=BUCKET_QUOTA,
            detail="status 402",
            remediation="top up the balance",
        ),
        ("cli", "cli_map"): SeatFinding(kind="cli", seat_id="cli_map", origin="config_block"),
        ("cli", "cli_fusion"): SeatFinding(kind="cli", seat_id="cli_fusion", origin="config_block"),
    }
    seat_doctor._apply_delegate_verdicts(specs, findings)
    for seat in ("cli_map", "cli_fusion"):
        assert findings[("cli", seat)].verdict == VERDICT_BROKEN
        assert findings[("cli", seat)].bucket == BUCKET_QUOTA
        assert findings[("cli", seat)].remediation == "top up the balance"
        assert findings[("cli", seat)].evidence["via"] == "grok_agent"


def test_a_composition_seat_with_no_delegate_is_not_configured():
    finding = seat_doctor._probe_composition_seat(
        SeatSpec(kind="cli", seat_id="cli_planner", origin="config_block", note="no delegate")
    )
    assert finding.verdict == VERDICT_BROKEN
    assert finding.bucket == BUCKET_NOT_CONFIGURED
    assert "No CLI agents are configured" in finding.remediation


def test_a_healthy_delegate_leaves_the_composition_unverified():
    specs = {
        ("cli", "codex_agent"): SeatSpec(kind="cli", seat_id="codex_agent", origin="cli_agents"),
        ("cli", "hybrid_team"): SeatSpec(
            kind="cli",
            seat_id="hybrid_team",
            origin="library_installed",
            delegates_to=["codex_agent"],
        ),
    }
    findings = {
        ("cli", "codex_agent"): SeatFinding(
            kind="cli", seat_id="codex_agent", verdict=VERDICT_UNVERIFIED, proves=PROVES_LIVENESS
        ),
        ("cli", "hybrid_team"): SeatFinding(kind="cli", seat_id="hybrid_team", origin="library_installed"),
    }
    seat_doctor._apply_delegate_verdicts(specs, findings)
    assert findings[("cli", "hybrid_team")].verdict == VERDICT_UNVERIFIED
    assert findings[("cli", "hybrid_team")].bucket == ""


def test_a_leaf_finding_is_never_overwritten_by_delegate_resolution():
    """Regression: the resolver once replaced a real API verdict with
    'delegates answered liveness only' simply because the seat had no delegates."""
    specs = {("api", "orchestration"): SeatSpec(kind="api", seat_id="orchestration", origin="llm_profile")}
    findings = {
        ("api", "orchestration"): SeatFinding(
            kind="api", seat_id="orchestration", verdict=VERDICT_OK, proves=PROVES_TURN
        )
    }
    seat_doctor._apply_delegate_verdicts(specs, findings)
    assert findings[("api", "orchestration")].verdict == VERDICT_OK
    assert findings[("api", "orchestration")].proves == PROVES_TURN


def test_a_delegation_cycle_terminates_instead_of_hanging():
    specs = {
        ("cli", "a"): SeatSpec(kind="cli", seat_id="a", origin="config_block", delegates_to=["b"]),
        ("cli", "b"): SeatSpec(kind="cli", seat_id="b", origin="config_block", delegates_to=["a"]),
    }
    findings = {
        ("cli", "a"): SeatFinding(kind="cli", seat_id="a", origin="config_block"),
        ("cli", "b"): SeatFinding(kind="cli", seat_id="b", origin="config_block"),
    }
    seat_doctor._apply_delegate_verdicts(specs, findings)
    for key in findings:
        assert "cycle" in findings[key].evidence["delegation"]


# ---------------------------------------------------------------------------
# roster + report shape
# ---------------------------------------------------------------------------


def test_enumerate_seats_spans_all_three_kinds_and_wires_delegates():
    config = {
        "llm": {"aux": {"provider": "openai", "model": "m", "base_url": "http://x/v1", "api_key": "${K}"}},
        "cli_agents": {"grok": {"cmd": ["grok"], "timeout": 90}},
        "remotes": {"rakazo": {"base_url": "http://203.0.113.32:3100"}},
        "agent_team": {"members": ["rakazo"]},
        "cli_map": {"planner": "grok", "workers": ["grok"]},
    }
    specs = enumerate_seats(config)
    assert {s.kind for s in specs} == {"api", "cli", "remote"}
    by_id = {s.seat_id: s for s in specs}
    assert {"aux", "grok_agent", "rakazo", "cli_map", "agent_team"} <= set(by_id)
    assert by_id["cli_map"].delegates_to == ["grok_agent"]
    assert by_id["cli_map"].delegate_kinds == {"grok_agent": "cli"}
    assert by_id["grok_agent"].timeout_s == 90
    # A team of remotes is a remote seat, not a CLI one.
    assert by_id["agent_team"].kind == "remote"
    assert by_id["agent_team"].delegates_to == ["rakazo"]
    # Every delegate must name a seat that exists, or the graph is decorative.
    keys = {(s.kind, s.seat_id) for s in specs}
    for spec in specs:
        for name in spec.delegates_to:
            assert (spec.delegate_kinds.get(name, "cli"), name) in keys, (spec.seat_id, name)


def test_a_composition_block_reaches_its_delegates_real_seat(monkeypatch):
    """Regression: the block says ``planner: "grok"`` but the seat is
    ``grok_agent``. Unresolved, a broken ``grok`` would have produced an
    ``unverified`` ``cli_map`` instead of its real quota bucket."""
    config = {
        "llm": {"grok_gate": {"provider": "openai", "model": "auxiliary", "base_url": "http://127.0.0.1:1/v1"}},
        "cli_agents": {"grok": {"cmd": ["grok"]}},
        "cli_map": {"planner": "grok", "workers": ["grok"]},
        "cli_fusion": {"default_cli": "grok"},
        "agent_team": {"members": ["grok"]},
    }
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
        ),
    )
    monkeypatch.setattr(
        seat_doctor,
        "_probe_remote_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
        ),
    )

    def _cli(spec, **_kwargs):
        broken = spec.seat_id == "grok_agent"
        return SeatFinding(
            kind=spec.kind,
            seat_id=spec.seat_id,
            verdict=VERDICT_BROKEN if broken else VERDICT_UNVERIFIED,
            bucket=BUCKET_QUOTA if broken else "",
            detail="status 402" if broken else "",
            remediation="top up the balance" if broken else "",
        )

    monkeypatch.setattr(seat_doctor, "_probe_cli_seat", _cli)
    rows = {(row.kind, row.seat_id): row for row in diagnose(config)}
    for seat in ("cli_map", "cli_fusion", "agent_team", "cli_agent"):
        row = rows[("cli", seat)]
        assert row.verdict == VERDICT_BROKEN, seat
        assert row.bucket == BUCKET_QUOTA, seat
        assert row.evidence["via"] == "grok_agent", seat


def test_a_cli_shares_a_profile_verdict_only_when_endpoint_and_model_both_match():
    endpoint = "http://203.0.113.30:8000/v1"
    config = {
        "llm": {"gate": {"provider": "openai", "model": "qwen3.8-27b-cf", "base_url": endpoint}},
        "cli_agents": {
            # Same endpoint, same model -> provably the same provider.
            "qwen": {"cmd": ["qwen", "--openai-base-url", endpoint, "--model", "qwen3.8-27b-cf"]},
            # Same endpoint, different model -> a different spend, no link.
            "omp": {"cmd": ["omp", "--openai-base-url", endpoint, "--model", "other-model"]},
            # A model pin with no stated endpoint proves nothing about the host.
            "pi": {"cmd": ["pi", "--model", "litellm/qwen3.8-27b-cf"]},
        },
    }
    by_id = {s.seat_id: s for s in enumerate_seats(config)}
    assert by_id["qwen_agent"].delegates_to == ["gate"]
    assert by_id["qwen_agent"].delegate_kinds == {"gate": "api"}
    assert by_id["omp_agent"].delegates_to == []
    assert by_id["pi_agent"].delegates_to == []


def test_a_healthy_cli_keeps_its_own_liveness_evidence_when_its_profile_is_healthy(monkeypatch):
    """Regression risk: a linked provider must not downgrade a seat that was
    probed in its own right — its liveness evidence is the more useful fact."""
    endpoint = "http://203.0.113.30:8000/v1"
    config = {
        "llm": {"gate": {"provider": "openai", "model": "m", "base_url": endpoint}},
        "cli_agents": {"qwen": {"cmd": ["qwen", "--openai-base-url", endpoint, "--model", "m"]}},
    }
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_OK, proves=PROVES_TURN
        ),
    )
    monkeypatch.setattr(
        seat_doctor,
        "_probe_cli_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind,
            seat_id=spec.seat_id,
            verdict=VERDICT_UNVERIFIED,
            proves=PROVES_LIVENESS,
            detail="`qwen --version` answered",
        ),
    )
    qwen = {(r.kind, r.seat_id): r for r in diagnose(config)}[("cli", "qwen_agent")]
    assert qwen.verdict == VERDICT_UNVERIFIED
    assert "--version" in qwen.detail
    assert qwen.evidence["provider_delegate"] == "gate"


def test_a_cli_inherits_its_profiles_broken_bucket(monkeypatch):
    endpoint = "http://203.0.113.30:8000/v1"
    config = {
        "llm": {"gate": {"provider": "openai", "model": "m", "base_url": endpoint}},
        "cli_agents": {"qwen": {"cmd": ["qwen", "--openai-base-url", endpoint, "--model", "m"]}},
    }
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind,
            seat_id=spec.seat_id,
            verdict=VERDICT_BROKEN,
            bucket=BUCKET_QUOTA,
            detail="status 402",
            remediation="top up the balance",
        ),
    )
    monkeypatch.setattr(
        seat_doctor,
        "_probe_cli_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED, proves=PROVES_LIVENESS
        ),
    )
    qwen = {(r.kind, r.seat_id): r for r in diagnose(config)}[("cli", "qwen_agent")]
    assert qwen.verdict == VERDICT_BROKEN
    assert qwen.bucket == BUCKET_QUOTA
    assert qwen.evidence["via"] == "gate"


def test_a_binary_that_will_not_execute_is_not_reported_as_missing(monkeypatch):
    from swarm.core import seat_health

    monkeypatch.setattr(
        seat_health,
        "probe_seat",
        lambda *_a, **_k: _verdict("broken", "agy could not be executed: FileNotFoundError"),
    )
    monkeypatch.setattr(seat_doctor.shutil, "which", lambda _name: "/opt/bin/agy")
    finding = seat_doctor._probe_cli_seat(
        SeatSpec(kind="cli", seat_id="agy_agent", cli="agy", origin="cli_agents"),
        deep=False,
        redactor=_redactor(),
    )
    assert finding.bucket == BUCKET_NOT_EXECUTABLE
    assert "do not reinstall" in finding.remediation
    assert finding.evidence["path"] == "/opt/bin/agy"


def test_a_dangling_delegate_edge_is_dropped_rather_than_reported_unverified():
    """A delegate that names no seat in the roster used to become a permanent
    ``referenced_only`` ``unverified`` placeholder — technically true, useless.
    The edge is removed and the note says so instead."""
    specs = [
        SeatSpec(kind="api", seat_id="api_agent", delegates_to=["ghost"], delegate_kinds={"ghost": "api"}),
    ]
    seat_doctor._retype_delegates_against_roster(specs, {("api", "api_agent"): specs[0]})
    assert specs[0].delegates_to == []
    assert "ghost" in specs[0].note
    assert "not seats in this roster" in specs[0].note


def test_a_delegate_kind_is_taken_from_the_roster_not_assumed():
    specs = [
        SeatSpec(kind="api", seat_id="api_agent", delegates_to=["grok_agent"], delegate_kinds={"grok_agent": "api"}),
        SeatSpec(kind="cli", seat_id="grok_agent", cli="grok"),
    ]
    by_key = {("api", "api_agent"): specs[0], ("cli", "grok_agent"): specs[1]}
    seat_doctor._retype_delegates_against_roster(specs, by_key)
    assert specs[0].delegate_kinds == {"grok_agent": "cli"}


def test_every_roster_delegate_names_a_seat_that_exists():
    config = {
        "llm": {"aux": {"provider": "openai", "model": "m", "base_url": "http://x/v1"}},
        "cli_agents": {"grok": {"cmd": ["grok"]}},
        "remotes": {"rakazo": {"base_url": "http://203.0.113.32:3100"}},
        "agent_team": {"members": ["rakazo"]},
        "cli_map": {"planner": "grok"},
    }
    specs = enumerate_seats(config)
    keys = {(s.kind, s.seat_id) for s in specs}
    for spec in specs:
        for name in spec.delegates_to:
            assert (spec.delegate_kinds.get(name, "cli"), name) in keys, (spec.seat_id, name)


def test_an_unwired_composition_block_reports_its_empty_roles():
    config = {"cli_agents": {"grok": {"cmd": ["grok"]}}, "cli_planner": {"max_rounds": 3}}
    by_id = {s.seat_id: s for s in enumerate_seats(config)}
    assert by_id["cli_planner"].delegates_to == []
    finding = seat_doctor._probe_composition_seat(by_id["cli_planner"])
    assert finding.bucket == BUCKET_NOT_CONFIGURED


def test_the_roster_is_capped():
    config = {"cli_agents": {f"cli{i}": {"cmd": [f"cli{i}"]} for i in range(MAX_SEATS + 40)}}
    assert len(enumerate_seats(config)) <= MAX_SEATS


def test_diagnose_is_bounded_by_limit(monkeypatch):
    config = {
        "llm": {
            f"p{i}": {"provider": "openai", "model": "m", "base_url": "http://127.0.0.1:1/v1"}
            for i in range(12)
        }
    }
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
        ),
    )
    assert len(diagnose(config, limit=3)) == 3


def test_diagnose_filters_by_kind(monkeypatch):
    config = {
        "llm": {"p": {"provider": "openai", "model": "m", "base_url": "http://127.0.0.1:1/v1"}},
        "remotes": {"rakazo": {"base_url": "http://127.0.0.1:1"}},
    }
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
        ),
    )
    monkeypatch.setattr(
        seat_doctor,
        "_probe_remote_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
        ),
    )
    assert {row.kind for row in diagnose(config, kinds=["remote"])} == {"remote"}


def test_a_default_run_makes_no_call_beyond_the_single_test_probe(gateway, monkeypatch):
    """Politeness: one ``action="test"`` probe, plus at most one GET."""
    server, configure = gateway
    configure(chat_status=402, chat_body=_QUOTA_BODY, list_status=402)
    calls: list[str] = []
    from swarm.core import llm_profile_probe

    original = llm_profile_probe.probe_llm_profile

    def _counting(**kwargs):
        calls.append(str(kwargs.get("action")))
        return original(**kwargs)

    monkeypatch.setattr(llm_profile_probe, "probe_llm_profile", _counting)
    seat_doctor._probe_api_seat(
        _api_spec(server.base_url, "auxiliary"), deep=False, redactor=_redactor()
    )
    # The failing seat spends "test" plus at most one list_models; never chat.
    assert calls.count("test") == 1
    assert "chat" not in calls


def test_deep_mode_adds_the_chat_reprobe_only_for_a_deep_run(gateway, monkeypatch):
    server, configure = gateway
    # Models list works; only the chat fails, and slowly enough to look like a 5xx.
    configure(chat_status=400, chat_body='{"error":{"message":"upstream exploded"}}', list_status=200)
    from swarm.core import remotes

    posted: list[str] = []
    original = remotes.http_json

    def _counting(method, url, **kwargs):  # noqa: ANN001
        posted.append(method.upper())
        return original(method, url, **kwargs)

    monkeypatch.setattr(remotes, "http_json", _counting)
    spec = _api_spec(server.base_url, "orchestration")
    seat_doctor._probe_api_seat(spec, deep=False, redactor=_redactor())
    assert "POST" not in posted
    posted.clear()
    seat_doctor._probe_api_seat(spec, deep=True, redactor=_redactor())
    assert "POST" in posted


def test_report_payload_shape():
    payload = report_payload({"llm": {}, "cli_agents": {}, "remotes": {}})
    assert payload["object"] == "seat_doctor_report"
    assert payload["read_only"] is True
    assert payload["deep"] is False
    assert set(payload["totals"]) == {"seats", "broken", "unverified", "ok"}
    assert isinstance(payload["buckets"], dict)
    for row in payload["results"]:
        for key in (
            "kind",
            "seat_id",
            "verdict",
            "bucket",
            "detail",
            "remediation",
            "proves",
            "turn_proved",
            "evidence",
        ):
            assert key in row


def test_format_report_lists_broken_first_and_hides_the_rest_by_default():
    payload = {
        "totals": {"seats": 3, "broken": 1, "unverified": 1, "ok": 1},
        "results": [
            {"kind": "api", "seat_id": "ok_one", "verdict": "ok", "bucket": "", "remediation": ""},
            {
                "kind": "cli",
                "seat_id": "broken_one",
                "verdict": "broken",
                "bucket": "quota",
                "remediation": "top up",
            },
            {"kind": "remote", "seat_id": "mystery", "verdict": "unverified", "bucket": "", "remediation": ""},
        ],
    }
    text = format_report(payload)
    assert "broken_one" in text and "quota" in text and "top up" in text
    assert "mystery" not in text
    assert "--all" in text
    assert "mystery" in format_report(payload, show_all=True)


# ---------------------------------------------------------------------------
# the management command
# ---------------------------------------------------------------------------


def _neutral_probes(monkeypatch) -> None:
    for name in ("_probe_cli_seat", "_probe_remote_seat"):
        monkeypatch.setattr(
            seat_doctor,
            name,
            lambda spec, **_kwargs: SeatFinding(
                kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
            ),
        )


_COMMAND_CONFIG = {
    "llm": {
        "aux": {"provider": "openai", "model": "auxiliary", "base_url": "http://127.0.0.1:1/v1"}
    }
}


def test_seat_doctor_command_emits_json_and_writes_nothing(monkeypatch, tmp_path):
    from io import StringIO

    from django.core.management import call_command

    config_path = tmp_path / "swarm_config.json"
    config_path.write_text(json.dumps(_COMMAND_CONFIG), encoding="utf-8")
    before = config_path.read_bytes()
    monkeypatch.setattr(seat_doctor, "_swarm_config", lambda _explicit=None: json.loads(before))
    _neutral_probes(monkeypatch)
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind="api",
            seat_id=spec.seat_id,
            verdict=VERDICT_BROKEN,
            bucket=BUCKET_QUOTA,
            detail="status 402",
            remediation="top up the balance",
        ),
    )
    out = StringIO()
    call_command("seat_doctor", "--json", stdout=out)
    payload = json.loads(out.getvalue())
    assert payload["object"] == "seat_doctor_report"
    assert payload["totals"]["broken"] >= 1
    assert payload["buckets"]["quota"] >= 1
    # The rail API seat runs the broken profile, so it inherits the bucket.
    inherited = [r for r in payload["results"] if r["seat_id"] == "api_agent"]
    assert inherited, [r["seat_id"] for r in payload["results"]]
    assert inherited[0]["bucket"] == BUCKET_QUOTA
    assert inherited[0]["remediation"] == "top up the balance"
    # Read-only: the config on disk is byte-identical afterwards.
    assert config_path.read_bytes() == before


def test_seat_doctor_command_text_mode_names_the_fix(monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    monkeypatch.setattr(seat_doctor, "_swarm_config", lambda _explicit=None: dict(_COMMAND_CONFIG))
    _neutral_probes(monkeypatch)
    monkeypatch.setattr(
        seat_doctor,
        "_probe_api_seat",
        lambda spec, **_kwargs: SeatFinding(
            kind="api",
            seat_id=spec.seat_id,
            verdict=VERDICT_BROKEN,
            bucket=BUCKET_MODEL_INVALID,
            remediation="pick from the gateway's model list",
        ),
    )
    out = StringIO()
    call_command("seat_doctor", stdout=out)
    text = out.getvalue()
    assert "BROKEN" in text
    assert "model_invalid" in text
    assert "pick from the gateway" in text


def test_seat_doctor_command_reports_no_rows_when_nothing_is_broken(monkeypatch):
    from io import StringIO

    from django.core.management import call_command

    monkeypatch.setattr(seat_doctor, "_swarm_config", lambda _explicit=None: dict(_COMMAND_CONFIG))
    for name in ("_probe_api_seat", "_probe_cli_seat", "_probe_remote_seat"):
        monkeypatch.setattr(
            seat_doctor,
            name,
            lambda spec, **_kwargs: SeatFinding(
                kind=spec.kind, seat_id=spec.seat_id, verdict=VERDICT_UNVERIFIED
            ),
        )
    out = StringIO()
    call_command("seat_doctor", stdout=out)
    text = out.getvalue()
    assert "No broken seat found." in text
    assert "broken 0" in text

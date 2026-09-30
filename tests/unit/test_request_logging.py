"""Request logging: one line per request, one rate-limit report per window.

The defect these cover is volume. The 429 handler logged its entire forensic
report on *every* rejected request, so a burst of 300 rejections produced 300
identical multi-line reports (measured: 2,100 journal lines) — the logger, not
the client, was the flood. Alongside it there was no single structured record
of a request, so attribution had to be reconstructed by hand from interleaved
uvicorn access lines, Django request logs and throttle blocks.

The security axis matters as much as the volume one: a log line is a place a
credential can end up, so these tests fire real requests carrying real secret
shapes (headers, query strings, bodies, token-bearing paths) and assert the
captured journal output does not contain them. Assertions are made against
captured log output, never against source text.
"""

from __future__ import annotations

import logging
import re
import threading
import time

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework import exceptions

from swarm.core import request_logging
from swarm.core.request_telemetry import (
    REDACTED,
    RequestTelemetry,
    default_telemetry,
    normalize_path,
    sanitize_field,
)
from swarm.views import exception_handlers

# A 20-character key of the family this repo's scanner was widened to catch,
# plus the shapes that reach a request in practice: a bearer header, a query
# param, a path segment, and a body. None of these is a live credential.
FAKE_KEY = "sk-TESTONLY" + "aB3dE5fG7hJ9"
FAKE_PAT = "ghp_TESTONLY0123456789abcdefghij"
FAKE_JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"


class _Capture(logging.Handler):
    """The journal, as an operator would see it: fully formatted lines."""

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)

    @property
    def lines(self) -> list[str]:
        return [line for record in self.records for line in record.getMessage().splitlines()]

    @property
    def text(self) -> str:
        return "\n".join(self.lines)

    def named(self, name: str) -> list[str]:
        return [r.getMessage() for r in self.records if r.name == name]

    def count(self, name: str) -> int:
        return sum(1 for r in self.records if r.name == name)


@pytest.fixture
def journal():
    """Capture every telemetry logger, and reset the process-wide state."""
    telemetry = default_telemetry()
    telemetry.reset()
    if hasattr(request_logging, "uninstall"):
        request_logging.uninstall()
    log_filter = request_logging.install()

    capture = _Capture()
    levels = {}
    for name in ("swarm.requests", "swarm.throttle", "swarm.throttle_summary"):
        logger = logging.getLogger(name)
        levels[name] = logger.level
        logger.handlers = [capture]
        logger.propagate = False
        logger.setLevel(logging.DEBUG)

    yield capture, telemetry, log_filter

    telemetry.reset()
    request_logging.uninstall()
    for name, level in levels.items():
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
        logger.setLevel(level)


class _FakeRequest:
    """What the 429 handler reads off a request. No DB, no middleware."""

    def __init__(
        self,
        *,
        path="/v1/seat-health/",
        method="GET",
        client_ip="192.0.2.44",
        user=None,
        source="seatHealthPoll",
        headers=None,
    ):
        self.path = path
        self.method = method
        self.META = {"REMOTE_ADDR": client_ip}
        self.user = user
        self.headers = headers if headers is not None else {"X-Swarm-Client-Source": source}


def _reject(request, *, wait=60.0):
    """The exact call the 429 path makes when a throttle refuses a request."""
    return exception_handlers.swarm_exception_handler(
        exceptions.Throttled(wait=wait), {"request": request}
    )


def _record(telemetry, ip="192.0.2.44", path="/v1/seat-health/", count=3, source="seatHealthPoll"):
    base = time.monotonic()
    for i in range(count):
        telemetry.record(
            client_ip=ip,
            method="GET",
            path=path,
            status_code=429,
            user_key="42",
            source=source,
            duration_ms=1.0,
            response_bytes=88,
            now=base + i * 0.001,
        )


# ---------------------------------------------------------------------------
# 1. One structured line per HTTP request.
# ---------------------------------------------------------------------------


def test_request_line_is_a_single_line_with_the_attribution_fields(journal):
    capture, telemetry, _ = journal
    telemetry.record(
        client_ip="192.0.2.7",
        method="get",
        path="/v1/agents/7/settings",
        status_code=200,
        user_key="42",
        source="agentSettings",
        duration_ms=12.34,
        response_bytes=1234,
    )
    request_lines = capture.named("swarm.requests")
    assert len(request_lines) == 1
    line = request_lines[0]
    assert "\n" not in line
    for field in (
        "method=GET",
        "path=/v1/agents/{int}/settings",
        "status=200",
        "client=192.0.2.7",
        "user=42",
        "bytes=1234",
        "duration_ms=12.3",
        "source=agentSettings",
    ):
        assert field in line, f"{field} missing from {line!r}"


def test_request_line_reports_unknown_fields_rather_than_inventing_them(journal):
    capture, telemetry, _ = journal
    telemetry.record(
        client_ip="192.0.2.7",
        method="GET",
        path="/health",
        status_code=None,
        user_key="",
        duration_ms=0.0,
        response_bytes=None,
    )
    line = capture.named("swarm.requests")[0]
    assert "status=-" in line
    assert "user=-" in line
    assert "bytes=-" in line


def test_request_line_can_be_silenced_without_touching_throttle_rollups(monkeypatch):
    monkeypatch.setenv("SWARM_REQUEST_LOG", "off")
    assert RequestTelemetry()._emit_request_log is False
    monkeypatch.setenv("SWARM_REQUEST_LOG", "on")
    assert RequestTelemetry()._emit_request_log is True
    monkeypatch.delenv("SWARM_REQUEST_LOG")
    assert RequestTelemetry()._emit_request_log is True


def test_request_log_flag_defaults_on_for_the_process_wide_instance(monkeypatch):
    monkeypatch.delenv("SWARM_REQUEST_LOG", raising=False)
    from swarm.core.request_telemetry import request_log_enabled

    assert request_log_enabled() is True


# ---------------------------------------------------------------------------
# Path normalisation: aggregate ids, never merge different operations.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Different rows of the same operation aggregate.
        ("/v1/agents/7/settings", "/v1/agents/{int}/settings"),
        ("/v1/agents/9/settings", "/v1/agents/{int}/settings"),
        (
            "/v1/chat/123e4567-e89b-12d3-a456-426614174000/messages",
            "/v1/chat/{uuid}/messages",
        ),
        ("/v1/agents/0123456789abcdef0123456789abcdef/run", "/v1/agents/{hex}/run"),
        # Different operations on different rows stay different, because the
        # endpoint words are not id-shaped.
        ("/v1/agents/alpha/settings", "/v1/agents/alpha/settings"),
        ("/v1/agents/beta/settings", "/v1/agents/beta/settings"),
        ("/v1/agents/alpha/settings", "/v1/agents/alpha/settings"),
        # Verb matters: the line carries the method too, so these differ.
        ("/v1/agents/alpha/cancel", "/v1/agents/alpha/cancel"),
        # Query strings never reach the line.
        ("/v1/preferences/?x=1", "/v1/preferences/"),
        ("/v1/preferences/?y=2", "/v1/preferences/"),
        # A credential in the path is normalised out, not truncated-and-logged.
        ("/reset/" + "aB3dE5fG7hJ9kL2mN4pQ6rS8", "/reset/{token}"),
        ("/reset/" + "x" * 80, "/reset/{long}"),
        ("/u/someone@example.com/prefs", "/u/{email}/prefs"),
        ("", "-"),
        ("/v1/status/", "/v1/status/"),
        ("/v1/chat/settings.json", "/v1/chat/settings.json"),
    ],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected


def test_normalised_paths_aggregate_but_different_operations_do_not():
    same = {normalize_path(f"/v1/agents/{i}/settings") for i in range(20)}
    assert len(same) == 1
    operations = {
        normalize_path("/v1/agents/alpha/settings"),
        normalize_path("/v1/agents/alpha/cancel"),
        normalize_path("/v1/agents/beta/settings"),
    }
    assert len(operations) == 3


def test_throttle_bucket_keys_on_the_normalised_path():
    telemetry = RequestTelemetry(throttle_window_seconds=60)
    base = time.monotonic()
    for i in range(5):
        telemetry.note_throttle(
            client_ip="192.0.2.44",
            method="GET",
            path=f"/v1/agents/{i}/settings",
            now=base + i * 0.001,
        )
    assert telemetry.tracked_throttle_buckets == 1
    event = telemetry.note_throttle(
        client_ip="192.0.2.44",
        method="GET",
        path="/v1/agents/9/settings",
        now=base + 0.01,
    )
    assert event.rejections == 6
    assert event.endpoint == "GET /v1/agents/{int}/settings"


# ---------------------------------------------------------------------------
# 2. Rate-limit events: one report per (client, endpoint) per window, with a
#    count. This is the volume fix.
# ---------------------------------------------------------------------------


def test_burst_of_rejections_logs_one_report_and_one_counted_rollup(journal):
    capture, telemetry, _ = journal
    _record(telemetry)
    rejections = 300
    for _ in range(rejections):
        _reject(_FakeRequest())
    telemetry.flush()

    reports = capture.named("swarm.throttle")
    assert len(reports) == 1, f"{len(reports)} full reports for {rejections} rejections"
    # The full report survives verbatim: client, wait, endpoints, cadence.
    assert "RATE_LIMIT_EXCEEDED" in reports[0]
    assert "192.0.2.44" in reports[0]
    assert "seatHealthPoll" in reports[0]

    rollups = capture.named("swarm.throttle_summary")
    window_lines = [line for line in rollups if line.startswith("[RATE_LIMIT_WINDOW]")]
    assert len(window_lines) == 1
    assert f"rejections={rejections}" in window_lines[0]
    assert capture.count("swarm.throttle_summary") == 2  # window rollup + summary


def test_rejection_volume_is_linear_free(journal):
    """The headline number: log lines per rejection, measured from output."""
    capture, telemetry, _ = journal
    _record(telemetry)
    for _ in range(100):
        _reject(_FakeRequest())
    telemetry.flush()
    throttle_lines = sum(len(m.splitlines()) for m in capture.named("swarm.throttle"))
    rollup_lines = sum(len(m.splitlines()) for m in capture.named("swarm.throttle_summary"))
    # Before: 7 lines per rejection (700 for 100). After: O(1) per window.
    assert throttle_lines + rollup_lines <= 12
    assert (throttle_lines + rollup_lines) / 100 < 0.2


def test_a_second_bucket_is_reported_once_per_window_too(journal):
    capture, telemetry, _ = journal
    _record(telemetry)
    for _ in range(10):
        _reject(_FakeRequest(path="/v1/agents/7/settings"))
    for _ in range(10):
        _reject(_FakeRequest())
    telemetry.flush()

    assert len(capture.named("swarm.throttle")) == 2
    window_lines = [
        line
        for line in capture.named("swarm.throttle_summary")
        if line.startswith("[RATE_LIMIT_WINDOW]")
    ]
    assert len(window_lines) == 2
    assert all("rejections=10" in line for line in window_lines)


def test_next_window_reports_again_rather_than_staying_silent(journal):
    capture, telemetry, log_filter = journal
    _record(telemetry)
    _reject(_FakeRequest())
    _reject(_FakeRequest())
    # A window later, the same client+endpoint is a new bucket: the operator
    # sees the recurrence, not just the first incident.
    _reject(_FakeRequest())  # still inside the first window (filter dedupes)
    lines = telemetry.flush()
    assert len(capture.named("swarm.throttle")) == 1

    late = time.monotonic() + 61
    fresh = RequestTelemetry(
        throttle_window_seconds=60,
        clock=time.monotonic,
    )
    log_filter._telemetry = fresh
    for _ in range(3):
        fresh.note_throttle(
            client_ip="192.0.2.44", method="GET", path="/v1/seat-health/", now=late
        )
    rolled = fresh.flush(now=late + 61)
    assert any("rejections=3" in line for line in rolled)
    assert len(lines) == 2


def test_report_is_not_swallowed_when_the_shape_is_unrecognised(journal):
    """Fail open: losing a 429 report is worse than logging one twice."""
    capture, telemetry, log_filter = journal
    record = logging.LogRecord(
        name="swarm.throttle",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="[RATE_LIMIT_EXCEEDED] something with no arguments",
        args=(),
        exc_info=None,
    )
    assert log_filter.filter(record) is True
    other = logging.LogRecord(
        name="swarm.throttle",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="a different warning entirely",
        args=("value",),
        exc_info=None,
    )
    assert log_filter.filter(other) is True


def test_filter_is_installed_idempotently():
    request_logging.uninstall()
    first = request_logging.install()
    second = request_logging.install()
    assert first is second
    assert logging.getLogger("swarm.throttle").filters.count(first) == 1
    request_logging.uninstall()
    assert logging.getLogger("swarm.throttle").filters == []


def test_repeated_failures_do_not_grow_the_report_formatting_work(journal):
    """Suppression is decided before the report body is rebuilt."""
    _, telemetry, log_filter = journal
    _record(telemetry)
    _reject(_FakeRequest())
    _reject(_FakeRequest())  # sets the thread's "already reported" event
    note = telemetry.format_top_endpoints("192.0.2.44")
    assert "suppressed" in note
    assert "rejections=" in note
    assert len(note.splitlines()) == 1
    sources_note = telemetry.format_sources("192.0.2.44")
    assert len(sources_note.splitlines()) == 1
    assert log_filter.suppressed >= 1


# ---------------------------------------------------------------------------
# 3. The recurrence summary: noisiest client, hottest endpoint, count, and the
#    minimum inter-arrival time that distinguishes a loop from real traffic.
# ---------------------------------------------------------------------------


def test_runaway_loop_is_visible_as_a_sub_second_interarrival(journal):
    capture, telemetry, _ = journal
    _record(telemetry)
    for i in range(200):
        _reject(_FakeRequest())
        telemetry.note_throttle(
            client_ip="192.0.2.44",
            method="GET",
            path="/v1/seat-health/",
            now=time.monotonic(),
        )
    lines = telemetry.flush()
    summary = next(line for line in lines if line.startswith("[RATE_LIMIT_SUMMARY]"))
    assert "rejections=" in summary
    interval = float(re.search(r"min_interarrival_ms=([\d.]+)", summary).group(1))
    assert interval < 1.0, summary


def test_organic_polling_reads_as_slow_not_as_a_loop():
    # A wider bucket window than the 60s rate window, so five rejections a
    # minute apart land in one bucket instead of opening five windows. At the
    # production 60s window these are five separate one-line windows, which is
    # also the right answer.
    telemetry = RequestTelemetry(throttle_window_seconds=600)
    base = 1_000_000.0
    for i in range(5):
        telemetry.note_throttle(
            client_ip="192.0.2.44", method="GET", path="/v1/preferences/", now=base + i * 60.0
        )
    lines = telemetry.flush(now=base + 300.0)
    rollup = next(line for line in lines if line.startswith("[RATE_LIMIT_WINDOW]"))
    assert "min_interarrival_ms=60000.0" in rollup
    assert "rejections=5" in rollup


def test_summary_names_the_noisiest_client_and_the_hottest_endpoint():
    telemetry = RequestTelemetry(throttle_window_seconds=60)
    base = 2_000_000.0
    for i in range(9):
        telemetry.note_throttle(
            client_ip="192.0.2.7", method="GET", path="/v1/chat/{uuid}/messages", now=base + i
        )
    for i in range(4):
        telemetry.note_throttle(
            client_ip="192.0.2.9", method="POST", path="/v1/responses", now=base + i
        )
    for i in range(2):
        telemetry.note_throttle(
            client_ip="192.0.2.9", method="GET", path="/v1/preferences/", now=base + i
        )
    lines = telemetry.flush(now=base + 30.0)
    summary = next(line for line in lines if line.startswith("[RATE_LIMIT_SUMMARY]"))
    assert "rejections=15" in summary
    assert "noisiest_client=192.0.2.7(9)" in summary
    assert 'hottest_endpoint="GET /v1/chat/{uuid}/messages"(9)' in summary
    assert "clients=2" in summary
    assert "buckets=3" in summary


def test_window_rollup_carries_the_caller_and_the_tightest_cadence(journal):
    capture, telemetry, _ = journal
    _record(telemetry)
    for _ in range(4):
        _reject(_FakeRequest())
    lines = telemetry.flush()
    rollup = next(line for line in lines if line.startswith("[RATE_LIMIT_WINDOW]"))
    assert len(rollup.splitlines()) == 1
    assert "client=192.0.2.44" in rollup
    assert "user=42" in rollup
    assert "source=seatHealthPoll" in rollup
    assert 'endpoint="GET /v1/seat-health/"' in rollup
    assert re.search(r"min_interarrival_ms=[\d.]+", rollup)


def test_summary_line_is_bounded_even_with_many_endpoints():
    telemetry = RequestTelemetry(throttle_window_seconds=60)
    base = 3_000_000.0
    long_name = "seat" * 15  # long, but not hex- or token-shaped
    for i in range(500):
        telemetry.note_throttle(
            client_ip=f"192.0.2.{i % 250 + 1}",
            method="GET",
            path=f"/v1/teams/{long_name}{i}/agents/{long_name}{i}/runs/{long_name}{i}/seats/{long_name}{i}",
            now=base + i * 0.01,  # one window
        )
    lines = telemetry.flush(now=base + 600.0)
    summary = next(line for line in lines if line.startswith("[RATE_LIMIT_SUMMARY]"))
    assert len(summary) <= 900
    assert summary.endswith("...")
    assert summary.count("\n") == 0
    assert "rejections=500" in summary


# ---------------------------------------------------------------------------
# 4. No secret, ever, in a log line.
# ---------------------------------------------------------------------------


def test_no_secret_shaped_substring_reaches_any_telemetry_log_line(journal):
    capture, telemetry, _ = journal
    token_path = f"/v1/tickets/{FAKE_KEY}/close"

    # A normal request carrying every credential shape at once.
    telemetry.record(
        client_ip="192.0.2.7",
        method="GET",
        path=f"{token_path}?api_key={FAKE_PAT}#access_token={FAKE_JWT}",
        status_code=401,
        user_key="42",
        source=f"seatHealthPoll {FAKE_PAT}",
        duration_ms=3.0,
        response_bytes=64,
    )
    # And the same shapes on the rate-limit path.
    for _ in range(5):
        _reject(
            _FakeRequest(
                path=token_path,
                source=f"caller/{FAKE_JWT}",
                headers={
                    "X-Swarm-Client-Source": f"caller/{FAKE_JWT}",
                    "Authorization": f"Bearer {FAKE_KEY}",
                },
            )
        )
    telemetry.flush()

    text = capture.text
    assert text, "nothing was logged; the assertions below would be vacuous"
    for secret in (FAKE_KEY, FAKE_PAT, FAKE_JWT):
        assert secret not in text
    # Header names and query keys never appear either: nothing logs them.
    assert "Authorization" not in text
    assert "api_key" not in text
    assert "access_token" not in text
    # The request is still attributed.
    assert "client=192.0.2.7" in text
    assert "/v1/tickets/{token}/close" in text


def test_a_real_throttle_report_still_reaches_the_log(journal):
    """The redaction above must not gut the report it is protecting."""
    capture, telemetry, _ = journal
    _record(telemetry)
    _reject(_FakeRequest())
    report = capture.named("swarm.throttle")[0]
    assert "RATE_LIMIT_EXCEEDED" in report
    assert "Top endpoints" in report
    assert "seat-health" in report


def test_sanitize_field_refuses_to_forge_a_log_line():
    injected = "seatHealthPoll\n[RATE_LIMIT_EXCEEDED] forged line"
    clean = sanitize_field(injected)
    assert "\n" not in clean
    assert "forged line" in clean  # the text survives, the line break does not
    assert REDACTED in sanitize_field(f"bearer {FAKE_KEY}")
    assert REDACTED in sanitize_field(f"pat {FAKE_PAT}")


def test_sanitisation_does_not_eat_ordinary_hyphenated_english():
    """The scanner this replaces once rejected the ordinary word 'ask-user'."""
    for word in ("ask-user", "task-manager", "seat-health", "seek-and-destroy"):
        assert sanitize_field(word) == word
        assert normalize_path(f"/v1/{word}/run") == f"/v1/{word}/run"


def test_path_normalisation_neutralises_a_bare_key_segment():
    assert FAKE_KEY not in normalize_path(f"/v1/x/{FAKE_KEY}")
    assert normalize_path(f"/v1/x/{FAKE_KEY}") == "/v1/x/{token}"


def test_an_unbounded_path_cannot_blow_up_a_log_line():
    telemetry = RequestTelemetry()
    long_path = "/" + "/".join("segment%d" % i for i in range(400))
    line = normalize_path(long_path)
    assert len(line) <= 256
    telemetry.record(
        client_ip="192.0.2.7",
        method="GET",
        path=long_path,
        status_code=404,
        user_key="",
        duration_ms=1.0,
    )


# ---------------------------------------------------------------------------
# 5. Bounded memory.
# ---------------------------------------------------------------------------


def test_ten_thousand_distinct_clients_do_not_grow_the_client_map():
    telemetry = RequestTelemetry(max_clients=64)
    for i in range(10_000):
        telemetry.record(
            client_ip=f"198.51.100.{i % 256}.{i // 256}",
            method="GET",
            path="/v1/preferences/",
            status_code=200,
            user_key="",
            duration_ms=1.0,
        )
    assert telemetry.tracked_clients <= 64


def test_ten_thousand_distinct_clients_do_not_grow_the_throttle_buckets():
    telemetry = RequestTelemetry(max_throttle_buckets=32, throttle_window_seconds=60)
    now = time.monotonic()
    for i in range(10_000):
        telemetry.note_throttle(
            client_ip=f"198.51.100.{i % 256}.{i // 256}",
            method="GET",
            path=f"/v1/agents/{i}/settings",
            now=now + i * 0.001,
        )
    assert telemetry.tracked_throttle_buckets <= 32


def test_idle_clients_are_dropped_so_a_client_scan_cannot_pin_memory():
    telemetry = RequestTelemetry(max_clients=10_000, window_seconds=60)
    base = time.monotonic()
    for i in range(200):
        telemetry.record(
            client_ip=f"198.51.100.1.{i}",
            method="GET",
            path="/v1/preferences/",
            status_code=200,
            user_key="",
            duration_ms=1.0,
            now=base,
        )
    assert telemetry.tracked_clients == 200
    # 20 minutes later the sweep finds nothing worth keeping.
    telemetry.record(
        client_ip="192.0.2.1",
        method="GET",
        path="/v1/preferences/",
        status_code=200,
        user_key="",
        duration_ms=1.0,
        now=base + 1200.0,
    )
    assert telemetry.tracked_clients == 1


def test_a_storm_of_rejections_on_one_client_stays_bounded():
    telemetry = RequestTelemetry(max_throttle_buckets=8, throttle_window_seconds=60)
    now = time.monotonic()
    for i in range(5000):
        telemetry.note_throttle(
            client_ip="192.0.2.44", method="GET", path="/v1/seat-health/", now=now + i * 0.0001
        )
    assert telemetry.tracked_throttle_buckets <= 8
    assert len(telemetry.flush(now=now + 61)) == 2  # one rollup + one summary


def test_concurrent_rejections_count_every_one():
    telemetry = RequestTelemetry(throttle_window_seconds=60)
    seen: list[int] = []
    lock = threading.Lock()

    def worker(name: int) -> None:
        for _ in range(50):
            event = telemetry.note_throttle(
                client_ip=f"192.0.2.{name + 1}",
                method="GET",
                path="/v1/preferences/",
                now=time.monotonic(),
            )
            with lock:
                seen.append(event.rejections)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Four clients x 50 rejections, every one counted exactly once.
    assert sorted(seen) == sorted(list(range(1, 51)) * 4)
    assert telemetry.tracked_throttle_buckets == 4


# ---------------------------------------------------------------------------
# 6. The throttle itself is unchanged.
# ---------------------------------------------------------------------------


def test_response_size_helper_reads_the_body_without_guessing():
    from django.http import HttpResponse, StreamingHttpResponse

    from swarm.middleware import _response_size

    assert _response_size(HttpResponse(b"hello")) == 5
    sized = HttpResponse(b"hello")
    sized["Content-Length"] = "5"
    assert _response_size(sized) == 5
    # A streaming response has no knowable length; say so rather than guess.
    assert _response_size(StreamingHttpResponse(iter([b"a"]))) is None
    assert _response_size(object()) is None


def test_middleware_emits_the_request_line_with_the_real_response(journal):
    from django.http import HttpResponse
    from django.test import RequestFactory

    from swarm.middleware import RequestTelemetryMiddleware

    capture, _, _ = journal
    request = RequestFactory().get(
        "/v1/agents/7/settings?api_key=shhh", HTTP_X_SWARM_CLIENT_SOURCE="agentSettings"
    )
    request.user = None
    middleware = RequestTelemetryMiddleware(lambda _request: HttpResponse(b"hello"))
    response = middleware(request)

    assert response.content == b"hello"
    line = capture.named("swarm.requests")[0]
    assert "\n" not in line
    assert "path=/v1/agents/{int}/settings" in line
    assert "status=200" in line
    assert "bytes=5" in line
    assert "api_key" not in line


def test_throttle_still_allows_exactly_its_configured_budget(monkeypatch):
    from django.core.cache import cache
    from rest_framework.test import APIRequestFactory

    from swarm import throttling

    rates = {"anon": "5/min", "user": "5/min", "anon_read": "20/min", "user_read": "20/min"}
    monkeypatch.setattr(throttling.ReadBurstAnonRateThrottle, "THROTTLE_RATES", rates)
    monkeypatch.setattr(throttling.ReadBurstUserRateThrottle, "THROTTLE_RATES", rates)
    cache.clear()
    try:
        throttle = throttling.ReadBurstAnonRateThrottle()
        request = APIRequestFactory().get("/health", REMOTE_ADDR="192.0.2.44")
        request.user = AnonymousUser()
        allowed = sum(1 for _ in range(25) if throttle.allow_request(request, None))
        assert allowed == 20, "observability changed the budget"
        assert (throttle.num_requests, throttle.duration) == (20, 60)
    finally:
        cache.clear()


class _ThrottleRequest:
    method = "GET"
    META = {"REMOTE_ADDR": "192.0.2.44"}
    user = None
    headers: dict = {}


def test_rate_window_constant_matches_the_configured_rates():
    from swarm import throttle_defaults

    assert throttle_defaults.RATE_WINDOW_SECONDS == 60
    for rate in (
        throttle_defaults.ANON_RATE,
        throttle_defaults.USER_RATE,
        throttle_defaults.ANON_READ_RATE,
        throttle_defaults.USER_READ_RATE,
    ):
        assert rate.split("/")[1] == "min"
        assert int(rate.split("/")[0]) / 60 < 10  # still bounded, still req/s
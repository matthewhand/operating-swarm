"""#800 — server-side request telemetry: sliding-window burst forensics."""

from __future__ import annotations

import threading
import time

from swarm.core.request_telemetry import (
    RequestTelemetry,
    default_telemetry,
    get_client_burst_summary,
)


def _record(telemetry: RequestTelemetry, ip: str, path: str, source: str = "") -> None:
    telemetry.record(
        client_ip=ip,
        method="GET",
        path=path,
        status_code=200,
        user_key="u1",
        source=source,
        duration_ms=1.0,
    )


def test_record_and_summary_counts_recent_paths():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=100)
    now = time.monotonic()
    for _ in range(3):
        telemetry.record(
            client_ip="192.0.2.7",
            method="GET",
            path="/v1/preferences/",
            status_code=200,
            user_key="u1",
            source="prefsQuery",
            duration_ms=2.0,
            now=now,
        )
    telemetry.record(
        client_ip="192.0.2.7",
        method="PATCH",
        path="/v1/preferences/",
        status_code=200,
        user_key="u1",
        source="saveUserPrefs",
        duration_ms=5.0,
        now=now,
    )
    summary = telemetry.client_summary("192.0.2.7", now=now)
    assert summary["total"] == 4
    top = summary["top_paths"]
    assert top[0]["path"] == "/v1/preferences/"
    assert top[0]["count"] == 4


def test_window_expiry_drops_old_records():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=100)
    now = time.monotonic()
    _record(telemetry, "192.0.2.7", "/v1/old/")
    summary = telemetry.client_summary("192.0.2.7", now=now + 61)
    assert summary["total"] == 0


def test_max_records_per_client_bounds_memory():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=5)
    now = time.monotonic()
    for i in range(50):
        telemetry.record(
            client_ip="192.0.2.7",
            method="GET",
            path=f"/v1/p{i}/",
            status_code=200,
            user_key="u1",
            source="",
            duration_ms=1.0,
            now=now + i * 0.001,
        )
    summary = telemetry.client_summary("192.0.2.7", now=now + 1)
    assert summary["total"] == 5


def test_min_interval_detects_sub_second_loops():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=100)
    base = time.monotonic()
    for i in range(5):
        telemetry.record(
            client_ip="192.0.2.7",
            method="GET",
            path="/v1/preferences/",
            status_code=200,
            user_key="u1",
            source="loop",
            duration_ms=1.0,
            now=base + i * 0.05,  # 50ms apart — a tight loop
        )
    summary = telemetry.client_summary("192.0.2.7", now=base + 1)
    prefs_row = next(r for r in summary["top_paths"] if r["path"] == "/v1/preferences/")
    assert prefs_row["min_interval_ms"] == 50.0


def test_sources_breakdown_lists_callers():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=100)
    now = time.monotonic()
    _record(telemetry, "192.0.2.7", "/v1/a/", source="compA")
    _record(telemetry, "192.0.2.7", "/v1/a/", source="compA")
    _record(telemetry, "192.0.2.7", "/v1/b/", source="compB")
    summary = telemetry.client_summary("192.0.2.7", now=now)
    sources = {row["source"]: row["count"] for row in summary["sources"]}
    assert sources["compA"] == 2
    assert sources["compB"] == 1


def test_clients_are_isolated():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=100)
    now = time.monotonic()
    _record(telemetry, "192.0.2.7", "/v1/a/")
    _record(telemetry, "192.0.2.8", "/v1/b/")
    assert telemetry.client_summary("192.0.2.7", now=now)["total"] == 1
    assert telemetry.client_summary("192.0.2.8", now=now)["total"] == 1


def test_record_is_thread_safe():
    telemetry = RequestTelemetry(window_seconds=60, max_records_per_client=1000)
    def worker(n: int) -> None:
        for i in range(200):
            _record(telemetry, f"192.0.2.{n + 10}", f"/v1/p{i % 7}/")
    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total = sum(
        telemetry.client_summary(f"192.0.2.{n + 10}")["total"] for n in range(4)
    )
    assert total == 800


def test_default_telemetry_is_a_singleton():
    assert default_telemetry() is default_telemetry()

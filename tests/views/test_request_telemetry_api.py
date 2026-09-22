"""#800 — 429 burst telemetry: middleware recording, forensic handler, API."""

from __future__ import annotations

import pytest

from swarm.core import request_telemetry
from swarm.core.request_telemetry import RequestTelemetry, default_telemetry

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _fresh_default_telemetry(monkeypatch):
    """Isolate tests from the process-wide singleton."""
    monkeypatch.setattr(
        request_telemetry, "_INSTANCE", RequestTelemetry(window_seconds=120)
    )
    yield


def test_middleware_records_requests_into_window(authenticated_client):
    from swarm.middleware import RequestTelemetryMiddleware  # noqa: F401 — wired in settings

    authenticated_client.get("/v1/preferences/")
    authenticated_client.get("/v1/blueprints/")
    summary = default_telemetry().client_summary("127.0.0.1")
    paths = {row["path"] for row in summary["top_paths"]}
    assert "/v1/preferences/" in paths
    assert "/v1/blueprints/" in paths


def test_client_source_header_surfaces_in_telemetry(authenticated_client):
    authenticated_client.get(
        "/v1/preferences/", headers={"X-Swarm-Client-Source": "prefsQuery"}
    )
    summary = default_telemetry().client_summary("127.0.0.1")
    sources = [row["source"] for row in summary["sources"]]
    assert "prefsQuery" in sources


def test_telemetry_requests_endpoint_returns_own_window(authenticated_client):
    authenticated_client.get("/v1/preferences/", headers={"X-Swarm-Client-Source": "me"})
    response = authenticated_client.get("/v1/telemetry/requests/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "request_telemetry"
    assert body["client_ip"] == "127.0.0.1"
    assert any(row["path"] == "/v1/preferences/" for row in body["top_paths"])


def test_throttled_exception_logs_forensics(monkeypatch):
    from rest_framework import exceptions

    from swarm.views import exception_handlers

    # The app's dictConfig swallows propagation, so capture the module logger
    # directly instead of relying on caplog.
    logged: list[str] = []

    class _FakeLogger:
        def warning(self, msg, *args):
            logged.append(msg % args if args else msg)

        def debug(self, *args, **kwargs):
            pass

    monkeypatch.setattr(exception_handlers, "logger", _FakeLogger())

    class FakeRequest:
        method = "GET"
        path = "/v1/preferences/"
        META = {"REMOTE_ADDR": "10.9.9.9"}
        user = None

        headers = {"X-Swarm-Client-Source": "loopingHook"}

    telemetry = default_telemetry()
    for i in range(3):
        telemetry.record(
            client_ip="10.9.9.9",
            method="PATCH",
            path="/v1/preferences/",
            status_code=200,
            user_key="u1",
            source="loopingHook",
            duration_ms=1.0,
            now=1000.0 + i * 0.01,
        )
    original_handler = exception_handlers.drf_exception_handler
    sentinel = object()
    monkeypatch.setattr(
        exception_handlers, "drf_exception_handler", lambda exc, ctx: sentinel
    )
    response = exception_handlers.swarm_exception_handler(
        exceptions.Throttled(wait=7), {"request": FakeRequest()}
    )
    assert response is sentinel
    text = "\n".join(logged)
    assert "RATE_LIMIT_EXCEEDED" in text
    assert "10.9.9.9" in text
    assert "/v1/preferences/" in text
    assert "loopingHook" in text


def test_throttle_incidents_ring_serves_via_api(authenticated_client):
    from swarm.views.telemetry_api import record_throttle_incident

    record_throttle_incident(
        {"ts": 1.0, "client_ip": "10.5.5.5", "path": "/v1/preferences/", "wait": 12}
    )
    response = authenticated_client.get("/v1/telemetry/throttles/")
    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "throttle_incidents"
    assert any(
        incident["path"] == "/v1/preferences/" for incident in body["incidents"]
    )

"""The seat doctor over HTTP, and the line it must not cross (#1658).

The batch probe is cheap liveness and drives the rail's `⚠ broken` label. The
doctor is a bounded evidence-backed audit whose `ok` is *stricter* (only a proved
turn is `ok`; a `--version` and a health GET are `unverified`). Merging a doctor's
verdict into the liveness store would let a 40-second audit silently relabel the
rail — the exact false-positive failure the labelling work already had to undo
once, when probes that lacked information reported `broken` for working seats.
"""

from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

pytestmark = pytest.mark.django_db

from swarm.core.seat_health import VALID_KINDS  # noqa: E402
from swarm.views.seat_health_api import MAX_SEATS  # noqa: E402


def _client() -> APIClient:
    client = APIClient()
    client.force_authenticate(user=None)
    return client


def test_the_doctor_route_resolves():
    # Both spellings are registered, matching the seats-health convention:
    # the unsuffixed name is the slashed path, `-no-slash` is the bare one.
    assert reverse("seats-doctor") == "/v1/seats/doctor/"
    assert reverse("seats-doctor-no-slash") == "/v1/seats/doctor"


def test_an_unknown_kind_is_rejected_rather_than_silently_dropped():
    """"kind=ap" must not quietly become an empty audit that reads as healthy."""
    response = _client().get("/v1/seats/doctor?kind=ap")
    assert response.status_code == 400
    body = response.json()
    assert "ap" in body["error"]
    assert set(body["valid"]) == set(VALID_KINDS)


def test_a_non_integer_limit_is_rejected():
    response = _client().get("/v1/seats/doctor?limit=lots")
    assert response.status_code == 400
    assert "integer" in response.json()["error"]


def test_a_zero_or_negative_limit_is_clamped_not_honoured():
    """limit=0 meaning "audit nothing" would read as "everything is fine"."""
    for raw in ("0", "-5"):
        body = _client().get(f"/v1/seats/doctor?limit={raw}&kind=cli").json()
        rows = body["results"]
        # Clamped to 1 -> at least one CLI seat is audited. Honoured -> zero rows,
        # which is indistinguishable from "no seat is broken".
        assert len(rows) == 1, raw


def test_a_limit_above_the_cap_is_clamped_to_the_cap():
    """An uncapped scan is the risk here, so pin the bound, not the plumbing."""
    body = _client().get(f"/v1/seats/doctor?limit={MAX_SEATS + 500}&kind=cli").json()
    assert len(body["results"]) <= MAX_SEATS


def test_deep_is_off_unless_asked_for():
    for raw, expected in (("0", False), ("", False), ("1", True), ("true", True), ("yes", True)):
        response = _client().get(f"/v1/seats/doctor?kind=cli&deep={raw}")
        assert response.status_code == 200
        assert response.json()["deep"] is expected, raw


def test_the_report_is_read_only_and_says_so():
    body = _client().get("/v1/seats/doctor?kind=cli&limit=1").json()
    assert body["object"] == "seat_doctor_report"
    assert body["read_only"] is True
    assert "totals" in body and "buckets" in body


def test_running_the_doctor_never_writes_into_the_liveness_store():
    """The separation this file exists to protect.

    `probe_seats` is what the 60s poll calls, and its rows are what the rail label
    is derived from. A doctor verdict is strictly better evidence but a different
    claim, so the audit must leave the store untouched: a seat that is merely
    `unverified` (a live binary, no proved turn) must not become `broken`, and a
    seat the doctor bucketed must not gain a liveness `reason` it never had.
    """
    from swarm.core import seat_health

    seat_health.probe_seats([{"kind": "cli", "seat_id": "a-real-binary", "cli": "python3"}])
    before = seat_health.seat_state("cli", "a-real-binary")

    _client().get("/v1/seats/doctor?kind=cli&limit=1")

    assert seat_health.seat_state("cli", "a-real-binary") == before
    row = seat_health.probe_seat("cli", "a-real-binary", cli="python3")
    # Nothing from the audit may masquerade as a liveness verdict.
    assert row.state in {"ok", "broken", "unknown"}
    assert "remediation" not in row.reason.lower()

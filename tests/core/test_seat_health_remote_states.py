"""A remote probe must distinguish 'down' from 'never probed' (#1658).

Third instance of the same fail-closed bug, found by looking at live output
rather than at the tests: `remotes.check_health` deliberately reports `UNKNOWN`
plus a machine-readable `gap` when it could not send a request at all (the
remote was never added, or its base URL is a `192.0.2.0/24` placeholder). The
seat probe was collapsing every `ok=False` into `broken`, which relabelled every
not-yet-configured remote with a `⚠ broken` label — and quietly undid the remotes
work whose whole point was "never announce an offline gateway for a remote that
was never configured".

Only positive evidence of failure may produce `broken`.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from swarm.core import seat_health
from swarm.core.seat_health import STATE_BROKEN, STATE_OK, STATE_UNKNOWN, probe_seat


def _probe_with(monkeypatch: pytest.MonkeyPatch, result: object) -> str:
    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(remotes_core, "check_health", lambda *_a, **_k: result)
    return probe_seat("remote", "some-remote", force=True).state


def test_a_reachable_remote_is_ok(monkeypatch):
    state = _probe_with(
        monkeypatch, SimpleNamespace(ok=True, state="UP", detail="", gap="", latency_ms=3)
    )
    assert state == STATE_OK


def test_a_positively_down_remote_is_broken(monkeypatch):
    state = _probe_with(
        monkeypatch,
        SimpleNamespace(ok=False, state="DOWN", detail="connection refused", gap="", latency_ms=1),
    )
    assert state == STATE_BROKEN


def test_a_never_probed_remote_is_unknown_not_broken(monkeypatch):
    """A `gap` means no request was sent. That is missing information."""
    state = _probe_with(
        monkeypatch,
        SimpleNamespace(
            ok=False,
            state="UNKNOWN",
            detail="no base_url is set; the catalog default is a placeholder address",
            gap="remote_base_url_placeholder",
            latency_ms=0,
        ),
    )
    assert state == STATE_UNKNOWN


def test_an_unknown_state_without_a_gap_is_still_not_broken(monkeypatch):
    state = _probe_with(
        monkeypatch, SimpleNamespace(ok=False, state="UNKNOWN", detail="", gap="", latency_ms=0)
    )
    assert state == STATE_UNKNOWN


def test_a_probe_that_raises_is_unknown_not_broken(monkeypatch):
    """The UI must never see an exception, and a crash is not proof of a fault."""
    from swarm.core import remotes as remotes_core

    def boom(*_a, **_k):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(remotes_core, "check_health", boom)
    verdict = probe_seat("remote", "some-remote", force=True)
    assert verdict.state == STATE_UNKNOWN
    assert "RuntimeError" in verdict.reason


def test_an_unrecognised_state_fails_open(monkeypatch):
    state = _probe_with(
        monkeypatch, SimpleNamespace(ok=False, state="weird-new-state", detail="", gap="", latency_ms=0)
    )
    assert state == STATE_UNKNOWN


def test_the_reason_survives_so_the_operator_sees_why(monkeypatch):
    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(
        remotes_core,
        "check_health",
        lambda *_a, **_k: SimpleNamespace(
            ok=False, state="DOWN", detail="tcp 203.0.113.32:3100 refused", gap="", latency_ms=7
        ),
    )
    verdict = probe_seat("remote", "rakazo", force=True)
    assert verdict.state == STATE_BROKEN
    assert "refused" in verdict.reason


def test_a_real_placeholder_remote_is_not_labelled_broken(monkeypatch):
    """The exact regression: the catalog's own placeholder default."""
    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(
        remotes_core,
        "check_health",
        lambda *_a, **_k: SimpleNamespace(
            ok=False,
            state="UNKNOWN",
            detail="no base_url is set; the catalog default http://192.0.2.1:3000 is a placeholder address",
            gap="remote_base_url_placeholder",
            latency_ms=0,
        ),
    )
    verdict = seat_health.probe_seat("remote", "flowise", force=True)
    assert verdict.state == STATE_UNKNOWN
    # `broken` is derived in as_dict(), not a field on the dataclass.
    assert verdict.as_dict()["broken"] is False


def test_the_gap_code_travels_with_the_row(monkeypatch):
    """#1783: the client needs the CODE, not the prose.

    Remote health now polls over `POST /v1/seats/health` (one write for the
    whole list) instead of one `POST /v1/remotes/<id>/health/` per remote, and
    the batch row is the only thing it has to go on. `state: unknown` alone
    cannot tell "this remote was never configured" from "our probe raised", and
    the UI renders those differently — `unconfigured` versus no verdict at all.
    So the machine-readable `gap` is part of the payload, rather than being
    re-derived by pattern-matching `reason` in another language.
    """
    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(
        remotes_core,
        "check_health",
        lambda *_a, **_k: SimpleNamespace(
            ok=False, state="UNKNOWN", detail="not added to this install", gap="remote_not_added", latency_ms=0
        ),
    )
    row = seat_health.probe_seat("remote", "herdr", force=True).as_dict()
    assert row["gap"] == "remote_not_added"
    assert row["state"] == STATE_UNKNOWN


def test_a_probed_remote_reports_no_gap(monkeypatch):
    """The default must be empty, not a code that means "nothing was probed"."""
    from swarm.core import remotes as remotes_core

    monkeypatch.setattr(
        remotes_core,
        "check_health",
        lambda *_a, **_k: SimpleNamespace(ok=True, state="UP", detail="", gap="", latency_ms=2),
    )
    assert seat_health.probe_seat("remote", "rakazo", force=True).as_dict()["gap"] == ""


def test_the_batch_row_carries_the_gap_for_every_remote(monkeypatch):
    """The shape the batched remote poll actually reads: a list of rows."""
    from swarm.core import remotes as remotes_core

    def fake_check(remote_id, **_k):
        if remote_id == "placeholder":
            return SimpleNamespace(
                ok=False,
                state="UNKNOWN",
                detail="placeholder address",
                gap="remote_base_url_placeholder",
                latency_ms=0,
            )
        return SimpleNamespace(ok=True, state="UP", detail="", gap="", latency_ms=1)

    monkeypatch.setattr(remotes_core, "check_health", fake_check)
    seat_health.clear_cache()

    rows = seat_health.probe_seats(
        [
            {"kind": "remote", "seat_id": "placeholder"},
            {"kind": "remote", "seat_id": "live"},
        ],
        force=True,
    )
    by_id = {row["seat_id"]: row for row in rows}
    assert by_id["placeholder"]["gap"] == "remote_base_url_placeholder"
    assert by_id["placeholder"]["state"] == STATE_UNKNOWN
    assert by_id["live"]["gap"] == ""
    assert by_id["live"]["state"] == STATE_OK

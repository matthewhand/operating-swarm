"""Seat health across API / CLI / remote seats (#1658 follow-up).

Contract pinned here:
  * one honest verdict per seat, for every kind
  * remotes reuse the existing `check_health`; API seats reuse the existing
    `probe_llm_profile`; CLIs get a cheap liveness check (binary + --version)
  * an unknown kind or a non-seat id is `unknown`, never a false `broken`
  * a probe never raises at the caller — a status poll must not 500
  * a real turn failure promotes a reachable seat to `broken`, and a later
    success or a good probe clears it (that is what makes the UI self-healing)
  * verdicts are cached, so a chatty client costs one probe per TTL
"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from swarm.core import seat_health
from swarm.core.seat_health import (
    STATE_BROKEN,
    STATE_OK,
    STATE_UNKNOWN,
    clear_cache,
    is_skippable,
    note_turn_failure,
    note_turn_success,
    probe_seat,
    probe_seats,
    seat_state,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _clear():
    clear_cache()
    yield
    clear_cache()


def test_an_unknown_kind_is_unknown_not_broken():
    verdict = probe_seat("quantum", "seat-1")
    assert verdict.state == STATE_UNKNOWN
    assert "unknown seat kind" in verdict.reason


@pytest.mark.parametrize("seat_id", ["", "   ", "all", "unassigned", "none"])
def test_non_seat_ids_are_never_probed(seat_id):
    assert is_skippable(seat_id)
    assert probe_seat("remote", seat_id).state == STATE_UNKNOWN


def test_a_healthy_remote_reports_ok():
    class _Result:
        ok = True
        state = "UP"
        detail = "http 200 on /api/health (live mode)"
        latency_ms = 12
        http_status = 200

    with patch("swarm.core.remotes.check_health", return_value=_Result()):
        verdict = probe_seat("remote", "hermes")
    assert verdict.state == STATE_OK
    assert verdict.reason == ""
    assert verdict.latency_ms == 12


def test_a_down_remote_reports_broken_with_the_servers_reason():
    class _Result:
        ok = False
        state = "DOWN"
        detail = "connect ECONNREFUSED 127.0.0.1:9"
        latency_ms = 3
        http_status = 0

    with patch("swarm.core.remotes.check_health", return_value=_Result()):
        verdict = probe_seat("remote", "anythingllm")
    assert verdict.state == STATE_BROKEN
    assert "ECONNREFUSED" in verdict.reason


def test_a_remote_probe_that_explodes_is_unknown_not_a_500():
    """The original intent — "not a 500" — still holds, and is still asserted.

    What changed is the STATE. This test used to require `broken`, i.e. it
    encoded the fail-closed mistake: a probe that raised on OUR side was reported
    as proof the remote was faulty. The live rail then labelled ~30 working seats
    broken, and the same class of bug had to be undone three separate times in
    this module. A crash is missing information, so it is `unknown` — the UI
    still gets a verdict instead of an exception, which was the real contract.
    """
    with patch("swarm.core.remotes.check_health", side_effect=RuntimeError("boom")):
        verdict = probe_seat("remote", "n8n")
    assert verdict.state == STATE_UNKNOWN
    assert "RuntimeError" in verdict.reason
    # Still a verdict row, never a raised exception — the original guarantee.
    assert verdict.as_dict()["seat_id"] == "n8n"


def test_an_api_probe_that_explodes_is_unknown_not_a_500():
    """Same correction as the remote case, for the api probe.

    The provider may be perfectly healthy while our own call to it fails (a bad
    base_url, a DNS blip, a missing optional dependency). Only a verdict the
    provider actually returned may be `broken`.
    """
    with patch("swarm.core.llm_profile_probe.probe_llm_profile", side_effect=RuntimeError("boom")):
        verdict = probe_seat("api", "some_agent", base_url="http://x.invalid", model="m")
    assert verdict.state == STATE_UNKNOWN
    assert "RuntimeError" in verdict.reason


def test_a_declared_cli_binary_that_is_missing_is_broken():
    """The caller said which binary it means, and it is not installed."""
    verdict = probe_seat("cli", "kilocode-agent", cli="definitely-not-a-real-cli-xyz")
    assert verdict.state == STATE_BROKEN
    assert "not installed" in verdict.reason


def test_a_seat_id_that_is_not_a_binary_is_unknown_not_broken():
    """#1658 regression: mirror/alias seats (hass-eng, openswarm-agy) work.

    Their rail id is not a binary on this host. "Not on PATH" for a name we
    were never told is the meaning of is missing information, and calling that
    broken labelled every working mirror in the rail.
    """
    verdict = probe_seat("cli", "hass-eng")
    assert verdict.state == STATE_UNKNOWN
    assert "not a binary" in verdict.reason


def test_a_cli_with_no_name_at_all_is_unknown():
    assert probe_seat("cli", "").state == STATE_UNKNOWN


def test_a_cli_that_answers_version_is_ok():
    import shutil

    if not shutil.which("python3") and not shutil.which("python"):
        pytest.skip("no python on PATH to stand in for a CLI")
    verdict = probe_seat("cli", "python3")
    assert verdict.state == STATE_OK


def test_a_cli_that_exits_non_zero_is_broken():
    import shutil
    import sys

    if not shutil.which("false"):
        pytest.skip("no `false` binary on PATH")
    verdict = probe_seat("cli", "false")
    assert verdict.state == STATE_BROKEN
    assert "--version" in verdict.reason


def test_an_api_seat_with_no_provider_is_unknown_not_broken():
    """#1658 regression: most API seats inherit their profile server-side.

    The rail sends no provider/model for them, so there is nothing to probe.
    Calling that broken labelled every API seat broken, including ones a live
    sweep had just seen answer.
    """
    verdict = probe_seat("api", "mystery_agent", base_url="", model="")
    assert verdict.state == STATE_UNKNOWN
    assert "inherits its profile" in verdict.reason


def test_an_api_seat_uses_the_existing_profile_probe():
    captured: dict = {}

    def _probe(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "latency_ms": 42, "error_class": None, "hint": ""}

    with patch("swarm.core.llm_profile_probe.probe_llm_profile", _probe):
        verdict = probe_seat(
            "api",
            "security_reviewer",
            base_url="http://203.0.113.30:8000/v1",
            model="auxiliary",
        )
    assert verdict.state == STATE_OK
    assert captured["action"] == "test"
    assert captured["model"] == "auxiliary"
    assert verdict.latency_ms == 42


def test_a_rejected_api_model_is_broken_with_the_hint_not_the_secret():
    with patch(
        "swarm.core.llm_profile_probe.probe_llm_profile",
        return_value={
            "ok": False,
            "latency_ms": 5,
            "error_class": "model_missing",
            "hint": "That model is not available on this gateway.",
        },
    ):
        verdict = probe_seat("api", "roadmap", base_url="http://gw/v1", model="nope-9")
    assert verdict.state == STATE_BROKEN
    assert "not available" in verdict.reason


def test_a_bad_base_url_is_unknown_not_broken():
    """A malformed URL is OUR input being wrong, not the provider being down.

    Renamed from `test_a_probe_that_raises_is_broken_not_a_500`: the "not a 500"
    guarantee is unchanged and still asserted, but requiring `broken` here
    encoded the fail-closed mistake — an unparseable base_url would have labelled
    the seat faulty when the provider was never even contacted.
    """
    with patch(
        "swarm.core.llm_profile_probe.probe_llm_profile", side_effect=ValueError("bad url")
    ):
        verdict = probe_seat("api", "roadmap", base_url="::::", model="auxiliary")
    assert verdict.state == STATE_UNKNOWN
    assert "ValueError" in verdict.reason
    assert verdict.as_dict()["seat_id"] == "roadmap"


def test_a_turn_failure_promotes_a_reachable_seat_and_recovers():
    """A dead turn marks the seat broken, keeps the reason, and heals.

    The reason is the whole point of `note_turn_failure`: a bare `broken` tells
    the user nothing, and the string is the only evidence the seat's own
    liveness probe could never have produced (the probe forks `grok
    --version`, which passes while every real turn 402s).

    The previous assertion here was
    ``assert "402" in probe_seat(*ref, force=True).reason or True`` — `or`
    returns its first operand, so the trailing `True` made it
    unconditionally true, in the very test whose stated purpose is "reason
    kept on the verdict". It could not fail.
    ``tests/core/test_seat_health_fail_open.py`` asserts the *state*
    transition for `note_turn_failure`; nothing asserted the reason, which is
    why replacing it with a real assertion is a tightening, not a relaxation.
    """
    ref = ("cli", "grok")
    probe_seat("cli", "grok", cli="python3")  # reachable
    assert seat_state(*ref) == STATE_OK

    reason = "API error (status 402): usage balance exhausted"
    verdict = note_turn_failure(*ref, reason)
    assert seat_state(*ref) == STATE_BROKEN

    # 1. The verdict handed back to the caller carries the reason verbatim.
    assert verdict.state == STATE_BROKEN
    assert verdict.reason == reason
    assert "402" in verdict.reason

    # 2. The cached verdict the UI polls also carries it -- this is the read
    #    that never re-probes. Read without `force=True` on purpose: forcing
    #    would fork the real `grok` binary and overwrite the stored reason
    #    with a fresh liveness result, which is a different assertion.
    cached = probe_seat(*ref)
    assert cached.state == STATE_BROKEN
    assert cached.reason == reason
    assert "402" in cached.reason
    assert cached.as_dict()["reason"] == reason

    # 3. A reason-less verdict is refused, so `reason or "turn failed"` can
    #    never be the thing that satisfies the assertion above.
    blank = note_turn_failure("cli", "no-reason-seat", "")
    assert blank.reason == "turn failed", (
        "an empty turn-failure reason must get the explicit fallback, so the "
        "assertions above can only pass on the caller's own text"
    )

    note_turn_success(*ref)
    assert seat_state(*ref) == STATE_OK
    assert probe_seat(*ref).reason == "", "a recovered seat keeps no stale reason"


def test_a_verdict_is_cached_until_the_ttl_expires():
    calls: list[str] = []

    class _Result:
        ok = True
        state = "UP"
        detail = "fine"
        latency_ms = 1
        http_status = 200

    def _health(remote_id, **_kwargs):
        calls.append(remote_id)
        return _Result()

    with patch("swarm.core.remotes.check_health", _health):
        probe_seat("remote", "rakazo")
        probe_seat("remote", "rakazo")
        assert len(calls) == 1
        probe_seat("remote", "rakazo", force=True)
        assert len(calls) == 2


def test_batch_probe_never_raises_and_skips_junk_rows():
    class _Result:
        ok = False
        state = "DOWN"
        detail = "down"
        latency_ms = 1
        http_status = 500

    with patch("swarm.core.remotes.check_health", return_value=_Result()):
        rows = probe_seats(
            [
                {"kind": "remote", "seat_id": "n8n"},
                "not a dict",
                {"kind": "cli", "seat_id": "n8n-seat", "cli": "definitely-not-real-xyz"},
                {"kind": "nope", "seat_id": "x"},
            ]
        )
    assert len(rows) == 3  # the "not a dict" row is skipped, not turned into a verdict
    by_id = {row["seat_id"]: row for row in rows}
    assert by_id["n8n"]["broken"] is True
    # An unrecognised kind is reported as unknown, never as a false "broken".
    assert by_id["x"]["kind"] == "nope"
    assert by_id["x"]["state"] == STATE_UNKNOWN
    assert by_id["x"]["broken"] is False
    for row in rows:
        assert set(row) >= {"seat_id", "kind", "state", "reason", "latency_ms", "checked_at", "broken"}


def test_batch_probe_is_capped():
    rows = probe_seats([{"kind": "remote", "seat_id": f"r{i}"} for i in range(200)])
    assert len(rows) <= seat_health.MAX_BATCH


def test_checked_at_is_epoch_millis():
    before = int(time.time() * 1000)
    row = probe_seat("cli", "x", cli="definitely-not-real-xyz").as_dict()
    assert row["checked_at"] >= before - 2000

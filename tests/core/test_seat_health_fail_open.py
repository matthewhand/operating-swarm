"""No probe may report `broken` without a verdict the target actually gave us.

This is the FOURTH time the same defect class has been found in
`seat_health._probe_*`, and the reason it keeps recurring is that each kind has
its own probe and only one of them was ever checked against the rule.

The rule, stated once: `broken` requires positive evidence. A probe that
crashed, lacked the information it needed, or was asked about a target it never
reached must report `unknown`. A signal that cries wolf is worse than no signal
— the first version of this feature labelled ~30 working seats broken.

The one legitimate `broken` is `note_turn_failure`: a real turn actually failed.
That is evidence, not a guess, and this file pins that too so nobody "fixes" it
into `unknown` later.
"""

from __future__ import annotations

import pytest

from swarm.core import seat_health
from swarm.core.seat_health import (
    STATE_BROKEN,
    STATE_OK,
    STATE_UNKNOWN,
    note_turn_success,
    probe_seat,
    seat_state,
)


def test_an_api_probe_that_raises_is_unknown_not_broken(monkeypatch: pytest.MonkeyPatch):
    """A crash on OUR side says nothing about the provider's health."""
    from swarm.core import llm_profile_probe

    def boom(*_a, **_k):
        raise RuntimeError("probe exploded")

    monkeypatch.setattr(llm_profile_probe, "probe_llm_profile", boom)
    verdict = probe_seat("api", "some_agent", base_url="http://x.invalid", model="m", force=True)
    assert verdict.state == STATE_UNKNOWN
    assert "RuntimeError" in verdict.reason
    assert "no verdict" in verdict.reason


def test_an_api_probe_that_raises_does_not_mark_the_seat_broken(monkeypatch: pytest.MonkeyPatch):
    """The store is what the rail label reads, so assert on the stored state too."""
    from swarm.core import llm_profile_probe

    monkeypatch.setattr(
        llm_profile_probe,
        "probe_llm_profile",
        lambda *_a, **_k: (_ for _ in ()).throw(OSError("network gone")),
    )
    probe_seat("api", "stored_api_seat", base_url="http://x.invalid", model="m", force=True)
    assert seat_state("api", "stored_api_seat") == STATE_UNKNOWN


def test_a_provider_that_answers_unhealthy_is_still_broken(monkeypatch: pytest.MonkeyPatch):
    """The fix must not neuter the probe: a real negative verdict is evidence."""
    from swarm.core import llm_profile_probe

    monkeypatch.setattr(
        llm_profile_probe,
        "probe_llm_profile",
        lambda *_a, **_k: {"ok": False, "error_class": "auth", "hint": "Unauthorized"},
    )
    verdict = probe_seat("api", "auth_seat", base_url="http://x.invalid", model="m", force=True)
    assert verdict.state == STATE_BROKEN
    assert "Unauthorized" in verdict.reason


def test_a_real_turn_failure_is_the_one_legitimate_broken():
    """`note_turn_failure` records evidence, not a guess. Do not weaken it."""
    seat_health.note_turn_failure("api", "turn_failed_seat", "provider returned 500")
    assert seat_state("api", "turn_failed_seat") == STATE_BROKEN
    note_turn_success("api", "turn_failed_seat")
    assert seat_state("api", "turn_failed_seat") != STATE_BROKEN


def test_a_probe_that_raises_does_not_overwrite_a_known_bad_verdict(monkeypatch: pytest.MonkeyPatch):
    """A later crash must not erase a real fault we already established."""
    from swarm.core import llm_profile_probe

    monkeypatch.setattr(
        llm_profile_probe,
        "probe_llm_profile",
        lambda *_a, **_k: {"ok": False, "error_class": "auth", "hint": "Unauthorized"},
    )
    probe_seat("api", "sticky_seat", base_url="http://x.invalid", model="m", force=True)
    assert seat_state("api", "sticky_seat") == STATE_BROKEN

    monkeypatch.setattr(
        llm_profile_probe,
        "probe_llm_profile",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("later crash")),
    )
    verdict = probe_seat("api", "sticky_seat", base_url="http://x.invalid", model="m", force=True)
    # The fresh verdict is `unknown` (no evidence obtained now) — but it must not
    # be reported as if the seat recovered, and it must not have flipped to ok.
    assert verdict.state == STATE_UNKNOWN
    assert seat_state("api", "sticky_seat") != STATE_OK

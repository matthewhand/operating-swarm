"""#1181 — a DOWN verdict needs a confirming second probe.

One failed probe (TCP refused / reset while :8002 or the gateway restarts)
used to flip every seat "down" at once and let the #1169 pre-flight veto a
turn on evidence one transient probe deep. Contract: only a *confirmed*
second DOWN is down; UP/DEGRADED/AUTH verdicts stay single-shot (they are
real HTTP answers, not transport noise).
"""

from __future__ import annotations

from unittest.mock import patch

from swarm.core import remotes


def _health(state: str, ok: bool | None = None) -> remotes.HealthResult:
    return remotes.HealthResult(
        remote="letta-demo",
        ok=ok if ok is not None else state == "UP",
        state=state,
        detail=f"state {state}",
        http_status=200 if state == "UP" else None,
    )


def _cfg():
    return {"remotes": {"letta-demo": {"kind": "letta"}}}


def test_transient_down_recovers_to_up_without_copy():
    """DOWN then UP on the confirm probe ⇒ the seat reports UP; pre-flight passes the turn."""
    with patch.object(
        remotes, "_check_health_once", side_effect=[_health("DOWN"), _health("UP")]
    ) as once, patch("time.sleep") as slept:
        result = remotes.check_health("letta-demo", config=_cfg(), timeout=6)
        assert result.state == "UP"
        assert once.call_count == 2
        slept.assert_called_once()
    with patch.object(
        remotes, "_check_health_once", side_effect=[_health("DOWN"), _health("UP")]
    ), patch("time.sleep"):
        assert remotes.remote_down_preflight("letta-demo", config=_cfg()) is None


def test_confirmed_down_still_down_with_copy():
    """DOWN twice ⇒ down verdict stands and the #1169 copy is produced."""
    with patch.object(
        remotes, "_check_health_once", return_value=_health("DOWN")
    ), patch("time.sleep"):
        result = remotes.check_health("letta-demo", config=_cfg(), timeout=6)
        assert result.state == "DOWN"
        text = remotes.remote_down_preflight("letta-demo", config=_cfg())
    assert text is not None and "letta-demo" in text


def test_up_never_pays_the_retry():
    """A healthy probe is single-shot — no sleep, no second probe, no latency tax."""
    with patch.object(remotes, "_check_health_once", return_value=_health("UP")) as once, patch(
        "time.sleep"
    ) as slept:
        result = remotes.check_health("letta-demo", config=_cfg(), timeout=6)
    assert result.state == "UP"
    assert once.call_count == 1
    slept.assert_not_called()


def test_degraded_and_unknown_stay_single_shot():
    """Real HTTP answers (DEGRADED) are not retried; UNKNOWN is not down."""
    for state in ("DEGRADED", "UNKNOWN"):
        with patch.object(
            remotes, "_check_health_once", return_value=_health(state)
        ) as once, patch("time.sleep") as slept:
            remotes.check_health("letta-demo", config=_cfg(), timeout=6)
        assert once.call_count == 1, state
        slept.assert_not_called(), state

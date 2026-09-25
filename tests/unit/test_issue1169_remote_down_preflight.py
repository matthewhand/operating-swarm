"""#1169 — a seat bound to a dead gateway fails fast, visibly.

The pre-flight helper (`remote_down_preflight`) is the honest one-shot health
probe the remote_harness seat runs *before* its LLM hop: when the remote is
unreachable (state DOWN), the turn can render the gateway-down copy immediately
instead of masking a 0.1s failure behind a spinner that outlives it. AUTH /
UNKNOWN must not abort — the gateway is up, and the adapter's own send path
owns those errors. A probe crash also never aborts: send proceeds as before.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from swarm.core import remotes


def _cfg():
    return {"remotes": {"letta-demo": {"kind": "letta"}}}


def test_down_gateway_produces_preflight_copy():
    health = remotes.HealthResult(
        remote="letta-demo", ok=False, state="DOWN",
        detail="connection refused", http_status=None,
    )
    with patch.object(remotes, "check_health", return_value=health):
        text = remotes.remote_down_preflight("letta-demo", config=_cfg())
    assert text is not None
    assert "letta-demo" in text
    assert "connection refused" in text
    assert "Settings" in text or "remotes" in text.lower()


def test_up_gateway_returns_none():
    health = remotes.HealthResult(
        remote="letta-demo", ok=True, state="UP", detail="fine", http_status=200,
    )
    with patch.object(remotes, "check_health", return_value=health):
        assert remotes.remote_down_preflight("letta-demo", config=_cfg()) is None


def test_unknown_and_auth_do_not_abort():
    for state in ("UNKNOWN", "AUTH"):
        health = remotes.HealthResult(
            remote="letta-demo", ok=False, state=state, detail="meh",
        )
        with patch.object(remotes, "check_health", return_value=health):
            assert remotes.remote_down_preflight("letta-demo", config=_cfg()) is None, state


def test_probe_crash_never_aborts():
    with patch.object(remotes, "check_health", side_effect=RuntimeError("boom")):
        assert remotes.remote_down_preflight("letta-demo", config=_cfg()) is None


def test_unconfigured_remote_returns_none():
    with patch.object(remotes, "check_health") as probe:
        assert remotes.remote_down_preflight("never-added", config=_cfg()) is None
        probe.assert_not_called()

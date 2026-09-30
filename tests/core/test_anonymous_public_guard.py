"""#1342: SWARM_ALLOW_ANONYMOUS / SWARM_DEMO_MODE must not open a public host.

``AllowAnonymousPreviewMiddleware`` logs in any unauthenticated caller as
``swarm-anon-preview`` when ``swarm_allow_anonymous()`` is true, and that
session satisfies ``HasValidTokenOrSession`` for the whole DRF surface
(``/v1/responses`` = LLM spend). With ``DJANGO_DEBUG=false`` the deployment is
meant to be reachable by strangers, so a truthy anon flag now has to be
accompanied by the explicit ``SWARM_ALLOW_PUBLIC_ANONYMOUS=1`` opt-in.
"""

from __future__ import annotations

import inspect

import pytest
from django.core.exceptions import ImproperlyConfigured

from swarm.apps import SwarmConfig
from swarm.middleware import (
    PUBLIC_ANONYMOUS_OPT_IN_ENV,
    anonymous_preview_forced_by_env,
    assert_public_anonymous_allowed,
    public_anonymous_opt_in,
    swarm_allow_anonymous,
)
from swarm.utils.env_utils import is_django_debug

_ANON_ENV = (
    "DJANGO_DEBUG",
    "SWARM_ALLOW_ANONYMOUS",
    "SWARM_DEMO_MODE",
    PUBLIC_ANONYMOUS_OPT_IN_ENV,
)


@pytest.fixture(autouse=True)
def _hermetic_anonymous_env(monkeypatch):
    """No ambient env: every case states the full flag set it cares about."""
    for name in _ANON_ENV:
        monkeypatch.delenv(name, raising=False)


def test_debug_false_anon_flag_raises(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")

    with pytest.raises(ImproperlyConfigured) as exc:
        assert_public_anonymous_allowed()

    message = str(exc.value)
    assert "SWARM_ALLOW_ANONYMOUS" in message
    assert "DJANGO_DEBUG" in message
    assert PUBLIC_ANONYMOUS_OPT_IN_ENV in message
    # Actionable: names the exposure, not just "bad config".
    assert "public" in message.lower()


def test_debug_false_demo_mode_raises(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")

    with pytest.raises(ImproperlyConfigured) as exc:
        assert_public_anonymous_allowed()

    message = str(exc.value)
    assert "SWARM_DEMO_MODE" in message
    assert "SWARM_ALLOW_ANONYMOUS" not in message
    assert PUBLIC_ANONYMOUS_OPT_IN_ENV in message


def test_debug_false_both_flags_names_both(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")
    monkeypatch.setenv("SWARM_DEMO_MODE", "true")

    with pytest.raises(ImproperlyConfigured) as exc:
        assert_public_anonymous_allowed()

    message = str(exc.value)
    assert "SWARM_ALLOW_ANONYMOUS" in message
    assert "SWARM_DEMO_MODE" in message


def test_debug_false_no_flags_does_not_raise(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")

    assert anonymous_preview_forced_by_env() == []
    assert public_anonymous_opt_in() is False
    assert_public_anonymous_allowed()  # must not raise


def test_public_opt_in_is_the_escape_hatch(monkeypatch):
    """Documents SWARM_ALLOW_PUBLIC_ANONYMOUS=1: deliberate opt-out, no raise."""
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")

    assert public_anonymous_opt_in() is False
    with pytest.raises(ImproperlyConfigured):
        assert_public_anonymous_allowed()

    monkeypatch.setenv(PUBLIC_ANONYMOUS_OPT_IN_ENV, "1")
    assert public_anonymous_opt_in() is True
    assert_public_anonymous_allowed()  # must not raise


def test_public_opt_in_also_covers_demo_mode(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    monkeypatch.setenv(PUBLIC_ANONYMOUS_OPT_IN_ENV, "1")

    assert_public_anonymous_allowed()  # must not raise


def test_debug_true_anon_flag_does_not_raise(monkeypatch):
    """The dev/demo path must keep working unchanged."""
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")

    assert is_django_debug() is True
    assert_public_anonymous_allowed()  # must not raise


def test_debug_true_demo_mode_does_not_raise(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")

    assert_public_anonymous_allowed()  # must not raise


def test_anon_flag_explicitly_off_is_not_an_offender(monkeypatch):
    """SWARM_ALLOW_ANONYMOUS=0 forces anonymous off, so it cannot open a host."""
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "0")

    assert anonymous_preview_forced_by_env() == []
    assert_public_anonymous_allowed()  # must not raise
    assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=False) is False


def test_falsy_values_of_anon_flag_do_not_open_the_host(monkeypatch):
    for value in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("DJANGO_DEBUG", "false")
        monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", value)
        monkeypatch.delenv(PUBLIC_ANONYMOUS_OPT_IN_ENV, raising=False)
        assert anonymous_preview_forced_by_env() == [], value
        assert_public_anonymous_allowed()  # must not raise


def test_forced_by_env_reports_flag_names(monkeypatch):
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")
    assert anonymous_preview_forced_by_env() == ["SWARM_ALLOW_ANONYMOUS"]

    monkeypatch.delenv("SWARM_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    assert anonymous_preview_forced_by_env() == ["SWARM_DEMO_MODE"]

    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")
    assert anonymous_preview_forced_by_env() == ["SWARM_ALLOW_ANONYMOUS", "SWARM_DEMO_MODE"]


# ---------------------------------------------------------------------------
# What the guard is protecting: the flag really does hand out a session on a
# public host (DEBUG=false). Without this the guard would be guarding nothing.
# ---------------------------------------------------------------------------


def test_flag_really_would_open_a_public_host(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")
    monkeypatch.delenv("SWARM_DEMO_MODE", raising=False)
    assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=False) is True

    monkeypatch.delenv("SWARM_ALLOW_ANONYMOUS", raising=False)
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")
    assert swarm_allow_anonymous("8.8.8.8", debug=False, testing=False) is True


# ---------------------------------------------------------------------------
# Real guard path: the exact code SwarmConfig.ready() runs at boot.
# ---------------------------------------------------------------------------


def test_appconfig_check_raises_on_public_anonymous(monkeypatch):
    """SwarmConfig._check_public_anonymous() is the ready() guard; it re-raises."""
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_DEMO_MODE", "1")

    with pytest.raises(ImproperlyConfigured, match="SWARM_DEMO_MODE"):
        SwarmConfig._check_public_anonymous()


def test_appconfig_check_passes_with_opt_in(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "false")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")
    monkeypatch.setenv(PUBLIC_ANONYMOUS_OPT_IN_ENV, "1")

    SwarmConfig._check_public_anonymous()  # must not raise


def test_appconfig_check_passes_in_debug(monkeypatch):
    monkeypatch.setenv("DJANGO_DEBUG", "true")
    monkeypatch.setenv("SWARM_ALLOW_ANONYMOUS", "1")

    SwarmConfig._check_public_anonymous()  # must not raise


def test_appconfig_check_never_swallows_unexpected_errors(monkeypatch):
    """A surprise in flag parsing is logged, not raised — and not swallowed silently."""
    monkeypatch.setattr(
        "swarm.middleware.anonymous_preview_forced_by_env",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    SwarmConfig._check_public_anonymous()  # must not raise


def test_ready_runs_the_public_anonymous_guard():
    """Wiring: ready() must call the guard, next to the SWARM_TEST_MODE one."""
    source = inspect.getsource(SwarmConfig.ready)
    assert "_check_public_anonymous()" in source
    assert source.index("assert_test_mode_allowed()") < source.index(
        "_check_public_anonymous()"
    )


def test_guard_is_named_consistently_with_existing_flags():
    """Greppable + consistent with SWARM_ALLOW_NO_AUTH / SWARM_ALLOW_ANONYMOUS."""
    assert PUBLIC_ANONYMOUS_OPT_IN_ENV == "SWARM_ALLOW_PUBLIC_ANONYMOUS"
    assert PUBLIC_ANONYMOUS_OPT_IN_ENV.startswith("SWARM_ALLOW_")

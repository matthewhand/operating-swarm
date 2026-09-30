"""Startup footgun: warn when serving with API auth off."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


@pytest.mark.django_db
@pytest.mark.parametrize(
    "argv",
    [
        ["uvicorn", "swarm.asgi:application"],
        ["os-api", "--port", "8000"],
        ["/home/user/.local/bin/os-api", "--host", "0.0.0.0"],
        ["swarm-api"],
    ],
    ids=["uvicorn", "os-api", "os-api-console-path", "swarm-api"],
)
def test_warns_when_serving_without_api_auth(settings, monkeypatch, argv):
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = False
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    monkeypatch.delenv("SWARM_PROCESS_ROLE", raising=False)
    monkeypatch.setattr(sys, "argv", argv)
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_called_once()
    assert "API authentication is OFF" in warn.call_args[0][0]


@pytest.mark.django_db
def test_no_warn_when_api_auth_on(settings, monkeypatch):
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = True
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    monkeypatch.delenv("SWARM_PROCESS_ROLE", raising=False)
    monkeypatch.setattr(sys, "argv", ["uvicorn", "swarm.asgi:application"])
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_not_called()


def test_no_warn_when_not_serving(settings, monkeypatch):
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = False
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    monkeypatch.setattr(sys, "argv", ["pytest"])
    monkeypatch.delenv("SWARM_PROCESS_ROLE", raising=False)
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_not_called()


def test_spawn_worker_warns_only_with_process_role(settings, monkeypatch):
    """Dockerfile exports SWARM_PROCESS_ROLE because spawn rewrites argv."""
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = False
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    monkeypatch.delenv("SWARM_PROCESS_ROLE", raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["/usr/bin/python", "-c", "from multiprocessing.spawn import spawn_main"],
    )
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_not_called()

    monkeypatch.setenv("SWARM_PROCESS_ROLE", "serve")
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_called_once()

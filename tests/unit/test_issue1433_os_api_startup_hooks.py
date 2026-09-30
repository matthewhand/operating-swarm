"""#1433 — os-api declares serving before ASGI boot.

``swarm.core.swarm_api.main`` calls ``serving_process.mark_serving()``
(``SWARM_PROCESS_ROLE=serve``) before uvicorn. ``SwarmConfig.ready`` uses that
module for the auth warning, worker check, async resume, and schedule engine.
Basename matching still covers ``os-api`` / ``gunicorn`` / ``daphne`` /
plain uvicorn. The role env covers spawned workers that rewrite argv.
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import threading

import pytest

from swarm.apps import SwarmConfig
from swarm.core.serving_process import SERVE_ROLE_ENV, detect_process_role, mark_serving


def _no_serving_env(monkeypatch) -> None:
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    monkeypatch.delenv(SERVE_ROLE_ENV, raising=False)
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.delenv("SWARM_DISABLE_SCHEDULE_ENGINE", raising=False)
    monkeypatch.delenv("SWARM_UVICORN_WORKERS", raising=False)
    monkeypatch.delenv("RUN_MAIN", raising=False)


@contextlib.contextmanager
def _grab_hook_logs():
    """Collect startup lines from the logger itself.

    Django's config writes ``swarm.apps`` to a stderr handler that pytest's
    caplog and capfd do not see.
    """
    found: list[str] = []

    class _Grab(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            message = record.getMessage()
            if message.startswith("Startup hooks started:"):
                found.append(message)

    handler = _Grab()
    logger = logging.getLogger("swarm.apps")
    level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield found
    finally:
        logger.removeHandler(handler)
        logger.setLevel(level)


def _patch_hooks(monkeypatch):
    scheduled: list[bool] = []
    resumed: list[dict] = []

    import swarm.core.schedule_engine as schedule_engine

    monkeypatch.setattr(
        schedule_engine, "start_loop", lambda: scheduled.append(True) or True
    )

    class FakeThread:
        def __init__(self, target=None, daemon=False):
            self.target = target
            self.daemon = daemon

        def start(self):
            resumed.append({"daemon": self.daemon, "started": True})

    monkeypatch.setattr(threading, "Thread", FakeThread)
    return scheduled, resumed


def test_os_api_main_registers_serving_hooks(monkeypatch):
    """os-api main, with the server run mocked, registers serving hooks."""
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["pytest", "tests/unit"])
    scheduled, resumed = _patch_hooks(monkeypatch)

    import uvicorn

    booted: dict[str, str | None] = {}

    def fake_run(*_args, **_kwargs):
        booted[SERVE_ROLE_ENV] = os.environ.get(SERVE_ROLE_ENV)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    # main() assigns the role directly. Snapshot first so teardown does not
    # leak "serve" into later tests.
    monkeypatch.setenv(SERVE_ROLE_ENV, os.environ.get(SERVE_ROLE_ENV, ""))

    from swarm.core.swarm_api import main

    with _grab_hook_logs() as hook_logs:
        main(["--host", "127.0.0.1", "--port", "0"])

    assert booted[SERVE_ROLE_ENV] == "serve"
    assert scheduled == [True]
    assert resumed == [{"daemon": True, "started": True}]
    assert len(hook_logs) == 1
    started = hook_logs[0].split("; skipped:")[0]
    assert "async_resume" in started
    assert "schedule_engine" in started
    assert hook_logs[0].endswith("why: SWARM_PROCESS_ROLE set by launcher")


@pytest.mark.parametrize("command", ["migrate", "shell"])
def test_management_commands_do_not_start_hooks(monkeypatch, command):
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["manage.py", command])
    scheduled, resumed = _patch_hooks(monkeypatch)

    with _grab_hook_logs() as hook_logs:
        SwarmConfig._start_serving_hooks()

    assert scheduled == []
    assert resumed == []
    assert os.environ.get(SERVE_ROLE_ENV) in (None, "")
    assert len(hook_logs) == 1
    assert hook_logs[0].startswith("Startup hooks started: none;")
    assert f"management command {command}" in hook_logs[0]


def test_os_api_argv_starts_hooks_without_process_role(monkeypatch):
    """The console-script basename is a server even when no role env is set."""
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["/home/user/.local/bin/os-api", "--port", "8000"])
    scheduled, _resumed = _patch_hooks(monkeypatch)

    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]
    assert "os-api" in detect_process_role().reason


def test_mark_serving_starts_hooks_when_argv_is_a_spawn_worker(monkeypatch):
    """Spawned workers rewrite argv. The role env is what starts hooks."""
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["/usr/bin/python", "-c", "from multiprocessing.spawn import spawn_main"],
    )
    scheduled, _resumed = _patch_hooks(monkeypatch)

    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == []

    monkeypatch.setenv(SERVE_ROLE_ENV, "")
    mark_serving()
    assert os.environ[SERVE_ROLE_ENV] == "serve"
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]
    assert detect_process_role().reason == "SWARM_PROCESS_ROLE set by launcher"


@pytest.mark.parametrize(
    "argv",
    [
        ["gunicorn", "swarm.asgi:application"],
        ["daphne", "-b", "0.0.0.0", "-p", "8000", "swarm.asgi:application"],
    ],
)
def test_gunicorn_and_daphne_argv_start_schedule(monkeypatch, argv):
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", argv)
    scheduled, _resumed = _patch_hooks(monkeypatch)
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]


def test_plain_uvicorn_argv_fallback_starts_schedule(monkeypatch):
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(
        sys,
        "argv",
        ["/usr/local/bin/uvicorn", "swarm.asgi:application", "--host", "0.0.0.0"],
    )
    scheduled, _resumed = _patch_hooks(monkeypatch)
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]
    role = detect_process_role()
    assert role.serving is True
    assert "uvicorn swarm.asgi:application" in role.reason


def test_uvicorn_basename_counts_even_for_help(monkeypatch):
    """Basename matching treats ``uvicorn`` as a server, including ``--help``.

    A path that merely contains the word uvicorn does not. That case is
    pinned in test_serving_process_1444.
    """
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["uvicorn", "--help"])
    scheduled, _resumed = _patch_hooks(monkeypatch)
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]
    assert detect_process_role().reason == "argv: uvicorn"


def test_pytest_does_not_start_hooks(monkeypatch):
    _no_serving_env(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["pytest", "tests/unit"])
    scheduled, resumed = _patch_hooks(monkeypatch)
    SwarmConfig._maybe_resume_async_tasks()
    SwarmConfig._maybe_start_schedule_engine()
    SwarmConfig._check_uvicorn_workers()
    assert scheduled == []
    assert resumed == []


def test_process_role_does_not_start_runserver_parent(monkeypatch):
    _no_serving_env(monkeypatch)
    monkeypatch.setenv(SERVE_ROLE_ENV, "serve")
    monkeypatch.setattr(sys, "argv", ["manage.py", "runserver", "8000"])
    scheduled, _resumed = _patch_hooks(monkeypatch)
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == []
    assert detect_process_role().reason == "runserver autoreload parent"


def test_worker_contract_failure_is_logged_then_raised(monkeypatch):
    _no_serving_env(monkeypatch)
    monkeypatch.setenv("SWARM_UVICORN_WORKERS", "4")
    monkeypatch.setenv("SWARM_ENFORCE_SINGLE_WORKER", "true")
    monkeypatch.setattr(sys, "argv", ["uvicorn", "swarm.asgi:application"])
    with _grab_hook_logs() as hook_logs, pytest.raises(ValueError):
        SwarmConfig._start_serving_hooks()
    assert len(hook_logs) == 1
    assert "uvicorn_workers (failed:" in hook_logs[0]
    assert "async_resume" in hook_logs[0]
    assert "schedule_engine" in hook_logs[0]


def test_runserver_parent_skips_engine_child_starts(monkeypatch):
    _no_serving_env(monkeypatch)
    scheduled, _resumed = _patch_hooks(monkeypatch)

    monkeypatch.setattr(sys, "argv", ["manage.py", "runserver", "8000"])
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == []

    monkeypatch.setenv("RUN_MAIN", "true")
    SwarmConfig._maybe_start_schedule_engine()
    assert scheduled == [True]


def test_serving_tokens_include_os_api_and_legacy_swarm_api(monkeypatch):
    """Basename detection stays available for processes that set neither flag."""
    monkeypatch.delenv(SERVE_ROLE_ENV, raising=False)
    monkeypatch.delenv("SWARM_SERVING", raising=False)
    from swarm.core.serving_process import (
        _ASGI_BASENAMES,
        is_asgi_server_process,
        is_serving_process,
    )

    os_api = ["/home/user/.local/bin/os-api", "--port", "8000"]
    swarm_api = ["/home/user/.local/bin/swarm-api", "--port", "8000"]
    pytest_argv = ["pytest", "tests/unit"]
    assert "os-api" in _ASGI_BASENAMES
    assert "swarm-api" in _ASGI_BASENAMES
    assert is_asgi_server_process(os_api)
    assert is_serving_process(os_api)
    assert is_asgi_server_process(swarm_api)
    assert not is_serving_process(pytest_argv)

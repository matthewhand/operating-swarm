"""#1444 — serving-process detection must follow the os-api entry point.

The old ``apps.py`` check joined ``sys.argv`` and substring-matched
``swarm-api`` / ``uvicorn`` / ``daphne``. ``os-api`` never contains those
words (uvicorn.run stays in-process), so auth warnings, async resume, and
the schedule engine never started. The same substring match treated a
migrate path like ``/var/log/uvicorn/error.log`` as a server.

The heuristic itself is tracked in #1433; this pins the behavior #1444
depends on.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from swarm.core.serving_process import (
    SERVE_ROLE_ENV,
    detect_process_role,
    is_asgi_server_process,
    is_serving_process,
    server_side_effects_enabled,
)

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _clear_serve_role(monkeypatch):
    monkeypatch.delenv(SERVE_ROLE_ENV, raising=False)
    monkeypatch.delenv("RUN_MAIN", raising=False)
    monkeypatch.delenv("SWARM_TEST_MODE", raising=False)
    monkeypatch.delenv("SWARM_DISABLE_SCHEDULE_ENGINE", raising=False)


def test_os_api_basename_is_an_asgi_server():
    argv = ["/usr/local/bin/os-api", "--host", "0.0.0.0", "--port", "8000"]
    assert is_asgi_server_process(argv)
    assert is_serving_process(argv)
    assert server_side_effects_enabled(argv)


def test_os_api_exe_basename_is_an_asgi_server():
    argv = [r"C:\Program Files\OperatingSwarm\os-api.exe"]
    assert is_asgi_server_process(argv)


def test_legacy_swarm_api_and_module_invocation_still_count():
    assert is_asgi_server_process(["/usr/bin/swarm-api"])
    assert is_asgi_server_process(["/usr/bin/python", "-m", "swarm.core.swarm_api"])
    assert is_asgi_server_process(
        ["/usr/bin/python", "/opt/os/src/swarm/core/swarm_api.py"]
    )


def test_uvicorn_token_and_basename_count():
    assert is_asgi_server_process(
        ["uvicorn", "swarm.asgi:application", "--port", "8000"]
    )
    assert is_asgi_server_process(
        ["/usr/bin/python", "-m", "uvicorn", "swarm.asgi:application"]
    )


def test_path_that_merely_contains_uvicorn_is_not_a_server():
    argv = [
        "/usr/bin/python",
        "manage.py",
        "migrate",
        "/var/log/uvicorn/error.log",
    ]
    assert not is_asgi_server_process(argv)
    assert not is_serving_process(argv)
    assert not server_side_effects_enabled(argv)


def test_argument_whose_basename_is_a_serving_token_is_not_a_server():
    """A path or flag that ends in a token is still an argument.

    Taking the basename of every argv element treated ``pytest /opt/os-api``,
    ``pytest os-api``, and ``migrate /var/log/uvicorn`` as servers (#1433).
    """
    cases = [
        ["pytest", "/opt/os-api"],
        ["pytest", "os-api"],
        ["/opt/os-api/.venv/bin/pytest", "os-api"],
        ["manage.py", "migrate", "/var/log/uvicorn"],
        ["manage.py", "migrate", "--log=/var/log/uvicorn"],
        ["manage.py", "migrate", "/var/log/runserver"],
        ["manage.py", "migrate", "/tmp/swarm_api.py"],
        [
            "python",
            "manage.py",
            "migrate",
            "/opt/os/src/swarm/core/swarm_api.py",
        ],
    ]
    for argv in cases:
        assert not is_asgi_server_process(argv), argv
        assert not is_serving_process(argv), argv
        assert not server_side_effects_enabled(argv), argv


def test_env_and_python_module_invocations_still_count():
    assert is_asgi_server_process(["/usr/bin/env", "os-api", "--port", "8000"])
    assert is_serving_process(
        ["/usr/bin/python3.12", "-m", "gunicorn", "swarm.asgi:application"]
    )


def test_daphne_substring_inside_another_path_is_not_a_server():
    argv = ["manage.py", "shell", "/opt/daphne-notes/readme.txt"]
    assert not is_serving_process(argv)


def test_explicit_serve_role_counts_even_when_argv_is_a_worker_bootstrap():
    argv = ["/usr/bin/python", "-c", "from multiprocessing.spawn import spawn_main"]
    assert not is_asgi_server_process(argv)
    with patch.dict("os.environ", {SERVE_ROLE_ENV: "serve"}):
        assert is_asgi_server_process(argv)
        assert server_side_effects_enabled(argv)


def test_runserver_parent_warns_but_does_not_start_side_effects():
    argv = ["manage.py", "runserver", "0.0.0.0:8000"]
    assert is_serving_process(argv)
    assert not is_asgi_server_process(argv)
    assert not server_side_effects_enabled(argv)


def test_runserver_child_and_noreload_start_side_effects():
    argv = ["manage.py", "runserver"]
    with patch.dict("os.environ", {"RUN_MAIN": "true"}):
        assert server_side_effects_enabled(argv)
    assert server_side_effects_enabled(["manage.py", "runserver", "--noreload"])


def test_serve_role_does_not_override_runserver_reloader_parent():
    argv = ["manage.py", "runserver"]
    with patch.dict("os.environ", {SERVE_ROLE_ENV: "serve"}):
        assert is_serving_process(argv)
        assert not is_asgi_server_process(argv)
        assert not server_side_effects_enabled(argv)


@pytest.mark.parametrize(
    "argv",
    [
        ["uvicorn", "swarm.asgi:application"],
        ["/usr/local/bin/uvicorn", "swarm.asgi:application", "--host", "0.0.0.0"],
        ["uvicorn", "--help"],
        ["/usr/local/bin/os-api", "--host", "0.0.0.0", "--port", "8000"],
        ["swarm-api"],
        ["gunicorn", "swarm.asgi:application"],
        ["daphne", "-b", "0.0.0.0", "-p", "8000", "swarm.asgi:application"],
        ["/usr/bin/env", "os-api", "--port", "8000"],
        ["/usr/bin/python", "-m", "swarm.core.swarm_api"],
        ["/usr/bin/python", "/opt/os/src/swarm/core/swarm_api.py"],
    ],
)
def test_reason_names_the_server_for_every_serving_shape(argv):
    """``detect_process_role`` phrases a reason for any argv it calls serving.

    The reason is what the ``Startup hooks started: ...; why:`` line carries,
    so a shape with no phrasing is an operator debugging a blank line. Every
    branch of the phraser's name set is covered here: the program basename on
    its own, ``env <server>``, and the two ``swarm_api`` invocation forms.
    """
    role = detect_process_role(argv)
    assert role.serving is True
    assert role.reason.startswith("argv"), role.reason
    assert role.reason != "argv: asgi server", role.reason


def test_reason_prefers_the_program_over_a_uvicorn_named_path_argument():
    """A ``--log-config`` path naming uvicorn is an argument, not the server."""
    argv = ["os-api", "--log-config", "/etc/uvicorn/conf.ini"]
    assert is_asgi_server_process(argv)
    assert detect_process_role(argv).reason == "argv: os-api"


@pytest.mark.django_db
def test_auth_warning_fires_for_os_api(settings, monkeypatch):
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = False
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/os-api"])
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_called_once()
    assert "API authentication is OFF" in warn.call_args[0][0]


@pytest.mark.django_db
def test_auth_warning_skips_uvicorn_substring_in_a_path(settings, monkeypatch):
    from swarm import apps as apps_mod
    from swarm.apps import SwarmConfig

    settings.ENABLE_API_AUTH = False
    monkeypatch.setattr(
        sys,
        "argv",
        ["manage.py", "migrate", "/var/log/uvicorn/error.log"],
    )
    with patch.object(apps_mod.logger, "warning") as warn:
        SwarmConfig._warn_if_api_auth_disabled()
    warn.assert_not_called()


def test_schedule_engine_starts_for_os_api(monkeypatch):
    from swarm.apps import SwarmConfig

    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/os-api"])
    with patch("swarm.core.schedule_engine.start_loop") as start:
        SwarmConfig._maybe_start_schedule_engine()
    start.assert_called_once()


def test_schedule_engine_skips_migrate_path_containing_uvicorn(monkeypatch):
    from swarm.apps import SwarmConfig

    monkeypatch.setattr(
        sys,
        "argv",
        ["manage.py", "migrate", "/var/log/uvicorn/error.log"],
    )
    with patch("swarm.core.schedule_engine.start_loop") as start:
        SwarmConfig._maybe_start_schedule_engine()
    start.assert_not_called()


def test_schedule_engine_skips_checkout_directory_named_os_api(monkeypatch):
    from swarm.apps import SwarmConfig

    monkeypatch.setattr(sys, "argv", ["pytest", "os-api"])
    with patch("swarm.core.schedule_engine.start_loop") as start:
        SwarmConfig._maybe_start_schedule_engine()
    start.assert_not_called()


def test_resume_starts_for_os_api(monkeypatch):
    from swarm.apps import SwarmConfig

    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/os-api"])
    with (
        patch("swarm.views.responses_views.resume_pending_responses") as resume,
        patch("threading.Thread") as thread,
    ):
        SwarmConfig._maybe_resume_async_tasks()
    thread.assert_called_once()
    assert thread.call_args.kwargs["target"] is resume
    assert thread.call_args.kwargs["daemon"] is True


def test_dockerfile_exports_serve_role_after_migrate():
    text = (REPO / "Dockerfile").read_text(encoding="utf-8")
    export_at = text.find("export SWARM_PROCESS_ROLE=serve")
    exec_at = text.find("exec uvicorn swarm.asgi:application")
    migrate_at = text.rfind("manage.py migrate", 0, exec_at)
    assert migrate_at != -1
    assert migrate_at < export_at < exec_at


def test_dev_compose_exports_serve_role_after_migrate():
    text = (REPO / "docker-compose.dev.yml").read_text(encoding="utf-8")
    export_at = text.find("export SWARM_PROCESS_ROLE=serve")
    exec_at = text.find("exec uvicorn swarm.asgi:application")
    migrate_at = text.rfind("manage.py migrate", 0, exec_at)
    assert migrate_at != -1
    assert migrate_at < export_at < exec_at

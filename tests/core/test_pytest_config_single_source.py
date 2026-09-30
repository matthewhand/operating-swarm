"""D-07: exactly one pytest config source, and it is the one actually applied.

Regression cover for a defect where ``pyproject.toml`` carried a
``[tool.pytest.ini_options]`` block that pytest *silently ignored*, because
``pytest.ini`` at the repo root takes precedence. Every run printed::

    configfile: pytest.ini (WARNING: ignoring pytest config in pyproject.toml!)

and every key in the dead block was inert, including two that guard the run
against real operator credentials:

* ``SWARM_SKIP_DOTENV`` -- without it ``settings.py`` loads the developer's
  actual ``~/.config/swarm/.env`` at import time, before any fixture can
  redirect ``HOME``. ~137 tests then 403 and the suite executes against live
  credentials (#1335). This survived only because ``tests/conftest.py`` also
  sets it, which is exactly the sort of accidental redundancy that hides the
  next outage.
* ``DJANGO_ALLOW_ASYNC_UNSAFE`` -- set nowhere else, so it was simply absent
  from every bare ``uv run pytest``.

These assertions read the *resolved* config out of the running pytest
(``request.config``) and the live process environment, not file text. A grep
for a substring in a config file is precisely the defect class that let this
ship: it would have passed against the dead pyproject block all the same.
"""

from __future__ import annotations

import configparser
import importlib.util
import os
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Filenames pytest consults, in the precedence order pytest itself uses.
#: The first hit in a directory wins outright -- it does not merge.
CANDIDATE_CONFIG_FILES = ("pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")


def _declares_pytest_config(path: Path) -> bool:
    """True if `path` is a config file that pytest would read settings from."""
    if path.name == "pytest.ini":
        return path.is_file()
    if path.name == "pyproject.toml":
        if not path.is_file():
            return False
        return "pytest" in tomllib.loads(path.read_text(encoding="utf-8")).get("tool", {})
    if not path.is_file():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
    except configparser.Error:
        return False
    return parser.has_section("pytest") or parser.has_section("tool:pytest")


def _declaring_sources() -> list[str]:
    return [name for name in CANDIDATE_CONFIG_FILES if _declares_pytest_config(REPO_ROOT / name)]


def test_only_one_pytest_config_source_exists() -> None:
    """Two sources means one is dead, and the dead one is silent about it."""
    assert _declaring_sources() == ["pytest.ini"], (
        "pytest reads the FIRST config file it finds per directory and does not "
        "merge, so a second source is not 'belt and braces' -- it is dead "
        "config. Found: " + ", ".join(_declaring_sources())
    )


def test_pytest_reports_pytest_ini_as_the_configfile_in_use(request: pytest.FixtureRequest) -> None:
    """The live file is the one we keep editing, proven by pytest itself."""
    assert request.config.inipath is not None, "pytest resolved no inifile at all"
    assert request.config.inipath.name == "pytest.ini", (
        f"pytest is applying {request.config.inipath.name}, not pytest.ini. "
        "Anything added to pytest.ini is inert until this is reconciled."
    )


def test_hang_guard_is_active(request: pytest.FixtureRequest) -> None:
    """A global per-test ceiling exists, and the plugin that enforces it loaded.

    ``timeout`` was registered in ``markers`` while the ini key was commented
    out, so a missing pytest-timeout would have made every
    ``@pytest.mark.timeout(N)`` a silent no-op rather than a loud error.
    """
    assert importlib.util.find_spec("pytest_timeout") is not None, (
        "pytest-timeout is not installed, so the `timeout` marker registered in "
        "markers is a silent no-op and the global guard below does nothing."
    )
    timeout = request.config.getini("timeout")
    # getini hands back the raw ini token (a string like "600"); pytest-timeout
    # is what coerces and displays it as "600.0s". Coerce the same way, and fail
    # loudly on junk rather than letting a typo read as "no guard".
    assert timeout not in (None, "", 0, "0"), (
        f"no global per-test hang guard is configured (timeout={timeout!r}). "
        "Without it a hung test hangs CI indefinitely: only one workflow job "
        "passed --timeout=180."
    )
    try:
        effective = float(timeout)
    except (TypeError, ValueError):
        pytest.fail(f"timeout={timeout!r} is not a number, so the guard is inert")
    # A hang guard must be far above any legitimate test. The full suite runs in
    # well under 600s TOTAL, so a small ceiling here would be a perf budget in
    # disguise and would start failing slow-but-correct tests.
    assert effective >= 300, f"timeout={effective} is too tight to be a hang guard"


def test_operator_dotenv_is_never_loaded_into_the_test_run() -> None:
    """The #1335 credential guard is in effect in this very process."""
    assert os.environ.get("SWARM_SKIP_DOTENV", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ), (
        "SWARM_SKIP_DOTENV is not set, so settings.py may have loaded the "
        "operator's real ~/.config/swarm/.env (API_AUTH_TOKEN, DATABASE_URL) "
        "into this run."
    )


def test_async_unsafe_guard_is_applied() -> None:
    """Was set ONLY in the dead pyproject block, so it was absent from every run."""
    assert os.environ.get("DJANGO_ALLOW_ASYNC_UNSAFE", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ), "DJANGO_ALLOW_ASYNC_UNSAFE is not set for this run"


def test_django_settings_module_is_resolved(request: pytest.FixtureRequest) -> None:
    """Guards against a 'cleanup' that drops the settings pointer with the block."""
    assert request.config.getini("DJANGO_SETTINGS_MODULE") == "swarm.settings"


def test_fixture_mark_warning_filter_is_applied(request: pytest.FixtureRequest) -> None:
    """Also only in the dead block; pytest 9 emits this as PytestRemovedIn9Warning."""
    filters = request.config.getini("filterwarnings")
    assert any("Marks applied to fixtures have no effect" in f for f in filters), (
        "the pytest-9 fixture-mark filter is missing, so every run emits a "
        "removal warning that trains everyone to ignore warnings"
    )

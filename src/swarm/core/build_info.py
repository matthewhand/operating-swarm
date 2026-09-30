"""Runtime install-profile reporting.

The base install is deliberately barebones: most heavyweight integrations live
behind extras in ``pyproject.toml`` (``pip install '.[oauth]'`` and friends).
Extras are invisible at runtime, though — nothing records which profile a
process actually booted with. That turns a missing optional dependency into a
mystery ``ImportError`` deep in a request path.

This module answers the question instead. It probes for the marker module each
extra provides and reports which profiles are live, so a boot log or a
``/v1/system/build/`` response can be read without guessing.

Keep :data:`EXTRA_MARKERS` in step with ``[project.optional-dependencies]`` in
``pyproject.toml``. The probe uses :func:`importlib.util.find_spec` rather than
a real import, so reporting never executes (or pays the import cost of) the
thing it is reporting on.
"""

from __future__ import annotations

import sys
from importlib import metadata
from importlib.util import find_spec

DISTRIBUTION_NAME = "os-core"

#: extra name -> module that proves the extra was installed.
EXTRA_MARKERS: dict[str, str] = {
    "google": "googleapiclient",
    "vector": "qdrant_client",
    "tasks": "celery",
    "wsgi": "gunicorn",
    "scraping": "bs4",
    "build": "PyInstaller",
    "e2e": "playwright",
    "oauth": "social_django",
    "tui": "textual",
    "sandbox": "daytona",
    "desktop": "webview",
    "memory": "mem0",
    "test": "pytest",
}

#: Startup requirements that are NOT optional. Tracked so a stripped install
#: can tell "wrong profile" apart from "broken image".
#:
#: Include anything whose absence breaks the boot or the *first request*:
#: whitenoise is a MIDDLEWARE entry, so a missing wheel does not fail
#: apps.populate() -- it 500s every request with no missing_required warning,
#: which is exactly the mystery ImportError this module exists to eliminate.
#: NOTE one-directional: find_spec only proves a distribution provides the
#: name, not that importing it works (psycopg2 can find_spec fine with a
#: missing libpq.so.5). psycopg2 is a config-dependent requirement -- it is
#: only imported on the Postgres path (core/database_config.py).
REQUIRED_MODULES: dict[str, str] = {
    "channels": "channels",  # websocket + ASGI routing (swarm.asgi)
    "daphne": "daphne",  # listed in INSTALLED_APPS for ASGI-aware runserver
    "agents": "agents",  # swarm.core.blueprint_base imports it at module scope
    "openai": "openai",
    "psycopg2": "psycopg2",
    "whitenoise": "whitenoise",  # MIDDLEWARE; fails per-request, not at boot
    "rest_framework": "rest_framework",  # INSTALLED_APPS
    "drf_spectacular": "drf_spectacular",  # INSTALLED_APPS
}


def _module_available(module: str) -> bool:
    """True if ``module`` is importable, without importing it."""
    try:
        spec = find_spec(module)
    except Exception:
        # ValueError: in sys.modules with __spec__ is None (test stubs).
        # ImportError: a parent package of a dotted name is missing.
        # Anything else is a third-party sys.meta_path finder misbehaving
        # (APM agents, coverage plugins). Broad on purpose: this is diagnostic
        # code called from an unwrapped API view, so it must never be the
        # thing that raises.
        return False
    # A namespace package (directory with no __init__.py) yields a truthy spec
    # with loader=None, which would report an extra as installed when it is
    # really just a stray directory on sys.path.
    if spec is None:
        return False
    return getattr(spec, "loader", None) is not None or spec.submodule_search_locations is None


def installed_extras() -> list[str]:
    """Sorted names of the extras whose marker module is present."""
    return sorted(name for name, module in EXTRA_MARKERS.items() if _module_available(module))


def missing_required() -> list[str]:
    """Sorted names of required modules that are absent.

    Should always be empty on a working install. A non-empty result means the
    image was built against a dependency set that does not match this code --
    for example ``pip install .`` after a dependency moved to an extra.
    """
    return sorted(name for name, module in REQUIRED_MODULES.items() if not _module_available(module))


def distribution_version() -> str | None:
    """Installed ``os-core`` version, or None when running from a source tree."""
    try:
        return metadata.version(DISTRIBUTION_NAME)
    except metadata.PackageNotFoundError:
        return None


def build_profile() -> dict:
    """Machine-readable snapshot of the running install profile."""
    return {
        "distribution": DISTRIBUTION_NAME,
        "version": distribution_version(),
        "python": ".".join(str(part) for part in sys.version_info[:3]),
        "extras": installed_extras(),
        "missing_required": missing_required(),
    }


def summary_line() -> str:
    """One-line human summary, suitable for a boot log."""
    version = distribution_version() or "source"
    extras = installed_extras()
    profile = f"{DISTRIBUTION_NAME} {version} (core only)" if not extras else f"{DISTRIBUTION_NAME} {version} +{'+'.join(extras)}"
    missing = missing_required()
    if missing:
        profile += f" [MISSING REQUIRED: {', '.join(missing)}]"
    return profile

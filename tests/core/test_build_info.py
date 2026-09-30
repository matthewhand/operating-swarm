"""Install-profile reporting (swarm.core.build_info) and the build endpoint.

The barebones/extras split is only safe if a process can report which profile it
booted with, so these cover the probe, the "missing required" alarm, and the
read-only endpoint that surfaces it.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from unittest.mock import patch

import pytest

from django.contrib.auth import get_user_model

from swarm.core import build_info

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Extras that intentionally have no marker module: pure metapackages, or
#: dev/tooling groups that are not install-time features.
UNMARKED_BY_DESIGN = {"deploy", "dev", "docs"}


def _declared_extras() -> set[str]:
    return set(tomllib.loads(PYPROJECT.read_text())["project"]["optional-dependencies"])


def test_every_declared_extra_has_a_marker():
    """An extra with no marker reports "not installed" forever.

    Reads pyproject.toml, so adding an extra without a probe fails here --
    a hardcoded name list could never catch that, which was the whole point.
    """
    declared = _declared_extras()
    assert declared, "could not read extras from pyproject.toml"
    missing = declared - UNMARKED_BY_DESIGN - set(build_info.EXTRA_MARKERS)
    assert not missing, f"extras with no EXTRA_MARKERS entry: {sorted(missing)}"


def test_no_orphaned_markers():
    """A marker with no matching extra is dead weight / a typo."""
    declared = _declared_extras()
    orphans = set(build_info.EXTRA_MARKERS) - declared
    assert not orphans, f"EXTRA_MARKERS entries with no extra: {sorted(orphans)}"


def test_required_modules_are_base_dependencies():
    """REQUIRED_MODULES must name packages in the BASE dependency list.

    This is the assertion that survives `uv sync --all-extras`, where a module
    wrongly moved to an extra is still installed. Asserting the live env
    satisfies the list cannot catch that: the list is what is being checked.
    """
    base = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    base_names = {
        re.split(r"[<>=!~\[; ]", spec, maxsplit=1)[0].strip().lower()
        for spec in base
    }
    # Only the import-name -> distribution-name renames. Module names are
    # underscored; PyPI dists are not (drf-spectacular, openai-agents...).
    dist_of = {
        "agents": "openai-agents",
        "psycopg2": "psycopg2-binary",
        "rest_framework": "djangorestframework",
        "drf_spectacular": "drf-spectacular",
    }
    # Iterate the REAL mapping. Iterating a hardcoded copy let a newly added
    # entry (or a bogus one pointing at an extra-only dist) escape entirely.
    for module in build_info.REQUIRED_MODULES:
        dist = dist_of.get(module, module)
        assert dist in base_names, (
            f"{module} is REQUIRED but its dist {dist!r} is not a base "
            f"dependency -- CI installs --all-extras, so only this assertion "
            f"catches a startup module having been moved to an extra"
        )


def test_container_profile_reports_its_component_extras():
    """`deploy` is a pure alias, so it is reported as its parts.

    A container boot logs "+oauth+wsgi" and never the word "deploy". This pins
    that installing the deploy profile is detectable through its components.
    """
    with patch.object(build_info, "_module_available", side_effect=lambda m: m in ("gunicorn", "social_django")):
        assert build_info.installed_extras() == ["oauth", "wsgi"]


def test_installed_extras_reflects_marker_availability():
    with patch.object(build_info, "_module_available", side_effect=lambda m: m == "celery"):
        assert build_info.installed_extras() == ["tasks"]


def test_installed_extras_empty_on_barebones_core():
    """A plain `pip install .` reports core only, with no optionals."""
    with patch.object(build_info, "_module_available", return_value=False):
        assert build_info.installed_extras() == []


def test_missing_required_flags_absent_startup_modules():
    with patch.object(build_info, "_module_available", side_effect=lambda m: m != "daphne"):
        assert build_info.missing_required() == ["daphne"]


def test_missing_required_is_empty_on_a_healthy_install():
    """The real environment must satisfy every startup requirement.

    This is the assertion that would have caught daphne/openai-agents being
    moved to extras: they are in REQUIRED_MODULES precisely because
    settings.INSTALLED_APPS and core.blueprint_base need them.
    """
    assert build_info.missing_required() == []


def test_module_available_handles_broken_specs():
    """find_spec raises for modules with __spec__ = None; probe must not."""
    with patch.object(build_info, "find_spec", side_effect=ValueError("__spec__ is None")):
        assert build_info._module_available("anything") is False
    with patch.object(build_info, "find_spec", side_effect=ImportError("boom")):
        assert build_info._module_available("anything") is False


def test_build_profile_shape():
    profile = build_info.build_profile()
    assert set(profile) == {
        "distribution",
        "version",
        "python",
        "extras",
        "missing_required",
    }
    assert profile["distribution"] == "os-core"
    assert isinstance(profile["extras"], list)
    assert isinstance(profile["python"], str)


def test_distribution_version_survives_missing_metadata():
    with patch.object(build_info.metadata, "version", side_effect=build_info.metadata.PackageNotFoundError):
        assert build_info.distribution_version() is None


def test_summary_line_reports_core_only():
    with patch.object(build_info, "distribution_version", return_value="9.9.9"):
        with patch.object(build_info, "installed_extras", return_value=[]):
            with patch.object(build_info, "missing_required", return_value=[]):
                assert build_info.summary_line() == "os-core 9.9.9 (core only)"


def test_summary_line_flags_missing_required_modules():
    with patch.object(build_info, "distribution_version", return_value="9.9.9"):
        with patch.object(build_info, "installed_extras", return_value=["oauth"]):
            with patch.object(build_info, "missing_required", return_value=["agents"]):
                line = build_info.summary_line()
    assert "+oauth" in line
    assert "MISSING REQUIRED: agents" in line


@pytest.mark.django_db
def test_build_endpoint_reports_the_running_profile(client):
    # Authenticated rather than the bare `api_client` fixture: settings.py
    # calls load_swarm_dotenv() at *import* time, before conftest's
    # isolate_xdg_config can redirect HOME, so a developer with a real
    # ~/.config/swarm/.env gets ENABLE_API_AUTH=True and a bare APIClient
    # 403s. That made this test permanently red on a normal dev box while
    # passing in CI -- the worst kind of false confidence.
    User = get_user_model()
    client.force_login(User.objects.create_user(username="buildinfo", password="pw"))
    resp = client.get("/v1/system/build/")
    assert resp.status_code == 200
    body = resp.json()
    assert body["distribution"] == "os-core"
    assert "extras" in body
    assert body["missing_required"] == []

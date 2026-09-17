"""REQ-885 — source lock for the config-discovery default.

Spec of record: docs/qa/REQ-885-config-discovery-default.md
Behaviour tests: tests/core/test_config_loader.py::TestDefaultConfigDiscovery

These pin the shape so a no-override caller cannot silently go back to merging
against an empty base config, and so the two default filenames stay in step.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CONFIG_LOADER = REPO / "src" / "swarm" / "core" / "config_loader.py"
PATHS = REPO / "src" / "swarm" / "core" / "paths.py"
SPEC = REPO / "docs" / "qa" / "REQ-885-config-discovery-default.md"

DISCOVERY_CALL = "config_path = find_config_file() or get_swarm_config_file()"


def _loader_default_branch() -> str:
    """The else-branch that resolves config_path when nothing was passed in."""
    body = CONFIG_LOADER.read_text(encoding="utf-8").split(
        "def load_full_configuration", 1
    )[1]
    return body.split("base_config = {}", 1)[0]


def test_req885_no_override_uses_discovery():
    branch = _loader_default_branch()
    assert DISCOVERY_CALL in branch, "the no-override branch must discover the config"
    # The fallback keeps the not-found warning naming a concrete path.
    assert "or get_swarm_config_file()" in DISCOVERY_CALL


def test_req885_explicit_paths_still_win():
    branch = _loader_default_branch()
    discovery_at = branch.index(DISCOVERY_CALL)
    assert branch.index("if config_path_override:") < discovery_at
    assert branch.index("elif default_config_path_for_tests:") < discovery_at


def test_req885_config_filename_default_matches_every_other_reader():
    text = PATHS.read_text(encoding="utf-8")
    assert (
        'def get_swarm_config_file(config_filename: str = "swarm_config.json")' in text
    )
    # The stale default must not be the *signature* default again; explaining the
    # history in the docstring and tests is fine.
    assert 'config_filename: str = "config.yaml"' not in text


def test_req885_requirements_gets_a_real_config():
    """``load_active_config`` is the caller this bug silently emptied."""
    requirements = (REPO / "src" / "swarm" / "core" / "requirements.py").read_text(
        encoding="utf-8"
    )
    assert 'load_full_configuration(blueprint_class_name="__requirements__")' in requirements


def test_req885_spec_doc_is_shipped():
    assert SPEC.is_file()
    text = SPEC.read_text(encoding="utf-8")
    assert "REQ-885" in text
    assert "test_req885_config_discovery_default.py" in text

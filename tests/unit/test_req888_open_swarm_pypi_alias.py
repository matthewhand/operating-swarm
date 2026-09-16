"""REQ-888 / #296 — PyPI `open-swarm` is a deprecation alias, not the product.

Product wheel is `os-core`. This stub lives in-tree at packaging/open-swarm-alias/.
Publish of the stub is operator-only after `os-core` exists on PyPI; do not yank 0.5.4.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STUB = REPO / "packaging" / "open-swarm-alias"
PYPROJECT = STUB / "pyproject.toml"
README = STUB / "README.md"


def _data() -> dict:
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def _project() -> dict:
    return _data()["project"]


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split(".")[:3])


def test_stub_pyproject_name_version_and_inactive_classifier():
    project = _project()
    assert project["name"] == "open-swarm"
    assert _version_tuple(str(project["version"])) > (0, 5, 4)
    assert "Development Status :: 7 - Inactive" in project["classifiers"]


def test_stub_pyproject_depends_on_os_core():
    project = _project()
    deps = list(project.get("dependencies") or [])
    names = [str(dep).split()[0].split("[")[0] for dep in deps]
    assert "os-core" in names
    assert "os-core" in " ".join(str(d) for d in deps)


def test_stub_pyproject_does_not_define_swarm_cli_or_other_scripts():
    data = _data()
    project = data["project"]
    scripts = project.get("scripts") or {}
    assert "swarm-cli" not in scripts
    assert "os-cli" not in scripts
    assert "os-api" not in scripts
    assert scripts == {}
    raw = PYPROJECT.read_text(encoding="utf-8")
    assert "[project.scripts]" not in raw
    assert "swarm-cli" not in raw


def test_stub_readme_is_rename_banner_not_full_product():
    text = README.read_text(encoding="utf-8")
    lowered = text.lower()
    assert "operating swarm" in lowered
    assert "os-core" in text
    assert "https://github.com/matthewhand/operating-swarm" in text
    assert "open-swarm" in lowered
    assert "deprecated" in lowered or "deprecation" in lowered or "alias" in lowered
    assert not (STUB / "src" / "swarm").exists()
    # Stub is not a second copy of the app README.
    assert "## Kinds (locked)" not in text
    assert "WebUI is first-class" not in text

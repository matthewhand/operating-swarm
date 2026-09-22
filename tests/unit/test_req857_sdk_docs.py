"""#857 — SDK surface boundaries and doc coverage.

Contracts:
- Every first-class package ``__init__.py`` (excluding Django plumbing and
  deprecated blueprint stubs) defines an explicit ``__all__``.
- The key SDK modules a recipe author imports are documented at module
  level and expose Google-style docstrings on their public callables.
- MkDocs + mkdocstrings config exists and its nav references real files.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src"
REPO = SRC.parent

# Packages whose ``__init__`` must declare ``__all__``. Django plumbing
# (migrations/management) is excluded; deprecated stub packages are covered
# by the blueprint discovery doc rules instead.
BOUNDARY_PACKAGES = [
    "swarm/remotes",
    "swarm/core/remote_impls",
    "swarm/core/sandbox",
    "swarm/core/roles",
    "swarm/memory",
    "swarm/services",
    "swarm/custom_cli_agents",
    "swarm/herdr",
]

# Key SDK modules: every public callable (def/class at col 0, no leading _)
# must carry a docstring, and the module itself must have a docstring.
SDK_MODULES = [
    "swarm/core/sandbox/base.py",
    "swarm/core/sandbox/manager.py",
    "swarm/core/sandbox/opt_in.py",
    "swarm/core/sandbox/display.py",
    "swarm/core/roles/base.py",
    "swarm/remotes/base.py",
    "swarm/remotes/registry.py",
    "swarm/herdr/ssh.py",
]

DEF_RE = re.compile(r"^(?:class|def|async def)\s+([A-Za-z_][A-Za-z0-9_]*)")


def _docstring_follows(lines: list[str], idx: int) -> bool:
    """True when a docstring opens before the body starts.

    Scans from the def line past decorators, a multi-line signature (until
    the line ending in ``:``), and blank lines — a docstring anywhere before
    the first real statement counts.
    """
    j = idx + 1
    # Skip decorators/blank lines, then the rest of a multi-line signature.
    seen_colon = lines[idx].rstrip().endswith(":")
    while j < len(lines):
        stripped = lines[j].strip()
        if not stripped or stripped.startswith("@"):
            j += 1
            continue
        if not seen_colon:
            if stripped.endswith(":") and not stripped.startswith(('"', "'")):
                seen_colon = True
            j += 1
            continue
        break
    while j < len(lines) and not lines[j].strip():
        j += 1
    return j < len(lines) and lines[j].lstrip().startswith(( '"""', "'''"))


@pytest.mark.parametrize("pkg", BOUNDARY_PACKAGES)
def test_package_defines_all(pkg: str):
    init = SRC / pkg / "__init__.py"
    assert init.exists(), f"package missing: {pkg}"
    text = init.read_text()
    assert "__all__" in text, f"{pkg}/__init__.py must declare __all__ (#857)"


@pytest.mark.parametrize("rel", SDK_MODULES)
def test_sdk_module_documents_public_surface(rel: str):
    path = SRC / rel
    assert path.exists(), f"SDK module missing: {rel}"
    lines = path.read_text().splitlines()
    assert lines and lines[0].lstrip().startswith(('"""', "'''")), (
        f"{rel} needs a module-level docstring (#857)"
    )
    missing: list[str] = []
    for i, line in enumerate(lines):
        m = DEF_RE.match(line)
        if not m or m.group(1).startswith("_"):
            continue
        if not _docstring_follows(lines, i):
            missing.append(m.group(1))
    assert not missing, f"{rel} public callables without docstrings: {missing}"


def test_mkdocs_config_and_nav():
    cfg = REPO / "mkdocs.yml"
    assert cfg.exists(), "mkdocs.yml must exist (#857)"
    text = cfg.read_text()
    assert "mkdocstrings" in text, "mkdocstrings must be configured"
    assert "material" in text, "mkdocs-material must be the theme"
    # Every nav entry referencing an API file must point at a real file.
    nav_files = re.findall(r"docs/[\w/.\-]+\.md", text)
    for rel in nav_files:
        assert (REPO / rel).exists(), f"mkdocs nav references missing file: {rel}"


def test_reference_docs_generated():
    ref_dir = REPO / "docs" / "sdk" / "reference"
    assert ref_dir.exists(), "docs/sdk/reference/ must exist"
    index = ref_dir / "index.md"
    assert index.exists() and "swarm.core" in index.read_text()

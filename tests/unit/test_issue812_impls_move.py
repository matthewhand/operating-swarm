"""#812 slice 5 — the remotes.py monolith moved its impl bodies out.

``swarm.core.remotes`` kept the kernel (config persistence, specs, health,
operate, catalog) while every per-harness body moved verbatim to
``swarm.core.remote_impls.<kind>`` (plus ``_wiring`` for the REQ-203
registrations). These tests pin the structural contract of that move:

1. the issue's ≥65% line-count reduction actually happened,
2. every historical name still resolves on ``remotes`` (lazy re-export),
3. kept code never references a moved name *bare* — bare names inside
   remotes.py do not hit module ``__getattr__``, so a bare call is a
   runtime ``NameError`` (it must go through the ``R`` handle),
4. impl modules import the kernel via the module object (``R``), never
   by value — that is what keeps ``monkeypatch.setattr(remotes, ...)``
   effective from the moved bodies.
"""

from __future__ import annotations

import ast
from pathlib import Path

import swarm.core.remotes as remotes
from swarm.core.remote_impls import NAME_TO_MODULE

REPO = Path(__file__).resolve().parents[2]
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"
IMPLS = REPO / "src" / "swarm" / "core" / "remote_impls"

# Issue #812's baseline (the monolith it was filed against).
BASELINE_LINES = 6334


def test_remotes_line_count_reduced_by_65_percent():
    lines = len(REMOTES.read_text(encoding="utf-8").splitlines())
    ceiling = BASELINE_LINES * 0.35
    assert lines <= ceiling, (
        f"remotes.py is {lines} lines; #812 requires <= {ceiling:.0f} "
        f"(65% below the {BASELINE_LINES}-line baseline)"
    )


def test_every_moved_name_still_resolves_on_remotes():
    for name in NAME_TO_MODULE:
        obj = getattr(remotes, name)  # AttributeError here = broken re-export
        home = getattr(obj, "__module__", "")
        assert home.startswith("swarm.core.remote_impls"), (
            f"{name} resolved from {home or type(obj)!r}, not the impl package"
        )


def test_no_bare_references_to_moved_names_in_kept_code():
    """A bare Name-load of a moved name inside remotes.py bypasses module
    __getattr__ and raises NameError at call time. Kept call sites must
    use the ``R`` handle (attribute access is late-bound)."""
    moved = set(NAME_TO_MODULE)
    tree = ast.parse(REMOTES.read_text(encoding="utf-8"))
    bare: set[tuple[str, str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for sub in ast.walk(node):
                if (
                    isinstance(sub, ast.Name)
                    and isinstance(sub.ctx, ast.Load)
                    and sub.id in moved
                ):
                    bare.add((node.name, sub.id, sub.lineno))
    assert bare == set(), (
        f"kept functions reference moved impl names bare (NameError at call "
        f"time) — qualify via R: {sorted(bare)}"
    )


def test_impl_modules_import_kernel_via_module_object():
    """Patch safety: impl bodies must resolve kernel names at call time via
    the ``R`` module handle, never bind them by value at import."""
    offenders: list[str] = []
    for path in sorted(IMPLS.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "swarm.core.remotes":
                names = ", ".join(a.name for a in node.names)
                offenders.append(f"{path.name}: from swarm.core.remotes import {names}")
    assert not offenders, (
        "impl modules must not value-import kernel names (breaks "
        f"monkeypatch.setattr(remotes, ...)): {offenders}"
    )

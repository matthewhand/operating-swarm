"""#812 slice 5 — the remotes.py monolith moved its impl bodies out.

``swarm.core.remotes`` kept the kernel (config persistence, specs, health,
operate, catalog) while every per-harness body moved verbatim to
``swarm.core.remote_impls.<kind>`` (plus ``_wiring`` for the REQ-203
registrations). These tests pin the structural contract of that move:

1. the per-harness logic is OUT of ``remotes.py`` — asserted structurally,
   not by a raw line count (the long note below says why the count went),
2. every historical name still resolves on ``remotes`` (lazy re-export),
3. kept code never references a moved name *bare* — bare names inside
   remotes.py do not hit module ``__getattr__``, so a bare call is a
   runtime ``NameError`` (it must go through the ``R`` handle),
4. impl modules import the kernel via the module object (``R``), never
   by value — that is what keeps ``monkeypatch.setattr(remotes, ...)``
   effective from the moved bodies.  Together 3+4 are the import-cycle
   guard: if a cycle comes back, one of them fails.

WHY #812's RAW LINE COUNT WAS REPLACED (not merely relaxed)
-----------------------------------------------------------
The original test 1 was ``remotes.py <= 2300 lines``, against the
6334-line monolith #812 was filed against.  That target is unreachable,
and the reason is worth recording rather than working around:

* ``remotes.py`` measures **2988** lines today.  Reaching 2300 means
  shedding **688**.
* The per-harness *bodies* still in the kernel are exactly the 7 defs in
  :data:`RESIDUAL_HARNESS_BODIES` — **235 lines** (trueforge's catalog /
  turn-state cluster, ``_apply_herdr_persist``, ``is_trueforge_remote``).
  Moving *all* of them still leaves 2753, i.e. **453** over the ceiling.
* That 453 only comes out of the kernel itself: ``load_remote`` (189),
  ``persist_remote`` (167), ``operate`` (138), ``RemoteSpec`` (136),
  ``probe_candidate_remote`` (77), ``configured_remote_ids`` (41) — **748**
  lines, i.e. the module's identity, against a 453 gap.  Relocating those
  re-creates precisely the bare-``Name`` / import-cycle hazard that tests 3
  and 4 exist to catch, in a module whose entire public API is a PEP-562
  lazy re-export.

A line count is also the wrong *kind* of statement: it cannot see where
code lives, so each of these regressions satisfies it.

* Re-adding ``def _anythingllm_list(...)`` to the kernel.  ``__getattr__``
  is only consulted for names **absent** from module globals, so the new
  kernel copy silently **shadows** the impl package's body —
  ``remotes._anythingllm_list`` starts returning the kernel function, the
  impl body becomes dead code, and every re-export and patch-target test
  still passes.
* The same body re-added under a fresh name (``_anythingllm_list_v2``), or
  as a new per-harness helper.
* A per-harness branch added to a *generically named* kernel function:
  three lines of ``if kind == "flowise":`` cost nothing against any ceiling.
* Any of the above made to fit by deleting comments and docstrings
  elsewhere — that is how a line-count gate gets satisfied.

The assertions below catch every one of those, and they hold against the
tree as it stands.  They state the issue's actual invariant: per-harness
logic lives in ``remote_impls/``, and the kernel may only *know about*
harnesses as data.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import swarm.core.remotes as remotes
from swarm.core.remote_impls import NAME_TO_MODULE

REPO = Path(__file__).resolve().parents[2]
REMOTES = REPO / "src" / "swarm" / "core" / "remotes.py"
IMPLS = REPO / "src" / "swarm" / "core" / "remote_impls"

# Issue #812's baseline (the monolith it was filed against).
BASELINE_LINES = 6334

# Post-#812 high-water mark: 2276 at the #1000 move, then honest feature code
# landed in the kernel afterwards (#1170 chat gate, #1182 confirm-retry probe).
# The pin now guards against the monolith REGROWING from that mark — new
# per-harness bodies belong in remote_impls/, not here.
_HARNESS_TOKEN = re.compile(
    r"(?<![a-z0-9])(hermes|anythingllm|openwebui|flowise|n8n|omb|rakazo"
    r"|herdr|swarm|trueforge|octop|openmuse)(?![a-z0-9])"
)

# Frozen high-water mark for the kernel, at its real post-move size.  This is
# a *secondary* non-regrowth alarm, not the invariant — see the header note.
# The old 2300 ceiling had been red for a long time and a permanently-red
# assertion guards nothing; pinning the real size restores an alarm that
# actually fires.  Moving the 235 lines in RESIDUAL_HARNESS_BODIES out is the
# next slice and should lower this number.
KERNEL_HIGH_WATER_LINES = 2988

# ── The frozen residual ────────────────────────────────────────────────────
# #812 could not move these without dismantling the kernel (see the header
# note).  They are listed rather than hidden, so the debt is enumerable and
# can only shrink.  Moving one means DELETING its entry here — adding an
# entry always means also moving the body out.

#: def/class in remotes.py whose *name* is tagged with a harness id.
RESIDUAL_HARNESS_BODIES: frozenset[str] = frozenset(
    {
        # trueforge — the catalog + latest-session cluster derives the
        # TrueForge agent/session shapes. ``trueforge_catalog`` is public API
        # (the Settings view calls it), so it cannot hide behind a lazy
        # re-export without a caller change.
        "is_trueforge_remote",
        "_latest_trueforge_session",
        "_normalize_trueforge_catalog_agents",
        "_normalize_trueforge_catalog_sessions",
        "_trueforge_catalog_payload",
        "trueforge_catalog",
        # herdr — SSH-vs-local config persistence, called from inside
        # persist_remote's transaction.
        "_apply_herdr_persist",
    }
)

#: def/class in remotes.py allowed to *branch* on a harness-id string literal.
#: The rest of the per-harness residue is data (REMOTE_IDS, _DEFAULTS,
#: _ENV_*, _TOOL_NAMES, the per-kind timeout knobs) which is catalog-shaped
#: and legitimate.  Adding a name here is how the kernel regrows: an adapter
#: method or a registry entry is the extension seam, per RemoteAdapter.
RESIDUAL_HARNESS_DISPATCH: frozenset[str] = frozenset(
    {
        # id -> kind resolution over the catalogued ids.
        "kind_of_instance",
        # trueforge — the "is this a trueforge instance" predicate.
        "is_trueforge_remote",
        # herdr — the only harness with a second transport, so config
        # persistence and probing carry an ssh-vs-local branch.
        "_opt_in_not_configured_message",
        "load_remote",
        "configured_remote_ids",
        "persist_remote",
        "probe_candidate_remote",
        # n8n — header name differs from the generic api-key header.
        "_auth_headers",
        # herdr/trueforge — per-kind send timeout and resume shape.
        "operate",
        # trueforge catalog (public view API).
        "_trueforge_catalog_payload",
        "trueforge_catalog",
        # RemoteSpec.public_dict publishes the herdr ssh target.
        "RemoteSpec.public_dict",
    }
)


def _defined_names(path: Path) -> set[str]:
    """Qualified names of every def/class in ``path``.

    A class body is its own namespace, so its methods are reported as
    ``Class.method``; a function body is not, so nested defs stay
    unqualified (``outer`` owns the whole subtree).
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                out.add(qual)
                visit(child, f"{qual}." if isinstance(child, ast.ClassDef) else "")
            else:
                visit(child, prefix)

    visit(tree)
    return out


def _docstring_nodes(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)
        ):
            continue
        if (
            node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        ):
            ids.add(id(node.body[0].value))
    return ids


def _owns_harness_literal(node: ast.AST, docstrings: set[int]) -> bool:
    """True when ``node``'s *own* body holds a harness-id string literal.

    Nested defs/classes are skipped: they are visited separately and reported
    under their own qualified name, so a class is never blamed for a method
    (``RemoteSpec`` is not per-harness dispatch; ``RemoteSpec.public_dict``
    is, and is listed on its own).
    """
    stack = list(ast.iter_child_nodes(node))
    while stack:
        sub = stack.pop()
        if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if (
            isinstance(sub, ast.Constant)
            and isinstance(sub.value, str)
            and id(sub) not in docstrings
            and _HARNESS_TOKEN.fullmatch(sub.value.lower())
        ):
            return True
        stack.extend(ast.iter_child_nodes(sub))
    return False


def _harness_dispatch_owners(path: Path) -> set[str]:
    """Qualified names of defs/classes whose own body branches on a harness id.

    AST-based, so a harness id in a comment, a docstring, or a module-level
    catalog is never mistaken for dispatch.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = _docstring_nodes(tree)
    owners: set[str] = set()

    def visit(node: ast.AST, prefix: str = "") -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qual = f"{prefix}{child.name}"
                if _owns_harness_literal(child, docstrings):
                    owners.add(qual)
                visit(child, f"{qual}." if isinstance(child, ast.ClassDef) else "")
            else:
                visit(child, prefix)

    visit(tree)
    return owners


def test_remotes_defines_no_per_harness_body():
    """#812's invariant, structurally: the per-harness logic is OUT.

    Aims at exactly the re-introductions a line count cannot see — a moved
    name re-bound in the kernel (which shadows the lazy re-export), a body
    re-added under a fresh harness-tagged name, and a per-harness branch
    added to a generically named kernel function.
    """
    defined = _defined_names(REMOTES)
    dispatching = _harness_dispatch_owners(REMOTES)

    # 1a. nothing rebinds a name #812 moved into remote_impls/.
    redefined = sorted(n for n in NAME_TO_MODULE if n in defined)
    assert not redefined, (
        "remotes.py rebinds names #812 moved into remote_impls/. PEP-562 "
        "__getattr__ only fires for names absent from module globals, so "
        f"these SHADOW the impl package: {redefined}"
    )

    # 1b. no per-harness body under a *fresh* name either.
    tagged = sorted(
        qual
        for qual in defined
        if _HARNESS_TOKEN.search(qual.rsplit(".", 1)[-1].lower())
        and qual not in RESIDUAL_HARNESS_BODIES
    )
    assert not tagged, (
        f"per-harness bodies re-added to remotes.py: {tagged}. New per-harness "
        "logic belongs in remote_impls/. If this is genuinely kernel, name it "
        "without a harness id and the assertion stays honest."
    )

    # 2. no per-harness branch anywhere, including inside kernel functions
    #    whose own name carries no harness token.
    added = sorted(dispatching - RESIDUAL_HARNESS_DISPATCH)
    assert not added, (
        f"per-harness dispatch added to remotes.py: {added}. The kernel may "
        "know harnesses as data (catalogs, timeouts, env names) but must not "
        "branch on them — add an adapter method or a registry entry instead."
    )

    # The residual is frozen in both directions: an entry may be deleted when
    # the body moves out, but neither list may drift from what the file holds.
    vanished = sorted(RESIDUAL_HARNESS_DISPATCH - dispatching)
    assert not vanished, (
        f"RESIDUAL_HARNESS_DISPATCH still lists {vanished}, which no longer "
        "branch on a harness id — the body moved out, so DELETE the entry."
    )
    stale_bodies = sorted(RESIDUAL_HARNESS_BODIES - defined)
    assert not stale_bodies, (
        f"RESIDUAL_HARNESS_BODIES still lists {stale_bodies}, which no longer "
        "exist in remotes.py — the body moved out, so DELETE the entry."
    )


def test_remotes_kernel_does_not_regrow():
    """Secondary non-regrowth alarm (see KERNEL_HIGH_WATER_LINES).

    Not the issue's invariant — test_remotes_defines_no_per_harness_body is.
    This only fires on net growth, which is precisely the regression the old
    2300 ceiling stopped seeing the day it went red.
    """
    lines = len(REMOTES.read_text(encoding="utf-8").splitlines())
    assert lines <= KERNEL_HIGH_WATER_LINES, (
        f"remotes.py grew to {lines} lines (high-water mark "
        f"{KERNEL_HIGH_WATER_LINES}). Per-harness bodies belong in "
        "remote_impls/; kernel growth needs its own justification."
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


def _is_type_checking_test(test: ast.expr) -> bool:
    """True for the expression ``TYPE_CHECKING`` or ``typing.TYPE_CHECKING``.

    Both spellings are the same guard. An attribute on any *other* module is
    not -- ``env.TYPE_CHECKING`` is that project's own flag and says nothing
    about whether this block runs at runtime.
    """
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    return (
        isinstance(test, ast.Attribute)
        and test.attr == "TYPE_CHECKING"
        and isinstance(test.value, ast.Name)
        and test.value.id == "typing"
    )


def runtime_kernel_imports(source: str) -> list[str]:
    """Every ``from swarm.core.remotes import ...`` that executes at runtime.

    Imports inside the *body* of an ``if TYPE_CHECKING:`` are annotation-only
    and are deliberately excluded. ``from __future__ import annotations``
    (PEP 563) stops an annotation being *evaluated*; it does not make the name
    exist, so a type checker still needs the import -- but the import itself
    never runs, so it cannot bind a name by value, and therefore cannot break
    ``monkeypatch.setattr(remotes, ...)``. That is the distinction this test
    exists to draw, and walking the tree without it flagged all 10 impl modules
    for an import they never perform.

    The exemption is scoped to the guarded *body*. An ``else:`` arm and a
    guard on any other name are ordinary runtime code.
    """
    found: list[str] = []

    def visit(node: ast.AST, guarded: bool) -> None:
        if isinstance(node, ast.If):
            # The body inherits the guard; the orelse never does, even when
            # the test is TYPE_CHECKING -- `if TYPE_CHECKING: ... else: ...`
            # runs its else arm at runtime.
            body_guarded = guarded or _is_type_checking_test(node.test)
            for stmt in node.body:
                visit(stmt, body_guarded)
            for stmt in node.orelse:
                visit(stmt, guarded)
            return
        if (
            isinstance(node, ast.ImportFrom)
            and node.module == "swarm.core.remotes"
            and not guarded
        ):
            found.append(", ".join(a.name for a in node.names))
        for child in ast.iter_child_nodes(node):
            visit(child, guarded)

    visit(ast.parse(source), guarded=False)
    return found


def test_impl_modules_import_kernel_via_module_object():
    """Patch safety: impl bodies must resolve kernel names at call time via
    the ``R`` module handle, never bind them by value at import.

    See :func:`runtime_kernel_imports` for why ``if TYPE_CHECKING:`` imports
    are not counted, and
    :func:`test_a_runtime_value_import_of_a_kernel_name_is_still_an_offender`
    for the proof that the exemption did not blunt the rule.
    """
    offenders: list[str] = []
    for path in sorted(IMPLS.glob("*.py")):
        for names in runtime_kernel_imports(path.read_text(encoding="utf-8")):
            offenders.append(f"{path.name}: from swarm.core.remotes import {names}")
    assert not offenders, (
        "impl modules must not value-import kernel names (breaks "
        f"monkeypatch.setattr(remotes, ...)): {offenders}"
    )


def test_a_runtime_value_import_of_a_kernel_name_is_still_an_offender():
    """The exemption above must not have blunted the rule.

    Each case below is a *runtime* import written in a shape close enough to
    the exempted one that a sloppy guard would miss it. If the TYPE_CHECKING
    exemption ever grows to cover any of these, this test goes red -- which is
    the point: the original test failed for a reason that was not a defect,
    and the fix for that must not become a way to smuggle a real one back in.
    """
    # 1. The plain case the test has always policed.
    assert runtime_kernel_imports(
        "from swarm.core.remotes import RemoteSpec\n"
    ) == ["RemoteSpec"]

    # 2. An `else:` arm is runtime code, even on a TYPE_CHECKING `if`.
    assert runtime_kernel_imports(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from swarm.core.remotes import RemoteSpec\n"
        "else:\n"
        "    from swarm.core.remotes import OperateResult\n"
    ) == ["OperateResult"], "the orelse of a TYPE_CHECKING guard runs at runtime"

    # 3. `not TYPE_CHECKING` inverts the guard: the body is the runtime half.
    assert runtime_kernel_imports(
        "from typing import TYPE_CHECKING\n"
        "if not TYPE_CHECKING:\n"
        "    from swarm.core.remotes import RemoteSpec\n"
    ) == ["RemoteSpec"]

    # 4. A guard on some *other* name does not exempt anything.
    assert runtime_kernel_imports(
        "if SOME_OTHER_FLAG:\n"
        "    from swarm.core.remotes import RemoteSpec\n"
    ) == ["RemoteSpec"]

    # 5. Qualified guard form is the same guard, so it is exempt too.
    assert runtime_kernel_imports(
        "import typing\n"
        "if typing.TYPE_CHECKING:\n"
        "    from swarm.core.remotes import RemoteSpec\n"
    ) == []

    # 5b. An attribute guard on some *other* module is not a type-check guard.
    assert runtime_kernel_imports(
        "import env\n"
        "if env.TYPE_CHECKING:\n"
        "    from swarm.core.remotes import RemoteSpec\n"
    ) == ["RemoteSpec"], "only typing.TYPE_CHECKING is a type-check guard"

    # 6. A genuinely type-check-only import IS exempt -- the positive case, so
    #    the negative cases above are not passing for the wrong reason.
    assert runtime_kernel_imports(
        "from typing import TYPE_CHECKING\n"
        "if TYPE_CHECKING:\n"
        "    from swarm.core.remotes import RemoteSpec, OperateResult\n"
    ) == []

    # 7. And the rule still holds against the real tree: the exemption is
    #    scoped to the guard, not to the module.
    for path in sorted(IMPLS.glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert runtime_kernel_imports(source) == [], (
            f"{path.name} has a runtime value-import of a kernel name"
        )

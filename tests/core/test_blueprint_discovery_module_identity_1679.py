"""#1679: blueprint discovery must not fork a blueprint module.

``discover_blueprints`` does not import blueprint packages the way the import
system does. It builds a spec for the ``.py`` **by file path**, registers the
fresh module in ``sys.modules`` and execs it — and used to do nothing about the
parent package attribute. One dotted name, two live objects::

    swarm.blueprints.agent_router.blueprint_agent_router
      sys.modules[dotted]         -> the module discovery just executed
      getattr(parent_pkg, leaf)   -> the module imported earlier, pre-fork

The seam splits in two, and both halves are load-bearing:

* ``swarm/blueprints/agent_router/engines.py`` late-binds the router through
  ``_RouterRef.__getattr__``, which calls ``importlib.import_module(...)`` on
  **every** access — a ``sys.modules`` read.
* ``from pkg import mod`` and ``monkeypatch.setattr("pkg.mod.X", ...)`` resolve
  through the **package attribute**: pytest's ``_pytest.monkeypatch.resolve()``
  walks the dotted path with ``getattr`` and only falls back to
  ``import_module`` on ``AttributeError``.

So a patch lands on the object nobody reads, the real ``agents.Agent`` is built
with a stub model, the run raises, and the seat silently degrades to its canned
text. Symptom: ``tests/core/test_operator_profile.py`` green alone, red after
any other discovery-triggering test.

The fix is in ``blueprint_discovery``: reuse the already-imported module when it
came from the same file (no re-execution, so no fork), and publish the module on
its parent package the way ``importlib._bootstrap._load`` does.

What is deliberately pinned as well: reconciling the parent attribute *after*
``exec_module`` (approach (a)) also makes ``sys.modules`` and
``getattr(parent, leaf)`` agree, but it leaves every **already-bound by-name**
reference stale — the ``AgentRouterBlueprint`` class ``agent_router_views`` binds
at import time still points at the pre-fork module dict, so a dotted patch of
``listed_remote_specs`` stops reaching the object the view runs and
``test_list_agents_includes_discovered_remote_children`` fails. The last two
tests in the first section pin that half too.
"""

from __future__ import annotations

import importlib
import importlib.util
import subprocess
import sys
import textwrap
import types

import pytest

ROUTER_PKG = "swarm.blueprints.agent_router"
ROUTER_MODULE = "swarm.blueprints.agent_router.blueprint_agent_router"


@pytest.fixture
def blueprint_dir() -> str:
    from django.conf import settings

    return str(settings.BLUEPRINT_DIRECTORY)


@pytest.fixture
def router_module():
    """A NORMAL import of the router module — the pre-fork object."""
    return importlib.import_module(ROUTER_MODULE)


@pytest.fixture
def router_package():
    return importlib.import_module(ROUTER_PKG)


# --------------------------------------------------------------------------
# the fork itself
# --------------------------------------------------------------------------


def test_discovery_leaves_one_module_object_for_the_dotted_name(
    blueprint_dir, router_module, router_package
):
    """``sys.modules[dotted]`` and ``getattr(parent, leaf)`` are the same object.

    A normal import binds the child on its parent as part of the same
    operation, so the two names can never diverge. Discovery used to do the
    ``sys.modules`` half only, which left ``agent_router`` re-executable on
    every discovery call, with a second live class object behind one name.
    """
    from swarm.core.blueprint_discovery import discover_blueprints

    found = discover_blueprints(blueprint_dir)
    assert "agent_router" in found, sorted(found)

    from_sys_modules = sys.modules[ROUTER_MODULE]
    from_package = getattr(router_package, "blueprint_agent_router", None)

    assert from_sys_modules is router_module, (
        "discovery re-executed a module that was already imported from the same "
        "file; sys.modules now holds a second object for one dotted name"
    )
    assert from_package is from_sys_modules, (
        "sys.modules and the parent package attribute disagree: the dotted name "
        f"resolves to two objects ({id(from_sys_modules)} vs {id(from_package)})"
    )


def test_discovery_reuses_the_imported_module_instead_of_re_executing(
    blueprint_dir, router_module, monkeypatch
):
    """Reuse is the mechanism, so assert it rather than inferring it.

    A sentinel set on the normally imported module survives discovery only if
    discovery handed back that same object; re-executing the file builds a new
    module dict without it, and the discovered class is a new class too.
    """
    from swarm.core.blueprint_discovery import discover_blueprints

    sentinel = object()
    monkeypatch.setattr(router_module, "SENTINEL_1679", sentinel, raising=False)

    found = discover_blueprints(blueprint_dir)

    assert getattr(sys.modules[ROUTER_MODULE], "SENTINEL_1679", None) is sentinel, (
        "discovery rebuilt the module from source instead of reusing the "
        "already-imported one — the fork is back"
    )
    assert found["agent_router"]["class_type"] is router_module.AgentRouterBlueprint


# --------------------------------------------------------------------------
# the by-name half: approach (a) reconciles the name, not the references
# --------------------------------------------------------------------------


def test_discovery_keeps_by_name_references_on_the_module_it_loads(
    blueprint_dir, router_module
):
    """A class bound *before* discovery must keep the globals discovery reads.

    ``load_designed_agents`` reads ``listed_remote_specs`` — imported by name at
    ``blueprint_agent_router.py:37`` and read at ``:692`` — from the module dict
    that was live when the class was created. ``swarm/views/agent_router_views.py``
    binds ``AgentRouterBlueprint`` at import time, so this is exactly the
    reference ``/v1/agents/`` runs.

    Reconciling only the parent attribute flips the *name* to the forked module
    and leaves this reference behind: the two disagree, and the patch that used
    to reach the view silently stops reaching it.
    """
    from swarm.core.blueprint_discovery import discover_blueprints

    bound_before = router_module.AgentRouterBlueprint
    globals_before = bound_before.load_designed_agents.__globals__
    assert "listed_remote_specs" in globals_before

    discover_blueprints(blueprint_dir)

    assert sys.modules[ROUTER_MODULE].__dict__ is globals_before, (
        "the class bound before discovery and the module discovery loads back "
        "different globals: by-name references are stale"
    )


def test_one_monkeypatch_reaches_both_readers(
    blueprint_dir, router_module, monkeypatch
):
    """The whole defect in one test: one patch, two readers, one object.

    ``monkeypatch.setattr("<dotted>.listed_remote_specs", ...)`` resolves through
    the package attribute, while ``engines._RouterRef`` re-imports the dotted
    name on every attribute access (a ``sys.modules`` read). Before the fix the
    patch landed on one of two module objects, so the engine's read missed it —
    which is how the About me card vanished and the seat fell back to its canned
    text once another test had run discovery.
    """
    from swarm.blueprints.agent_router import engines
    from swarm.core.blueprint_discovery import discover_blueprints

    bound_before = router_module.AgentRouterBlueprint
    discover_blueprints(blueprint_dir)

    def fake_listed(config=None, *, expand=None):  # noqa: ARG001 - stands in for the real lister
        return []

    monkeypatch.setattr(f"{ROUTER_MODULE}.listed_remote_specs", fake_listed)

    # reader 1: the engine's late-bound, per-access import_module read
    assert engines.R.listed_remote_specs is fake_listed, (
        "the engine reads a module object that a dotted monkeypatch never "
        "reaches — the patch landed on the forked half"
    )
    # reader 2: the view's already-bound class, whose globals carry the by-name import
    assert (
        bound_before.load_designed_agents.__globals__["listed_remote_specs"]
        is fake_listed
    ), "the class the view bound before discovery never saw the patch"


# --------------------------------------------------------------------------
# the parent attribute, in a process that never imported the package first
# --------------------------------------------------------------------------


_CHILD = textwrap.dedent(
    """
    import os, sys
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    os.environ.setdefault("DJANGO_DEBUG", "true")
    import django
    django.setup()

    ROUTER_PKG = "swarm.blueprints.agent_router"
    ROUTER = ROUTER_PKG + ".blueprint_agent_router"
    assert ROUTER not in sys.modules, "child pre-imported the module"

    from swarm.core.blueprint_discovery import discover_blueprints
    found = discover_blueprints(os.environ["SWARM_TEST_BP_DIR"])
    assert "agent_router" in found, sorted(found)

    # Publishing must not need — or trigger — an import of the package: an
    # eager parent import here is exactly the cycle
    # tests/core/test_agent_router_import_cycle.py pins.
    import importlib
    pkg = importlib.import_module(ROUTER_PKG)
    mod = sys.modules[ROUTER]
    assert getattr(pkg, "blueprint_agent_router", None) is mod, (
        "discovery did not publish the module on its parent package"
    )

    # the engine's late-bound read and the advertised class agree with it
    from swarm.blueprints.agent_router.engines import R
    assert R.AgentRouterBlueprint is mod.AgentRouterBlueprint
    assert found["agent_router"]["class_type"] is mod.AgentRouterBlueprint

    # and the documented lazy export still resolves through the same object
    from swarm.blueprints.agent_router import AgentRouterBlueprint
    assert AgentRouterBlueprint is mod.AgentRouterBlueprint
    print("OK")
    """
)


def test_fresh_interpreter_discovery_publishes_on_the_parent(blueprint_dir):
    """Discovery-first, nothing imported up front: one object, no cycle.

    A fresh interpreter, because that is the only order where discovery has to
    execute the file itself and the parent attribute can be missing entirely.
    Also pins that publishing on the parent does not re-trigger the
    ``agent_router`` import cycle.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        capture_output=True,
        text=True,
        timeout=300,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "HOME": __import__("os").environ.get("HOME", "/root"),
            "SWARM_TEST_BP_DIR": blueprint_dir,
            "SWARM_USER_BLUEPRINT_SANDBOX": "false",
        },
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


# --------------------------------------------------------------------------
# synthetic packages: the branches that must still execute
# --------------------------------------------------------------------------


@pytest.fixture
def synthetic_pkg(monkeypatch, tmp_path):
    """A real importable package tree, cleaned out of ``sys.modules`` after.

    Discovery derives the dotted name from the directory layout
    (``<pkg>/blueprints/<bp>/<bp>.py``), so a tmp tree *is* a real package and
    these assertions run against the real import machinery, not a mock.
    """
    created: list[str] = []

    def build(pkg_name: str, blueprint_name: str, source: str):
        monkeypatch.syspath_prepend(str(tmp_path))
        pkg = tmp_path / pkg_name
        bp_root = pkg / "blueprints"
        bp_dir = bp_root / blueprint_name
        bp_dir.mkdir(parents=True)
        for init in (
            pkg / "__init__.py",
            bp_root / "__init__.py",
            bp_dir / "__init__.py",
        ):
            init.write_text("", encoding="utf-8")
        parent = f"{pkg_name}.blueprints.{blueprint_name}"
        (bp_dir / f"{blueprint_name}.py").write_text(
            textwrap.dedent(source).replace("__PARENT__", parent), encoding="utf-8"
        )
        created.append(pkg_name)
        return bp_root, parent, f"{parent}.{blueprint_name}"

    yield build

    for name in created:
        for dotted in [k for k in sys.modules if k == name or k.startswith(f"{name}.")]:
            del sys.modules[dotted]


_SAFE_BP = """
    from swarm.core.blueprint_base import BlueprintBase

    class {cls}(BlueprintBase):
        metadata = {{"name": "{name}"}}
        async def run(self, messages, **kw):
            yield {{}}
"""


def test_discovery_executes_when_sys_modules_holds_another_file(synthetic_pkg):
    """Reuse is keyed on the file, so a same-named module from elsewhere must not win.

    A different ``__file__`` is different code, so discovery has to execute —
    and then it owns the dotted name outright: ``sys.modules`` *and* the parent
    attribute must both end up on the module it just ran, not on the decoy.
    """
    bp_root, parent_name, dotted = synthetic_pkg(
        "fork_decoy_pkg",
        "decoyed",
        _SAFE_BP.format(cls="RealBlueprint", name="decoyed"),
    )
    decoy_file = bp_root.parent / "decoyed_decoy.py"
    decoy_file.write_text("DECOY = True\n", encoding="utf-8")

    parent = importlib.import_module(parent_name)
    spec = importlib.util.spec_from_file_location(dotted, decoy_file)
    decoy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoy)
    sys.modules[dotted] = decoy
    parent.decoyed = decoy

    from swarm.core.blueprint_discovery import discover_blueprints

    found = discover_blueprints(str(bp_root), sandboxed=False)

    assert "decoyed" in found, sorted(found)
    assert found["decoyed"]["class_type"] is sys.modules[dotted].RealBlueprint
    assert sys.modules[dotted].__file__ == str(bp_root / "decoyed" / "decoyed.py")
    assert parent.decoyed is sys.modules[dotted], (
        "the parent package attribute still points at the superseded module"
    )


def test_discovery_executes_when_the_same_named_module_has_no_file(synthetic_pkg):
    """A dotted name occupied by something fileless is executed, not reused.

    Guards the ``__file__`` check: without it discovery would adopt a
    hand-planted module object and then find no BlueprintBase subclass in it,
    silently dropping the recipe.
    """
    bp_root, _parent_name, dotted = synthetic_pkg(
        "fileless_pkg",
        "fileless",
        _SAFE_BP.format(cls="FilelessBlueprint", name="fileless"),
    )
    sys.modules[dotted] = types.ModuleType(dotted)

    from swarm.core.blueprint_discovery import discover_blueprints

    found = discover_blueprints(str(bp_root), sandboxed=False)

    assert "fileless" in found, sorted(found)
    assert (
        found["fileless"]["class_type"] is sys.modules[dotted].FilelessBlueprint
    )


def test_discovery_from_a_blueprints_own_module_level_does_not_fork(synthetic_pkg):
    """Re-entrant discovery must still converge on one object per dotted name.

    A blueprint that calls ``discover_blueprints`` at its own module level finds
    its own half-built module in ``sys.modules``. Reuse hands it back as-is —
    what a cyclic import does — so the inner pass advertises nothing, the outer
    call advertises the recipe, and both names still point at one object
    afterwards.
    """
    bp_root, parent_name, dotted = synthetic_pkg(
        "reentrant_pkg",
        "reentrant",
        """
        import __PARENT__  # noqa: F401  (imports the parent, as agent_router does)
        from swarm.core.blueprint_base import BlueprintBase
        from swarm.core.blueprint_discovery import discover_blueprints
        from pathlib import Path

        INNER = discover_blueprints(str(Path(__file__).resolve().parents[1]), sandboxed=False)

        class ReentrantBlueprint(BlueprintBase):
            metadata = {"name": "reentrant"}
            async def run(self, messages, **kw):
                yield {}
        """,
    )

    from swarm.core.blueprint_discovery import discover_blueprints

    found = discover_blueprints(str(bp_root), sandboxed=False)

    assert "reentrant" in found, sorted(found)
    assert "reentrant" not in sys.modules[dotted].INNER, (
        "the inner pass must reuse the half-built module rather than re-execute it"
    )
    parent = importlib.import_module(parent_name)
    assert parent.reentrant is sys.modules[dotted]
    assert found["reentrant"]["class_type"] is sys.modules[dotted].ReentrantBlueprint

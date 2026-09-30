"""The ``agent_router`` import cycle that hid the whole recipe from discovery.

Live symptom: ``GET /v1/agents/`` advertised seats that every turn rejected with
``blueprint '<id>' was not found``, and the sweep blamed a missing package
because ``ls src/swarm/blueprints/`` showed no ``agent_router`` entry in the
*discovered* map.

Actual cause — a package ``__init__`` that eagerly re-exported the very module
discovery loads by file path::

    discover_blueprints()
      -> sys.modules["swarm.blueprints.agent_router.blueprint_agent_router"] = <empty>
      -> exec blueprint_agent_router.py:31
               from swarm.blueprints.agent_router.engines import RouterEnginesMixin
             -> Python imports the parent package
                  -> from ...blueprint_agent_router import AgentRouterBlueprint
                       -> sys.modules hit on the half-built module: unbound name
                          -> ImportError: cannot import name 'AgentRouterBlueprint'

Discovery caught it, logged, and dropped the id, so ``agent_router`` was never
registered — and every seat whose turn resolves through it (designer
personality / swarm / remote designs) had no recipe to run on.

The repro was **import-order dependent**: ``import swarm.urls`` before
discovery made ``swarm.blueprints.agent_router`` land in ``sys.modules``
first, which hides the cycle. So these tests pin the order-independent
property, in a fresh interpreter where nothing has imported the package yet.
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

PKG = "swarm.blueprints.agent_router"

# Runs in a fresh interpreter: this file is the only thing that may import
# ``swarm.blueprints.agent_router`` in-process, and it deliberately does not.
_CHILD = textwrap.dedent(
    """
    import os, sys
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    os.environ.setdefault("DJANGO_DEBUG", "true")
    import django
    django.setup()
    assert "swarm.blueprints.agent_router" not in sys.modules, "child pre-imported the package"

    from swarm.core.blueprint_discovery import discover_blueprints
    found = discover_blueprints(os.environ["SWARM_TEST_BP_DIR"])

    # 1. the recipe is registered, with the package never imported up front
    assert "agent_router" in found, sorted(found)
    assert found["agent_router"]["metadata"]["name"]

    # 2. and the lazy re-export still serves the documented import path
    from swarm.blueprints.agent_router import AgentRouterBlueprint
    assert AgentRouterBlueprint.__name__ == "AgentRouterBlueprint"
    print("OK")
    """
)


def _run_child(bp_dir: str) -> str:
    env = {
        "PATH": "/usr/bin:/bin:/usr/local/bin",
        "HOME": __import__("os").environ.get("HOME", "/root"),
        "SWARM_TEST_BP_DIR": bp_dir,
        "SWARM_USER_BLUEPRINT_SANDBOX": "false",
    }
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return proc.stdout


@pytest.fixture
def blueprint_dir() -> str:
    from django.conf import settings

    return str(settings.BLUEPRINT_DIRECTORY)


def test_discovery_registers_agent_router_with_no_prior_import(blueprint_dir):
    """The regression: discovery-first used to skip the package entirely.

    Reproduces the original bug (a fresh interpreter that has *not* imported
    ``swarm.blueprints.agent_router``) and asserts the recipe is discoverable
    now. A regression to an eager package export fails here with
    ``ImportError: cannot import name 'AgentRouterBlueprint'``.
    """
    out = _run_child(blueprint_dir)
    assert "OK" in out


def test_package_init_does_not_eagerly_import_the_discovery_module():
    """Structural pin for the root cause.

    The cycle is closed by a module-scope ``from ...blueprint_agent_router
    import ...`` in the package ``__init__``. A lazy PEP 562 export is the only
    shape that survives discovery's "register, then exec" loader, so assert —
    on the AST, not on text, so the explanation in the docstring cannot trip it
    — that no such import exists and that a module ``__getattr__`` does.
    """
    import ast
    from pathlib import Path

    import swarm.blueprints.agent_router as pkg

    tree = ast.parse(Path(pkg.__file__).read_text(encoding="utf-8"))
    offenders = [
        node
        for node in tree.body  # module scope only — a lazy body may import
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and "blueprint_agent_router" in ast.dump(node)
    ]
    assert not offenders, (
        "eager re-import in agent_router/__init__.py re-creates the discovery cycle"
    )
    assert any(
        isinstance(node, ast.FunctionDef) and node.name == "__getattr__"
        for node in tree.body
    ), "agent_router/__init__.py must export AgentRouterBlueprint lazily (PEP 562)"


def test_importing_the_package_does_not_import_the_blueprint_module():
    """Runtime half of the structural pin, in a fresh interpreter."""
    proc = subprocess.run(
        [
            sys.executable,
            "-c",
            textwrap.dedent(
                """
                import os, sys
                os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
                os.environ.setdefault("DJANGO_DEBUG", "true")
                import django
                django.setup()
                import swarm.blueprints.agent_router as pkg
                assert "swarm.blueprints.agent_router.blueprint_agent_router" not in sys.modules
                assert pkg.AgentRouterBlueprint.__name__ == "AgentRouterBlueprint"
                assert "swarm.blueprints.agent_router.blueprint_agent_router" in sys.modules
                print("OK")
                """
            ),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_a_blueprint_that_fails_to_import_is_excluded_and_reported(tmp_path, caplog):
    """The discovery half of the contract: fail loudly, with the id and why.

    A package whose ``__init__`` eagerly imports its own main module is the
    exact shape that hid ``agent_router``. Whatever the cause, discovery must
    (a) not advertise the id and (b) name the id, the module and the reason in
    an ERROR record — so "the roster shows a seat that 404s" traces to a named
    blueprint instead of reading as a silent skip.
    """
    from swarm.core.blueprint_discovery import discover_blueprints

    pkg = tmp_path / "halfinit"
    pkg.mkdir()
    (pkg / "__init__.py").write_text(
        "from halfinit_pkg_import_here import Nope  # noqa: F401\n", encoding="utf-8"
    )
    (pkg / "halfinit.py").write_text(
        "raise RuntimeError('boom during import')\n", encoding="utf-8"
    )

    with caplog.at_level("ERROR", logger="swarm.core.blueprint_discovery"):
        found = discover_blueprints(str(tmp_path))

    assert "halfinit" not in found
    messages = "\n".join(r.getMessage() for r in caplog.records)
    assert "halfinit" in messages, messages
    assert "is not advertised" in messages, messages
    assert "boom during import" in messages, messages

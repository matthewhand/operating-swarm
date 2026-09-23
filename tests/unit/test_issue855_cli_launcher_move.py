"""
#855 slice 2 — swarm_cli.py launcher/session helper extraction pins.

The module-level helpers moved verbatim to ``swarm/cli/launcher.py``
(swarm_cli.py keeps the Typer commands and the kernel, same doctrine as
the #855 slice-1 ``swarm/chat/helpers.py`` move and the #1000 remote_impls
move). These pins enforce the move's three invariants:

1. **Resolution** — swarm_cli rebinds every moved helper name eagerly, so
   command bodies and external ``from swarm.core.swarm_cli import <name>``
   keep working.
2. **Patch-safety** — the moved bodies resolve sibling helpers, ``paths``,
   the ``_shutil`` alias, and ``__file__`` through the late-bound ``R``
   handle, so ``patch("swarm.core.swarm_cli.<name>")`` keeps landing even
   when the caller lives in launcher.py.
3. **Coverage** — every function defined in launcher.py is re-exported on
   swarm_cli; a helper added to the moved span later must be re-bound, never
   silently dropped.
"""

from pathlib import Path

import swarm.cli.launcher as cli_launcher
import swarm.core.swarm_cli as swarm_cli

REPO = Path(__file__).resolve().parents[2]
LAUNCHER = REPO / "src" / "swarm" / "cli" / "launcher.py"


def test_all_moved_helper_names_rebound_on_swarm_cli():
    """Every function defined in launcher.py rebinds on swarm_cli."""
    moved = {
        name
        for name, obj in vars(cli_launcher).items()
        if callable(obj)
        and getattr(obj, "__module__", "") == "swarm.cli.launcher"
        and not name.startswith("__")
    }
    # The late-bound R handle (and its class) are module machinery, not moved
    # helpers.
    moved.discard("R")
    moved.discard("_CliRef")
    assert moved, "launcher.py must define the moved helpers"
    for name in moved:
        assert getattr(swarm_cli, name, None) is getattr(cli_launcher, name), (
            f"swarm_cli.{name} must rebind swarm.cli.launcher.{name}"
        )


def test_moved_bodies_route_siblings_through_r():
    """Moved bodies must resolve sibling helpers/paths through R.

    A bare reference would bind at import time and silently break
    ``patch("swarm.core.swarm_cli.<name>")`` for calls originating here.
    """
    text = LAUNCHER.read_text(encoding="utf-8")
    assert "R = _CliRef()" in text
    # Sibling-helper call sites are R-routed (e.g. _require_safe_… calls
    # _safe_blueprint_segment through the handle), so patches on swarm_cli
    # reach them.
    assert "R._safe_blueprint_segment" in text
    assert "R._require_safe_blueprint_segment" in text
    # The kernel ``paths`` module is R-routed too.
    bare = [line for line in text.splitlines() if "R.paths" not in line and line.strip().startswith("paths.")]
    assert not bare, bare


def test_patch_target_on_swarm_cli_reaches_moved_caller():
    """The #855 patch contract: patch on swarm_cli, call from launcher."""
    from unittest.mock import patch

    # _require_safe_blueprint_segment routes its sibling call through R, so a
    # patch of the callee on swarm_cli is observed by the moved caller.
    with patch.object(swarm_cli, "_safe_blueprint_segment", return_value="ok") as spy:
        assert cli_launcher._require_safe_blueprint_segment("fine") == "ok"
    assert spy.called

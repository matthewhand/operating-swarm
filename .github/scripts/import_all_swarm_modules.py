#!/usr/bin/env python
"""Import every ``swarm`` module and report what is missing.

The barebones dependency split means a module-level import of an optional
package resolves fine in CI (``--all-extras``) and fails only in a clean
container. This walks the whole package so that gap has a gate. See #1334.

Run it against whichever profile you just installed:

    uv pip install .            # barebones core
    uv pip install '.[deploy]'  # what the Dockerfile does

Exits non-zero and prints one line per failure. Deliberately dependency-free so
it runs in a barebones venv before anything else is importable.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback
from pathlib import Path

#: Modules that legitimately cannot be imported without an extra, each with the
#: reason. Keep this list short and justified -- it is the only escape hatch, so
#: an entry here means the barebones install genuinely does not need the module.
#: Prefer fixing a module (lazy import behind a feature gate) over adding to it.
#:
#: `swarm.tui.app` imports `textual` at module scope, which is correct for a TUI
#: module. It is only ever reached through `swarm.tui.cli`, which probes for
#: `textual` and imports `app` only after the probe passes -- so the core install
#: never touches it. Verified: `uv run python -c "import swarm.tui.cli"` succeeds
#: barebones.
OPTIONAL_MODULES: dict[str, str] = {
    "swarm.tui.app": "needs the `tui` extra (textual); reached only via swarm.tui.cli, which probes first",
}


def _iter_module_names() -> list[str]:
    """Every module that ships inside the installed ``swarm`` package.

    Derived from the **filesystem**, not ``pkgutil.walk_packages``. That was a
    real bug in the first version of this gate: ``pkgutil`` only recurses into
    regular packages, and 78 of the shipped modules live under
    ``swarm/blueprints/*/`` which have no ``__init__.py``. The walk reported 404
    modules and silently covered none of the blueprints -- so it did not catch
    the ``pytz`` bug this job exists for, when that was its whole purpose.
    """
    import swarm

    root = Path(swarm.__file__).resolve().parent
    names: set[str] = set()
    for path in root.rglob("*.py"):
        parts = path.relative_to(root).with_suffix("").parts
        if any(p == "__pycache__" for p in parts):
            continue
        if parts[-1] == "__init__":
            parts = parts[:-1]
            if not parts:
                continue
            names.add(".".join(("swarm", *parts)))
        else:
            names.add(".".join(("swarm", *parts)))
    return sorted(names)


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swarm.settings")
    os.environ.setdefault("DJANGO_DEBUG", "true")
    os.environ.setdefault("DJANGO_SECRET_KEY", "ci-only-not-a-secret")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    # Never pull the operator's real ~/.config/swarm/.env into CI.
    os.environ.setdefault("SWARM_SKIP_DOTENV", "1")

    import django

    django.setup()

    failures: list[tuple[str, str]] = []

    names = _iter_module_names()
    for name in names:
        if name in OPTIONAL_MODULES:
            continue
        try:
            importlib.import_module(name)
        except KeyboardInterrupt:
            raise
        except BaseException as exc:  # noqa: BLE001
            # BaseException, not Exception: a CLI module that calls sys.exit()
            # at import scope raises SystemExit and would otherwise terminate
            # the whole walk before it reports anything. (src/swarm/desktop/cli
            # does exactly this -- printing its REQ-883B notice and exiting.)
            # That is itself a finding: such a module makes the walk
            # non-deterministic, so it is reported rather than silently fatal.
            if isinstance(exc, SystemExit):
                failures.append(
                    (name, f"SystemExit({exc.code}) raised at import scope")
                )
            else:
                failures.append((name, f"{type(exc).__name__}: {exc}"))

    # REQUIRED_MODULES only. EXTRA_MARKERS names the modules that prove an
    # *extra* is installed, so on a barebones profile they are absent by
    # definition -- checking them here would report every extra as a failure.
    # REQUIRED_MODULES is the opposite: those must import on every profile.
    try:
        from swarm.core.build_info import REQUIRED_MODULES, build_profile

        for name, module in sorted(REQUIRED_MODULES.items()):
            try:
                importlib.import_module(module)
            except Exception as exc:  # noqa: BLE001
                failures.append(
                    (f"REQUIRED_MODULES[{name!r}] = {module!r}", f"{type(exc).__name__}: {exc}")
                )
        profile = build_profile()
        print(
            f"profile: extras={profile['extras'] or 'none'} "
            f"missing_required={profile['missing_required'] or 'none'}"
        )
        if profile["missing_required"]:
            failures.append(
                ("build_profile", f"missing_required={profile['missing_required']}")
            )
    except Exception:
        failures.append(("swarm.core.build_info", traceback.format_exc(limit=3)))

    print(f"walked {len(names)} swarm modules")

    if failures:
        print(f"\n{len(failures)} import failure(s):\n", file=sys.stderr)
        for name, err in failures:
            print(f"  FAIL {name}: {err}", file=sys.stderr)
        print(
            "\nA module-level import of an extra-only package resolves under "
            "`--all-extras` and breaks in the container. Make the import lazy "
            "behind a feature gate, or declare the package in base "
            "`dependencies`. See #1334.",
            file=sys.stderr,
        )
        return 1

    print("all swarm modules import cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

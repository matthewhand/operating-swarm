from swarm.desktop.cli import main

# Guarded: `pkgutil.walk_packages` imports every submodule, so an unguarded
# `raise SystemExit(main())` terminated the barebones import gate (see #1334)
# before it could report anything. As a real __main__ the name is still
# "__main__" when invoked via `python -m swarm.desktop`.
if __name__ == "__main__":
    raise SystemExit(main())

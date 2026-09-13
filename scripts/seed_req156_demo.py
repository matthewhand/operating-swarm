#!/usr/bin/env python3
"""Additive Demo roster seed for REQ-156 / REQ-135 (no secrets).

Writes labeled ``demo-*`` team rosters into ``team_rosters.json``. Does not
touch ``teams.json``, ``.env``, or day-to-day agents.

Usage (engineer on dev-worker-gpu / preview after merge)::

    uv run python scripts/seed_demo_agents.py --dry-run
    uv run python scripts/seed_demo_agents.py
    uv run python scripts/seed_demo_agents.py --config-dir /path/to/swarm --reset

See docs/SHOWOFF_DEMO_AGENTS.md and
docs/examples/openai-agents-handoff-graphs/README.md (:8001 seed).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from swarm.core.handoff_graph import DEMO_ROSTER_IDS, seed_demo_rosters  # noqa: E402
from swarm.core.paths import get_user_config_dir_for_swarm  # noqa: E402


def _dest(config_dir: str | None) -> Path:
    if config_dir:
        return Path(config_dir).expanduser() / "team_rosters.json"
    return get_user_config_dir_for_swarm() / "team_rosters.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config-dir",
        help="Directory that holds team_rosters.json (default: XDG swarm config).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print ids that would be written; do not touch disk.",
    )
    parser.add_argument(
        "--overwrite",
        "--reset",
        action="store_true",
        dest="overwrite",
        help="Replace existing demo-* ids (reset demo agents). Never deletes non-demo rosters.",
    )
    args = parser.parse_args(argv)
    dest = _dest(args.config_dir)
    merged = seed_demo_rosters(dest, overwrite=args.overwrite, dry_run=args.dry_run)
    demo = [rid for rid in DEMO_ROSTER_IDS if rid in merged]
    mode = "dry-run" if args.dry_run else "wrote"
    print(f"{mode}: {dest}")
    print("demo roster ids: " + ", ".join(demo))
    print("no secrets written; CLI/remote members stay placeholders")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

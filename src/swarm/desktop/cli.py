"""``swarm-desktop`` — REQ-883 Phase 0 scaffold.

``--print-plan`` dumps the loopback boot contract for CI. The pywebview
window (REQ-883B) is not wired: a launch attempt exits 2 with an install
hint, matching ``swarm-cli tui`` before Wave 1.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from swarm.desktop.boot import PRODUCT_NAME, desktop_profile_dir, print_plan
from swarm.desktop.packaging import PRIMARY_FREEZE, PRIMARY_SHELL


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="swarm-desktop",
        description=(
            f"{PRODUCT_NAME} desktop launcher (REQ-883). "
            "Loopback ASGI + native webview; no Docker / Python / Node for the "
            "eventual frozen app. REQ-883A is this --print-plan boot contract; "
            "the window is REQ-883B."
        ),
    )
    parser.add_argument(
        "--print-plan",
        action="store_true",
        help="Dump the loopback boot plan as JSON (CI / source lock). "
        "Does not start uvicorn or a window.",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Override SWARM_USER_DATA_DIR for this invocation.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Preferred loopback port (default: 8000, else ephemeral).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    profile = Path(args.profile).expanduser() if args.profile else desktop_profile_dir()

    if args.print_plan:
        plan = print_plan(profile=profile, port=args.port)
        sys.stdout.write(json.dumps(plan, indent=2) + "\n")
        return 0

    sys.stderr.write(
        f"{PRODUCT_NAME} desktop window is REQ-883B ({PRIMARY_SHELL} + "
        f"{PRIMARY_FREEZE}). Use --print-plan for the loopback boot contract. "
        "Install the optional extra later with: pip install -e '.[desktop]'\n"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

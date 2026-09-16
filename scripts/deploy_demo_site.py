#!/usr/bin/env python3
"""Operator-gated public demo deploy (REQ-882 / #279).

The mocked site ships in-repo. Fly.io / Pages publish runs only when the
operator has credentials. Missing credentials is a successful skip, not a
failure — CI and contributors without Fly tokens stay green.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FLY_TOML = REPO / "fly.demo.toml"
FRONTEND = REPO / "webui" / "frontend"


def _truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "y", "on"}


def fly_credentials_present() -> bool:
    if os.getenv("FLY_API_TOKEN", "").strip():
        return True
    flyctl = shutil.which("flyctl") or shutil.which("fly")
    if not flyctl:
        return False
    try:
        proc = subprocess.run(
            [flyctl, "auth", "whoami"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and bool((proc.stdout or "").strip())


def pages_credentials_present() -> bool:
    return bool(os.getenv("CLOUDFLARE_API_TOKEN", "").strip()) or _truthy(
        "GITHUB_PAGES_DEPLOY"
    )


def skip(reason: str) -> int:
    print(f"SKIP: {reason}")
    print("Mocked demo site is in-repo (VITE_DEMO_MODE / SWARM_DEMO_MODE).")
    return 0


def run(argv: list[str], cwd: Path | None = None) -> int:
    print("+", " ".join(argv))
    proc = subprocess.run(argv, cwd=cwd or REPO, check=False)
    return proc.returncode


def deploy_fly() -> int:
    flyctl = shutil.which("flyctl") or shutil.which("fly")
    if not flyctl:
        return skip("flyctl not on PATH")
    if not FLY_TOML.is_file():
        return skip(f"{FLY_TOML.name} missing")
    cmd = [flyctl, "deploy", "--config", str(FLY_TOML), "--remote-only"]
    if os.getenv("FLY_API_TOKEN", "").strip():
        cmd.extend(["--access-token", os.environ["FLY_API_TOKEN"]])
    return run(cmd)


def build_static() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("ERROR: npm not found", file=sys.stderr)
        return 1
    install = run(
        [npm, "ci", "--no-audit", "--no-fund", "--legacy-peer-deps"],
        cwd=FRONTEND,
    )
    if install != 0:
        return install
    return run([npm, "run", "build:demo"], cwd=FRONTEND)


def deploy_static() -> int:
    built = build_static()
    if built != 0:
        return built
    wrangler = shutil.which("wrangler")
    if wrangler and os.getenv("CLOUDFLARE_API_TOKEN", "").strip():
        project = os.getenv("CLOUDFLARE_PAGES_PROJECT", "open-swarm-demo")
        return run(
            [wrangler, "pages", "deploy", str(FRONTEND / "dist"), "--project-name", project],
            cwd=FRONTEND,
        )
    if _truthy("GITHUB_PAGES_DEPLOY"):
        print("Static dist is at webui/frontend/dist — publish with the operator Pages workflow.")
        return 0
    return skip("no Cloudflare / GitHub Pages credentials")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        choices=("fly", "static", "auto"),
        default="auto",
        help="fly = Fly.io app; static = Pages CDN; auto = fly if authed else static",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print credential state and exit without deploying",
    )
    args = parser.parse_args(argv)

    fly_ok = fly_credentials_present()
    pages_ok = pages_credentials_present()
    if args.dry_run:
        print(f"fly_credentials={fly_ok} pages_credentials={pages_ok}")
        return 0

    target = args.target
    if target == "auto":
        if fly_ok:
            target = "fly"
        elif pages_ok:
            target = "static"
        else:
            return skip("no Fly.io or Pages credentials (operator-gated)")

    if target == "fly":
        if not fly_ok:
            return skip("FLY_API_TOKEN unset and flyctl auth whoami failed")
        return deploy_fly()
    if not pages_ok:
        return skip("static hosting credentials missing")
    return deploy_static()


if __name__ == "__main__":
    raise SystemExit(main())

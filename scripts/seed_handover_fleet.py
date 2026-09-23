#!/usr/bin/env python3
"""Seed the handover mirror fleet into router_designs.

Reads ``scripts/handover_fleet_manifest.json`` and upserts every seat as a
designed agent via ``swarm.core.router_designs.upsert_design`` so the same
validation as ``POST /v1/agents/designs/`` applies.

kind=cli seats validate against the CLI catalog **plus** the host's
``cli_agents`` config overlay (the runtime prefers that overlay, and the
catalog on a deployed tip may be newer than this worktree's). If the
manifest's CLI is neither cataloged nor configured, the seat falls back to
``fallback_kind`` (default ``personality``) so the charter stays seatable —
the handover's prove-then-operate doctrine without faking CLI capability.

Usage:
    uv run python scripts/seed_handover_fleet.py [--dry-run] [--manifest PATH]

Existing design seats are never downgraded: upsert replaces the record with
the same agent_id (mirror ids are ``*-mirror`` and do not collide).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MANIFEST = ROOT / "scripts" / "handover_fleet_manifest.json"


def load_manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    seats = data.get("seats")
    if not isinstance(seats, list) or not seats:
        raise SystemExit(f"manifest {path} has no seats")
    return seats


def build_payload(seat: dict, cli_available: bool) -> dict:
    """Design payload for a seat, honoring the cli→personality fallback."""
    fallback = str(seat.get("fallback_kind") or "personality").strip().lower()
    base = {
        "name": seat.get("name") or seat["agent_id"],
        "agent_id": seat["agent_id"],
        "specialty": seat.get("specialty") or "",
        "description": seat.get("description") or "",
        "instructions": seat.get("instructions") or "",
        "icon": seat.get("icon") or "🛰️",
        "color": seat.get("color") or "#0ea5e9",
    }
    if cli_available:
        return {**base, "kind": "cli", "cli": seat["cli"]}
    if not fallback:
        raise SystemExit(
            f"seat {seat['agent_id']}: cli {seat['cli']!r} unavailable and no fallback_kind"
        )
    note = (
        f"[handover mirror fallback: CLI '{seat['cli']}' is not locally configured; "
        f"charter runs as {fallback} until it is added to cli_agents]"
    )
    return {
        **base,
        "kind": fallback,
        "description": f"{base['description']} {note}".strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print payloads without writing designs",
    )
    args = parser.parse_args()

    from swarm.core.cli_catalog import catalog_entry
    from swarm.core.paths import get_user_config_dir_for_swarm
    from swarm.core.router_designs import load_designs, upsert_design

    try:
        cfg_path = get_user_config_dir_for_swarm() / "swarm_config.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.is_file() else {}
        configured = set((cfg.get("cli_agents") or {}).keys())
    except Exception:
        configured = set()

    def cli_seatable(name: str) -> bool:
        return bool(catalog_entry(name)) or name in configured

    before = {a.get("agent_id") for a in load_designs()}
    seeded: list[tuple[str, str, str]] = []

    for seat in load_manifest(args.manifest):
        agent_id = seat.get("agent_id")
        if not agent_id or not seat.get("instructions"):
            raise SystemExit(f"seat missing agent_id/instructions: {seat!r}")
        cli_ok = cli_seatable(str(seat.get("cli") or ""))
        payload = build_payload(seat, cli_ok)
        if args.dry_run:
            print(f"[dry-run] {agent_id}: kind={payload['kind']}"
                  f"{' cli=' + payload['cli'] if 'cli' in payload else ''}")
            continue
        try:
            spec = upsert_design(payload)
        except ValueError:
            # This worktree's catalog may be older than the deployed tip's
            # (e.g. omp exists in cli_agents + tip catalog but not here).
            # Keep the charter seatable via the fallback kind, honestly noted.
            if "cli" not in payload:
                raise
            payload = build_payload(seat, cli_available=False)
            spec = upsert_design(payload)
            print(f"[seed] {agent_id}: catalog rejected cli={seat['cli']!r} here — "
                  f"fell back to {spec['kind']} (rerun on tip catalog to upgrade)")
        status = "updated" if agent_id in before else "created"
        seeded.append((agent_id, spec["kind"], status))
        print(f"[seed] {agent_id}: kind={spec['kind']} {status}")

    if args.dry_run:
        return 0
    print(f"\nseeded {len(seeded)} seats "
          f"(cli={sum(1 for _, k, _ in seeded if k == 'cli')}, "
          f"fallback={sum(1 for _, k, _ in seeded if k != 'cli')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

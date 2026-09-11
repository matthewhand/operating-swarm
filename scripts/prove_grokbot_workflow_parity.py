#!/usr/bin/env python3
"""Issue #162 prove: named seats → named tools → assigned project.

Deterministic (no LLM, no secrets, no paid providers). Creates three
fleet-pattern seats, lists them, invokes each named tool against its
bound workdir, and checks software_dev as_tool aliases match seat names.

Re-run::

    SWARM_TEST_MODE=1 uv run python scripts/prove_grokbot_workflow_parity.py
    uv run pytest tests/core/test_fleet_seats.py tests/blueprints/test_software_dev.py -q
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SEATS = (
    ("prove162-grok", "cos"),
    ("prove162-pi", "engineer"),
    ("prove162-opencode", "skeptic"),
)


def _banner(line: str) -> None:
    print(line, flush=True)


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    os.environ.setdefault("SWARM_TEST_MODE", "1")
    # Never inherit operator tokens into prove logs.
    for key in (
        "API_AUTH_TOKEN",
        "API_AUTH_TOKENS",
        "SWARM_API_KEY",
        "SWARM_API_KEYS",
        "OPENAI_API_KEY",
    ):
        os.environ.pop(key, None)

    from swarm.blueprints.software_dev.blueprint_software_dev import SoftwareDevBlueprint
    from swarm.blueprints.software_dev.roles import SEAT_COS, SEAT_ENGINEER, SEAT_SKEPTIC
    from swarm.core.agent_settings import reset_agent_settings_cache
    from swarm.core.fleet_seats import (
        create_seat,
        invoke_named_tool,
        list_seats,
        reset_fleet_seats_cache,
    )

    with tempfile.TemporaryDirectory(prefix="prove162-") as raw:
        home = Path(raw)
        os.environ["SWARM_FLEET_SEATS_PATH"] = str(home / "fleet_seats.json")
        os.environ["SWARM_AGENT_SETTINGS_PATH"] = str(home / "agent_settings.json")
        reset_fleet_seats_cache()
        reset_agent_settings_cache()

        _banner("prove_grokbot_workflow_parity: create/list/invoke 3 seats")
        created = []
        for ident, role in SEATS:
            row = create_seat(ident, home / ident, role=role)
            created.append(row)
            _banner(
                f"  CREATE {row['agent_id']} tool={row['tool_name']} "
                f"role={row['role']} workdir={row['workdir']}"
            )

        listed = list_seats()
        if len(listed) < 3:
            _banner(f"FAIL list: expected >=3 seats, got {len(listed)}")
            return 1
        for row in listed:
            if row["tool_name"] != row["agent_id"]:
                _banner(
                    f"FAIL named tool: {row['agent_id']} tool={row['tool_name']}"
                )
                return 1
            if not row["workdir"]:
                _banner(f"FAIL unbound project: {row['agent_id']}")
                return 1
        _banner(f"  LIST {len(listed)} seats tool_name==agent_id workdir bound")

        evidence = []
        for row in created:
            out = invoke_named_tool(row["agent_id"])
            if not out.get("ok"):
                _banner(f"FAIL invoke {row['agent_id']}: {out}")
                return 1
            marker = Path(row["workdir"]) / "_fleet_seat_pass.txt"
            if not marker.is_file():
                _banner(f"FAIL missing marker in {row['workdir']}")
                return 1
            _banner(f"  INVOKE {out['tool_name']} -> {out['evidence']}")
            evidence.append(out["evidence"])

        stolen = invoke_named_tool(
            "prove162-pi",
            path="../prove162-grok/stolen.txt",
            content="nope",
        )
        if stolen.get("ok") or (home / "prove162-grok" / "stolen.txt").exists():
            _banner("FAIL confinement: pi wrote into grok project")
            return 1
        _banner("  CONFINE pi cannot write into grok workdir")

        bp = SoftwareDevBlueprint()
        bp.set_params({"workdir": str(home / "software_dev")})
        agents = bp._build_agents()
        if not {SEAT_COS, SEAT_ENGINEER, SEAT_SKEPTIC} <= set(agents):
            _banner("FAIL software_dev seats missing")
            return 1
        names = []
        for tool in getattr(agents[SEAT_COS], "tools", []) or []:
            names.append(str(getattr(tool, "name", None) or getattr(tool, "__name__", "")))
        joined = " ".join(names)
        for required in ("consult_engineer", "engineer", "consult_skeptic", "skeptic"):
            if required not in joined:
                _banner(f"FAIL software_dev as_tool missing {required}: {joined}")
                return 1
        _banner(f"  SOFTWARE_DEV as_tool aliases: {joined}")

        _banner("PASS 3 named seats invoked matching tools against assigned projects")
        for line in evidence:
            _banner(f"  {line}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

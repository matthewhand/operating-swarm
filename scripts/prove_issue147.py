#!/usr/bin/env python3
"""Issue #147 prove: CLI-default discovered host CLIs + software_dev as_tool/handoff.

Programmatic path (always; SWARM_TEST_MODE; no secrets; no Neon):

  1. ``cli_agents_catalog_payload`` start set is PATH-discovered catalog CLIs.
     Fake names (echo/dummy/mock/…) must not leak. Absent catalog names (pi)
     stay absent.
  2. ``software_dev`` seats CoS + engineer + skeptic with **both** as_tool
     (consult_engineer / consult_skeptic) **and** handoff(engineer, skeptic).
  3. pytest of the tests that lock those contracts.

Live path (skip if the host/server/pi is missing):

  GET {SWARM_PROOF_BASE_URL}/v1/cli-agents/ — discovered-only start set.
  pi skipped when not on PATH / not in ``discovered``.

Prints PASS/FAIL lines. Exit 0 iff the programmatic path PASSes.

Re-run::

    SWARM_TEST_MODE=1 uv run python scripts/prove_issue147.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE_CLIS = ("echo", "fake", "dummy", "mock", "testcli", "placeholder")
SECRET_ENV = (
    "API_AUTH_TOKEN",
    "API_AUTH_TOKENS",
    "SWARM_API_KEY",
    "SWARM_API_KEYS",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "XAI_API_KEY",
)
PYTEST_TARGETS = [
    "tests/core/test_cli_first_defaults.py",
    "tests/core/test_req157_cli_agents.py",
    "tests/api/test_cli_agents_opt_in.py",
    "tests/cli/test_cli_agents_command.py",
    "tests/blueprints/test_software_dev.py",
    "tests/blueprints/test_sdlc_handoff.py",
    "tests/api/test_issue136_kind_chat_e2e.py::test_kind_turn_software_dev_handoff_as_tool",
]
AS_TOOL_REQUIRED = (
    "consult_engineer",
    "engineer",
    "consult_skeptic",
    "skeptic",
)


def _banner(line: str) -> None:
    print(line, flush=True)


def _scrub_env(env: dict[str, str]) -> dict[str, str]:
    cleaned = dict(env)
    for key in SECRET_ENV:
        cleaned.pop(key, None)
    return cleaned


def _tool_names(agent) -> list[str]:
    names: list[str] = []
    for tool in getattr(agent, "tools", []) or []:
        names.append(str(getattr(tool, "name", None) or getattr(tool, "__name__", "") or ""))
    return names


def _handoff_names(agent) -> list[str]:
    names: list[str] = []
    for item in getattr(agent, "handoffs", None) or []:
        name = getattr(item, "agent_name", None)
        if not name:
            inner = getattr(item, "agent", None)
            name = getattr(inner, "name", None)
        if name:
            names.append(str(name))
    return names


def _start_set(payload: dict) -> set[str]:
    names = set(payload.get("discovered") or [])
    names.update(payload.get("installed") or [])
    names.update((payload.get("suggestions") or {}).keys())
    for row in payload.get("rail") or []:
        if isinstance(row, dict) and row.get("cli"):
            names.add(str(row["cli"]))
    return names


def check_discovered_only() -> tuple[bool, str]:
    from swarm.core import cli_catalog

    catalog = set(cli_catalog.catalog_names())
    fake_in_catalog = sorted(catalog & set(FAKE_CLIS))
    if fake_in_catalog:
        return False, f"catalog contains fake CLIs: {fake_in_catalog}"

    payload = cli_catalog.cli_agents_catalog_payload({})
    discovered = list(payload.get("discovered") or [])
    leaked = sorted(_start_set(payload) & set(FAKE_CLIS))
    if leaked:
        return False, f"fake CLIs leaked into start set: {leaked}"
    extra = [n for n in discovered if n not in catalog]
    if extra:
        return False, f"discovered includes non-catalog names: {extra}"
    pi_on_path = cli_catalog.which_cli("pi") is not None
    if not pi_on_path and "pi" in discovered:
        return False, "pi absent on PATH but listed in discovered"
    return True, (
        f"discovered={discovered} known={len(payload.get('known') or [])} "
        f"configured={payload.get('configured') or []} "
        f"pi={'present' if pi_on_path else 'absent-skip'}"
    )


def check_software_dev_wiring() -> tuple[bool, str]:
    from swarm.blueprints.software_dev.blueprint_software_dev import SoftwareDevBlueprint
    from swarm.blueprints.software_dev.roles import SEAT_COS, SEAT_ENGINEER, SEAT_SKEPTIC

    bp = SoftwareDevBlueprint(config={"llm": {}, "software_dev": {"talk_to": "cos"}})
    agents = bp._build_agents()
    missing = [s for s in (SEAT_COS, SEAT_ENGINEER, SEAT_SKEPTIC) if s not in agents]
    if missing:
        return False, f"software_dev seats missing: {missing}"
    cos = agents[SEAT_COS]
    tools = _tool_names(cos)
    joined = " ".join(tools)
    missing_tools = [name for name in AS_TOOL_REQUIRED if name not in joined]
    if missing_tools:
        return False, f"as_tool missing {missing_tools}: {joined}"
    handoffs = _handoff_names(cos)
    missing_h = [name for name in ("engineer", "skeptic") if name not in handoffs]
    if missing_h:
        return False, f"handoff missing {missing_h}: {handoffs}"
    return True, f"as_tool={tools} handoffs={handoffs}"


def run_pytest(env: dict[str, str]) -> tuple[bool, str]:
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        *PYTEST_TARGETS,
        "-q",
        "--tb=line",
        "--no-cov",
    ]
    _banner("  pytest: " + " ".join(PYTEST_TARGETS))
    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
    tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-400:]
    for needle in ("sk-", "ghp_", "neon.tech"):
        if needle in tail:
            tail = tail.replace(needle, "[redacted]")
    if proc.returncode != 0:
        return False, f"pytest exit {proc.returncode}\n{tail.strip()}"
    summary = ""
    for line in reversed((proc.stdout or "").splitlines()):
        if "passed" in line or "failed" in line:
            summary = line.strip()
            break
    return True, summary or "pytest ok"


def check_live_cli_agents(env: dict[str, str]) -> tuple[str, str]:
    """Return (PASS|FAIL|SKIP, detail). Never prints secrets."""
    if env.get("SWARM_SKIP_LIVE") == "1":
        return "SKIP", "SWARM_SKIP_LIVE=1"
    base = (env.get("SWARM_PROOF_BASE_URL") or "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/v1/cli-agents/"
    req = urllib.request.Request(url, method="GET")
    token = env.get("SWARM_PROOF_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return "SKIP", f"HTTP {exc.code} from {url}"
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return "SKIP", f"no server at {url} ({type(exc).__name__})"
    if status != 200:
        return "FAIL", f"HTTP {status} from {url}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return "FAIL", "non-JSON body"
    if not isinstance(payload, dict):
        return "FAIL", "unexpected payload type"
    discovered = list(payload.get("discovered") or [])
    leaked = sorted(set(discovered) & set(FAKE_CLIS))
    if leaked:
        return "FAIL", f"fake CLIs in live discovered: {leaked}"
    configured = list(payload.get("configured") or [])
    return "PASS", f"discovered={discovered} configured={configured}"


def check_live_pi() -> tuple[str, str]:
    from swarm.core import cli_catalog

    if cli_catalog.which_cli("pi") is None:
        return "SKIP", "pi not on PATH"
    discovered = cli_catalog.discover_host_clis()
    if "pi" not in discovered:
        return "SKIP", "pi binary present but not a catalog discover hit"
    return "PASS", "pi in discovered"


def main() -> int:
    os.environ.setdefault("SWARM_TEST_MODE", "1")
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    env = _scrub_env(os.environ)
    for key, value in env.items():
        os.environ[key] = value
    for key in SECRET_ENV:
        os.environ.pop(key, None)
    sys.path.insert(0, str(ROOT / "src"))

    _banner("prove_issue147")
    _banner("PROGRAMMATIC")

    ok_disc, detail_disc = check_discovered_only()
    _banner(f"  discovered-only: {'PASS' if ok_disc else 'FAIL'} ({detail_disc})")

    ok_sd, detail_sd = check_software_dev_wiring()
    _banner(f"  software_dev as_tool+handoff: {'PASS' if ok_sd else 'FAIL'} ({detail_sd})")

    ok_py, detail_py = run_pytest(env)
    _banner(f"  pytest: {'PASS' if ok_py else 'FAIL'} ({detail_py})")

    programmatic_ok = ok_disc and ok_sd and ok_py

    _banner("LIVE")
    live_status, live_detail = check_live_cli_agents(env)
    _banner(f"  /v1/cli-agents: {live_status} ({live_detail})")
    pi_status, pi_detail = check_live_pi()
    _banner(f"  pi: {pi_status} ({pi_detail})")

    live_fail = live_status == "FAIL"
    if programmatic_ok and not live_fail:
        remaining = []
        if live_status == "SKIP":
            remaining.append("live /v1/cli-agents on remote-host")
        if pi_status == "SKIP":
            remaining.append("live pi (absent)")
        extra = f"; remaining host prove: {', '.join(remaining)}" if remaining else ""
        _banner(f"OVERALL: PASS (programmatic) live={live_status}{extra}")
        return 0
    if not programmatic_ok:
        _banner("OVERALL: FAIL (programmatic)")
        return 1
    _banner("OVERALL: FAIL (live)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

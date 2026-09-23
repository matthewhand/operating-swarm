#!/usr/bin/env python3
"""Prove the handover mirror fleet by chatting every seat on the live tip.

For each manifest seat this script:

1. POSTs one charter-true task starter to ``/v1/agents/<agent_id>/send/``
   on the running open-swarm tip (default ``http://127.0.0.1:8002``).
2. Writes the seat's full chat log (prompt + complete reply) to
   ``logs/handover_fleet/<run-id>/<agent_id>.md`` (gitignored).
3. Emits ``PROOF-REPORT.md`` — a PASS/FAIL table per seat with reply
   excerpts — as the reviewable chat-log proof the handover asks for.

Honesty rules: a seat that errors, times out, or answers empty is FAIL —
no garbage-as-success. No secrets are sent or logged.

Usage:
    uv run python scripts/prove_handover_fleet.py [--agents id1,id2]
        [--base-url URL] [--timeout SEC] [--base-dir PATH]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

DEFAULT_MANIFEST = ROOT / "scripts" / "handover_fleet_manifest.json"
DEFAULT_BASE_URL = "http://127.0.0.1:8002"
REVIEW_EXCERPT = 500


def seat_task(seat: dict) -> str:
    """One charter-true task starter per seat."""
    task = str(seat.get("proof_task") or "").strip()
    if task:
        return task
    return (
        "Handover mirror proof: in 2-4 sentences, state your charter, your "
        "current handover status (active / held / parked / stood down), and "
        "the first task you would pick up when unblocked. Do not start any "
        "tooling work in this turn."
    )


_CLI_FAILURE_RE = re.compile(
    r"^\s*(exited \d+:|Error:|Traceback \(most recent call last\)"
    r"|Unknown options:|timed out after \d+|Command timed out)"
)


def looks_like_cli_failure(text: str) -> bool:
    """CLI failure banners leaked into the reply are FAIL, not content.

    Checked on the leading banner zone only, so a seat legitimately
    discussing errors deeper in its reply is not penalized.
    """
    head = text[:240]
    return bool(_CLI_FAILURE_RE.match(head)) or "Failed to load extension" in head


def _post_json(base_url: str, path: str, body: dict,
               timeout: float, token: str | None) -> tuple[int, dict | str]:
    url = f"{base_url.rstrip('/')}{path}"
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"Content-Type": "application/json"},
    )
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")[:400]
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, f"transport error: {exc}"


def warm_router(base_url: str, agent_id: str, timeout: float, token: str | None) -> None:
    """Trigger the router blueprint's designs reload via one direct route."""
    _post_json(base_url, "/v1/agents/route/", {
        "message": "warm designs reload",
        "routing_strategy": "direct",
        "target_agent": agent_id,
        "stream": False,
    }, timeout, token)


def chat_once(base_url: str, agent_id: str, message: str,
              timeout: float, token: str | None) -> tuple[bool, str]:
    """One turn via POST /v1/agents/<id>/send/. Returns (ok, text)."""
    status, payload = _post_json(
        base_url, f"/v1/agents/{agent_id}/send/",
        {"message": message, "stream": False}, timeout, token,
    )
    if status == 404 and isinstance(payload, str) and "not found" in payload:
        # Router blueprint may not have reloaded designs since boot — warm and retry once.
        warm_router(base_url, agent_id, timeout, token)
        status, payload = _post_json(
            base_url, f"/v1/agents/{agent_id}/send/",
            {"message": message, "stream": False}, timeout, token,
        )
    if status == 0:
        return False, str(payload)
    if status != 200:
        return False, f"HTTP {status}: {payload}"
    if not isinstance(payload, dict):
        return False, f"unexpected non-JSON body: {str(payload)[:300]}"
    if str(payload.get("status")) != "success":
        return False, f"status={payload.get('status')!r} err={payload.get('error')!r}"
    text = str(payload.get("response") or "").strip()
    if not text:
        return False, "empty reply"
    if "internal server error" in text.lower():
        return False, f"server error surfaced in reply: {text[:300]}"
    if looks_like_cli_failure(text):
        return False, f"CLI failure banner in reply: {text[:300]}"
    return True, text


def write_log(log_dir: Path, seat: dict, task: str, ok: bool, text: str) -> Path:
    agent_id = seat["agent_id"]
    path = log_dir / f"{agent_id}.md"
    lines = [
        f"# Chat log — {agent_id}",
        "",
        f"- Recorded: {dt.datetime.now().isoformat(timespec='seconds')}",
        f"- Seat kind: {seat.get('_kind', 'unknown')}"
        + (f" (cli: {seat['_cli']})" if seat.get("_cli") else ""),
        f"- Specialty: {seat.get('specialty', '')}",
        f"- Result: {'PASS' if ok else 'FAIL'}",
        "",
        "## Prompt",
        "",
        task,
        "",
        "## Reply",
        "",
        text if ok else f"**ERROR** — {text}",
        "",
        "## Charter (manifest instructions)",
        "",
        seat.get("instructions", ""),
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--base-url", default=os.environ.get("SWARM_PROOF_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--timeout", type=float,
                        default=float(os.environ.get("SWARM_PROOF_TIMEOUT", "120")))
    parser.add_argument("--agents", default="",
                        help="comma-separated subset of agent_ids to prove")
    parser.add_argument("--base-dir", type=Path, default=ROOT / "logs" / "handover_fleet")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    seats = manifest.get("seats") or []
    if not seats:
        raise SystemExit(f"no seats in {args.manifest}")

    from swarm.core.router_designs import load_designs

    designs = {a.get("agent_id"): a for a in load_designs()}
    only = {a.strip() for a in args.agents.split(",") if a.strip()}
    if only:
        seats = [s for s in seats if s.get("agent_id") in only]

    token = os.environ.get("SWARM_PROOF_TOKEN") or None
    run_id = dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    log_dir = args.base_dir / run_id
    log_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for seat in seats:
        agent_id = seat["agent_id"]
        spec = designs.get(agent_id)
        if not spec:
            results.append({"agent_id": agent_id, "ok": False,
                            "text": "seat missing from router_designs (run seed_handover_fleet.py)"})
            continue
        seat = {**seat, "_kind": spec.get("kind"), "_cli": spec.get("cli")}
        task = seat_task(seat)
        print(f"[prove] {agent_id} ({spec.get('kind')})…", flush=True)
        ok, text = chat_once(args.base_url, agent_id, task, args.timeout, token)
        path = write_log(log_dir, seat, task, ok, text)
        excerpt = text[:REVIEW_EXCERPT].replace("\n", " ")
        results.append({"agent_id": agent_id, "ok": ok, "text": text,
                        "excerpt": excerpt, "log": str(path)})
        print(f"         {'PASS' if ok else 'FAIL'} → {path.name}", flush=True)

    passed = sum(1 for r in results if r["ok"])
    report = [
        "# Handover mirror fleet — PROOF REPORT",
        "",
        f"- Run: {run_id}",
        f"- Base URL: {args.base_url} (live tip)",
        f"- Result: {passed}/{len(results)} seats PASS",
        "",
        "| Seat | Kind | Result | Reply excerpt / error |",
        "|------|------|--------|----------------------|",
    ]
    for seat, r in zip(seats, results):
        kind = designs.get(seat["agent_id"], {}).get("kind", "?")
        excerpt = r.get("excerpt") or r["text"][:REVIEW_EXCERPT]
        report.append(f"| {r['agent_id']} | {kind} | "
                      f"{'PASS' if r['ok'] else 'FAIL'} | {excerpt} |")
    report += ["", "Full chat logs live beside this report.",
               "", "Fixes: handover proof request (chat-log review).", ""]
    report_path = log_dir / "PROOF-REPORT.md"
    report_path.write_text("\n".join(report), encoding="utf-8")

    print(f"\n{passed}/{len(results)} PASS — report: {report_path}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

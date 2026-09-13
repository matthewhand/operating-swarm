#!/usr/bin/env python3
"""Issue #168 — ping currently configured chat seats on :8002."""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("SWARM_PROBE_BASE", "http://127.0.0.1:8002")
PING = "Reply with the single word pong."


def load_dotenv() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def token() -> str:
    return (
        os.environ.get("API_AUTH_TOKEN")
        or os.environ.get("SWARM_API_KEY")
        or ""
    ).strip()


def request(method: str, path: str, body: dict | None = None, timeout: int = 45) -> tuple[int, object]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    auth = token()
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed: object = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw[:400]
            return resp.status, parsed
    except urllib.error.HTTPError as err:
        raw = err.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw[:400]
        return err.code, parsed
    except Exception as err:  # noqa: BLE001 — probe must name the failure
        return 0, {"error": str(err)}


def assistant_text(payload: object) -> str:
    if not isinstance(payload, dict):
        return str(payload)[:240]
    err = payload.get("error")
    if isinstance(err, dict):
        return str(err.get("message") or err)[:240]
    if isinstance(err, str) and err:
        return err[:240]
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return json.dumps(payload)[:240]
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if isinstance(msg, dict):
        return str(msg.get("content") or "")[:240]
    return ""


def ping(model: str, params: dict | None = None) -> tuple[int, str]:
    body: dict = {
        "model": model,
        "messages": [{"role": "user", "content": PING}],
        "stream": False,
    }
    if params:
        body["params"] = params
    status, payload = request("POST", "/v1/chat/completions", body)
    return status, assistant_text(payload)


def main() -> int:
    load_dotenv()
    seats: list[tuple[str, str, dict | None]] = [
        ("support", "support", None),
        ("codey", "codey", None),
        ("api_agent", "api_agent", None),
        ("cli_agent", "cli_agent", {"cli": "grok", "failover": False}),
        ("chatbot", "chatbot", None),
    ]
    _, remotes = request("GET", "/v1/remotes/")
    if isinstance(remotes, dict):
        rows = remotes.get("data") or remotes.get("remotes") or []
        if isinstance(rows, list):
            for row in rows[:6]:
                if not isinstance(row, dict):
                    continue
                rid = str(row.get("id") or "")
                if not rid:
                    continue
                seats.append((f"remote:{rid}", "remote_harness", {"remote_id": rid}))
    print(f"base={BASE} auth={'yes' if token() else 'no'}")
    failed = 0
    for label, model, params in seats:
        status, text = ping(model, params)
        stripped = text.strip()
        lower = stripped.lower()
        ok = (
            status == 200
            and bool(stripped)
            and "error" not in lower[:80]
            and not stripped.startswith("{")
            and stripped not in {"null"}
            and "runresult" not in lower[:40]
        )
        mark = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{mark}\t{label}\thttp={status}\t{text.replace(chr(10), ' ')[:180]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

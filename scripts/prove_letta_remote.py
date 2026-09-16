"""Live smoke: Letta health -> list -> resume -> send (sync) -> stream (deltas) -> marker round-trip.

Uses LETTA_BASE_URL / LETTA_API_KEY from the operator env only — no hostnames,
ports, or tokens in this file.
"""
from __future__ import annotations

import os
import sys
import uuid

from swarm.core import remotes as r
from swarm.core.remote_harness import sessions_from_operate

cfg = {"llm": {}, "remotes": {}}

print("=== 1. HEALTH ===")
health = r.check_health("letta", config=cfg, timeout=6)
print("HEALTH:", health.state, "|", health.detail)
if health.version:
    print("VERSION keys:", list(health.version)[:4])

print("\n=== 2. LIST ===")
listed = r.operate("letta", "list", config=cfg, timeout=6)
print("LIST ok:", listed.ok, "|", listed.detail)
sessions = sessions_from_operate(listed)
print(f"SESSIONS: {len(sessions)}")
for s in sessions[:5]:
    print("  -", s.id, "|", s.title)

print("\n=== 3. RESUME ===")
sent_no_session = r.operate("letta", "send", prompt="hi", config=cfg, timeout=6, session_id=None)
print("SEND-no-session ok:", sent_no_session.ok, "| gap:", sent_no_session.gap, "|", (sent_no_session.detail or "")[:90])

agent_id = (sessions[0].id if sessions else os.getenv("LETTA_AGENT_ID", "")).strip()
if not agent_id:
    print("No Letta agent session found or configured in LETTA_AGENT_ID to resume.")
    print("Skipping send, stream, and marker round-trip (never mints new agents).")
    sys.exit(0)

print(f"RESUMING agent: {agent_id} ({sessions[0].title if sessions else 'custom'})")

print("\n=== 4. SEND (SYNC) ===")
sync_sent = r.operate(
    "letta",
    "send",
    prompt="Hello from Open Swarm prove (sync)",
    config=cfg,
    timeout=30,
    session_id=agent_id,
)
print("SEND (sync) ok:", sync_sent.ok, "|", (sync_sent.detail or "")[:90])
if sync_sent.ok and sync_sent.data:
    resp = sync_sent.data.get("response") or ""
    print("RESPONSE preview:", resp[:80] if resp else "(empty)")

print("\n=== 5. STREAM (DELTAS) ===")
try:
    spec = r.load_remote("letta", config=cfg)
    deltas = []
    stream_err = None
    for delta, done, err in r.iter_letta_chat(
        spec,
        "Hello from Open Swarm prove (stream)",
        session_id=agent_id,
        timeout=30,
    ):
        if delta:
            deltas.append(delta)
        if err:
            stream_err = err
            break
        if done:
            break
    assembled = "".join(deltas)
    print(f"STREAM ok: {stream_err is None} | deltas: {len(deltas)} | err: {stream_err}")
    print("STREAM preview:", assembled[:80] if assembled else "(empty)")
except Exception as exc:
    print(f"STREAM failed: {exc}")

print("\n=== 6. MARKER ROUND-TRIP ===")
marker = f"SWARM-PROOF-{uuid.uuid4().hex[:8]}"
marker_prompt = f"Echo this exact token: {marker}"
marker_sent = r.operate(
    "letta",
    "send",
    prompt=marker_prompt,
    config=cfg,
    timeout=30,
    session_id=agent_id,
)
if marker_sent.ok and marker_sent.data:
    reply = marker_sent.data.get("response") or ""
    matched = marker in reply
    print(f"MARKER round-trip ok: {matched} | marker: {marker}")
    if not matched:
        print("Reply was:", reply[:120])
else:
    print("MARKER round-trip failed:", marker_sent.detail)

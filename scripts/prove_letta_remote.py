"""Live smoke: Letta health + list through the harness code.

Uses LETTA_BASE_URL / remotes.letta from the operator env only — no hostnames
or tokens in this file.
"""
from swarm.core import remotes as r
from swarm.core.remote_harness import sessions_from_operate

cfg = {"llm": {}, "remotes": {}}

health = r.check_health("letta", config=cfg, timeout=6)
print("HEALTH:", health.state, "|", health.detail)
if health.version:
    print("VERSION keys:", list(health.version)[:4])

listed = r.operate("letta", "list", config=cfg, timeout=6)
print("LIST ok:", listed.ok, "|", listed.detail)
sessions = sessions_from_operate(listed)
print(f"SESSIONS: {len(sessions)}")
for s in sessions[:5]:
    print("  -", s.id, "|", s.title)

sent = r.operate("letta", "send", prompt="hi", config=cfg, timeout=6, session_id=None)
print("SEND-no-session ok:", sent.ok, "| gap:", sent.gap, "|", (sent.detail or "")[:90])

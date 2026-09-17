"""Live smoke: n8n health + list through the new harness code."""

from swarm.core import remotes as r
from swarm.core.remote_harness import sessions_from_operate

cfg = {"llm": {}, "remotes": {}}

health = r.check_health("n8n", config=cfg, timeout=6)
print("HEALTH:", health.state, "|", health.detail)
if health.version:
    print("VERSION keys:", list(health.version)[:4])

listed = r.operate("n8n", "list", config=cfg, timeout=6)
print("LIST ok:", listed.ok, "|", listed.detail)
sessions = sessions_from_operate(listed)
print(f"SESSIONS: {len(sessions)}")
for s in sessions[:5]:
    print("  -", s.id, "|", s.title)

sent = r.operate("n8n", "send", prompt="hi", config=cfg, timeout=6, session_id=None)
print("SEND-no-session ok:", sent.ok, "| gap:", sent.gap, "|", sent.detail[:90])

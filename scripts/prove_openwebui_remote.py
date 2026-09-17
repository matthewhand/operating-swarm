"""Live smoke: Open WebUI health + list through the new harness code.

Env/placeholders only — no hostnames/tokens committed. Point OPENWEBUI_BASE_URL
and OPENWEBUI_API_KEY at the engineer's local self-hosted Open WebUI.
"""
import os

from swarm.core import remotes as r
from swarm.core.remote_harness import sessions_from_operate

cfg = {"llm": {}, "remotes": {}}

health = r.check_health("openwebui", config=cfg, timeout=6)
print("HEALTH:", health.state, "|", health.detail)

listed = r.operate("openwebui", "list", config=cfg, timeout=6)
print("LIST ok:", listed.ok, "|", listed.detail)
sessions = sessions_from_operate(listed)
print(f"SESSIONS: {len(sessions)}")
for s in sessions[:5]:
    print("  -", s.id, "|", s.title)

query = os.environ.get("OPENWEBUI_LIST_QUERY", "")
if query:
    searched = r.operate("openwebui", "list", config=cfg, timeout=6, query=query)
    print("SEARCH ok:", searched.ok, "|", searched.detail, "|", len(sessions_from_operate(searched)))

sent = r.operate("openwebui", "send", prompt="hi", config=cfg, timeout=6, session_id=None)
print("SEND-no-session ok:", sent.ok, "|", "gap:", sent.gap, "|", (sent.detail or "")[:90])

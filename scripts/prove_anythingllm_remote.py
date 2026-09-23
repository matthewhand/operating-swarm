"""Live smoke: AnythingLLM health + list through the new harness code."""
import os

from swarm.core import remotes as r
from swarm.core.remote_harness import sessions_from_operate

cfg = {"llm": {}, "remotes": {}}

health = r.check_health("anythingllm", config=cfg, timeout=6)
print("HEALTH:", health.state, "|", health.detail)
if health.version:
    print("VERSION keys:", list(health.version)[:4])

listed = r.operate("anythingllm", "list", config=cfg, timeout=6)
print("LIST ok:", listed.ok, "|", listed.detail)
sessions = sessions_from_operate(listed)
print(f"SESSIONS: {len(sessions)}")
for s in sessions[:5]:
    print("  -", s.id, "|", s.title)

# Send without a session: must be the honest gap, never a minted thread.
sent = r.operate("anythingllm", "send", prompt="hi", config=cfg, timeout=6, session_id=None)
print("SEND-no-session ok:", sent.ok, "| gap:", sent.gap, "|", sent.detail[:90])
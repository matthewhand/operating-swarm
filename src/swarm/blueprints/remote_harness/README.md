# remote_harness

Open Swarm as a **harness for other harnesses**: Hermes, OpenMausBot (OMB), Rakazo, and a nested open-swarm process.

This blueprint does **not** clone Grok / OMB / Rakazo seats. It configures remotes,
probes health, and (when the remote exposes an API) lists or sends a job through
`swarm.core.remotes`. Specialists are openai-agents **agent-as-tool** wrappers
for remotes **placed** in a Team (`agent_team.members`). That Team is not the
`/teams/` LLM-profile alias registry (prefer **Profiles** for that page).

Grok-Bot chrome is **not** claimed live.

## Configure

```bash
swarm-cli remotes set hermes --base-url http://198.51.100.36:8642 --api-key-env HERMES_API_KEY
swarm-cli remotes set omb --base-url http://198.51.100.32:8802 --api-key-env OMB_API_KEY
swarm-cli remotes set rakazo --base-url http://198.51.100.32:3100 --ui-url http://198.51.100.32:5173 --api-key-env RAKAZO_API_KEY
swarm-cli remotes set swarm --base-url http://127.0.0.1:9 --api-key-env SWARM_REMOTE_API_KEY
```

Or `PATCH /v1/remotes/<id>/`. See [docs/REMOTE_HARNESSES.md](../../../docs/REMOTE_HARNESSES.md).

## Grammar

```
health
health hermes
list
list omb
list swarm
send hermes summarize systemd units
send swarm hello
```

LAN LLM for *this* swarm (not a remote harness): `http://198.51.100.30:8000/v1`.
Do not point remotes at Fly open-litellm.

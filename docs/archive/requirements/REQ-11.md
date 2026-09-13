# REQ-11 — Remotes Hermes / OMB / Rakazo

**Status:** PR [318](https://github.com/matthewhand/open-swarm/pull/318) — in flight

## Intent

Open Swarm as a harness **for** Hermes, OpenMausBot (OMB), and Rakazo. Those
remotes are Team *members* you place into a roster so they can see and talk via
openai-agents handoff / `as_tool`.

## Success

| Remote | Host | Default | Auth |
|---|---|---|---|
| hermes | dev-worker-gpu | `http://198.51.100.36:8642` (UI `:9119` is chrome, not the operate API) | `HERMES_API_KEY` |
| omb | Windows2 | `http://198.51.100.32:8802` | `OMB_API_KEY` |
| rakazo | Windows2 | API `http://198.51.100.32:3100`, UI `:5173` | `RAKAZO_API_KEY` and/or session cookie |

- `swarm-cli remotes` set / place / unplace / health. REST `/v1/remotes/<id>/` + `/v1/agent-team/`.
- Health is one TCP + one HTTP, no retries, no crash-loop. DOWN is a report. 401/403 on a live port is UP.
- Persist refuses Fly open-litellm URLs. LAN LLM for *this* swarm: `http://198.51.100.30:8000/v1`.

## Constraints

- This is **not** Django `/teams/` + `/v1/teams/` (those are **LLM-profile aliases** — live today). Prefer **Profiles** in new copy. URLs stay `/teams/` (documented collision).
- Do not claim remotes work on this starting tree. Chat has no Remote selector here.
- No Neon. No oracle. Docs-only on this PR — do not implement here.

## Owner

- CoS transcribes
- cloud implements
- engineer GitHub-merge after skeptic
- live preview `198.51.100.30:8001` guest dirty only

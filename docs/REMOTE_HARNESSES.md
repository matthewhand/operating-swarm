# Remote harnesses — Hermes, OpenMausBot, Rakazo, Herdr, nested swarm

**Remote** is one user-facing kind. Concrete remotes **implement**
[`RemoteHarness`](./adr/011-remote-harness.md) (REQ-203 / #680). Herdr is a
Remote implementation, not a fifth kind.

| Implementation | `impl` id | Transport | Live verbs | Optional `operate` (computer) |
|----------------|-----------|-----------|------------|-------------------------------|
| **Hermes** | `hermes` | HTTP | health, list, send | no |
| **OpenMousBot** | `omb` | HTTP | health, list, send | yes — stub (`computer-status` / `computer-screenshot`) until ADR-007 Phase 3 |
| **Rakazo** | `rakazo` | HTTP | health, list, send | yes — stub until ADR-007 Phase 3 |
| **Herdr** | `herdr` | CLI local / SSH remote | health, list, send, interrogate | no |
| **Nested open-swarm** | `swarm` (`open-swarm`) | HTTP | health, list, send | no |

Typed protocol: `from swarm.core.remote_harness import RemoteHarness`. Settings
`GET /v1/remotes/` `kinds[]` uses `kind=remote` and `id`/`impl` as the
discriminator. Add-agent Remote tab lists these impls — not a parallel Herdr kind.

Open Swarm can sit **in front of** other agent harnesses: configure them, check
they are up, and send work through **their** APIs. This is not a concurrent
Grok / OMB / Rakazo seat clone, and **Grok-Bot chrome is not claimed live**.

**Team vocabulary (REQ-11 / REQ-57):** a Team is how you wire API agents, CLI
agents, and **remote** agents (Hermes / OMB / Rakazo / nested open-swarm) so
they can see and talk to each other via openai-agents **handoff / as_tool**.
Those remotes are Team *members* (`consult_hermes`, `consult_omb`,
`consult_rakazo`, `consult_swarm`). **Herdr** is also a remotes kind, but it
is **SSH-shaped** (local Herdr vs SSH to a Herdr host + its CLIs) — not
another HTTP remote. See [HERDR.md](./HERDR.md) (REQ-100 / #463).

That is **not** the Django `/teams/` JSON registry. `/teams/` today is
LLM-profile aliases (`DynamicTeamBlueprint`). New copy should not call those
aliases “teams”; prefer **Profiles**. `GET /v1/remotes/` and
`GET /v1/agent-team/` repeat this collision in `vocabulary` + `team_members`.

Place or unplace remotes in that Team (`agent_team.members` in
`swarm_config.json`; missing key = hermes/omb/rakazo placed; `swarm` stays
catalog-only until you `place` it — do not auto-add this instance as its own
remote; `[]` = empty Team):

```bash
swarm-cli remotes team
swarm-cli remotes unplace rakazo
swarm-cli remotes place rakazo
```

REST: `GET /v1/agent-team/` · `PATCH /v1/agent-team/` `{"members":["hermes","omb"]}`
or `{"place":"rakazo"}` / `{"unplace":"hermes"}`. `remote_harness` only attaches
`consult_*` as_tool specialists for **placed** members.

LAN LLM for *this* swarm: `http://198.51.100.30:8000/v1`. Do **not** point remotes
at Fly open-litellm.

This environment could not TCP-reach `198.51.100.36` / `198.51.100.32` (cloud VM, no
LAN). Defaults below are operator facts already present in `harness_fleet`
plus the published APIs for those products. Health fails honestly when the
box is down.

Remotes are **opt-in**. Settings → Remotes starts empty (no Hermes / OpenMousBot /
Rakazo card) until you **+ Add remote**. Kind `hermes` is complete: after add
(base URL + api-key-env *name* only) Settings can health / list / send.

## Configure (persist)

Kind defaults (override when adding). Unused kinds are not pre-seeded cards:

| Remote | Host | Default base URL | Auth env |
|---|---|---|---|
| **hermes** | dev-worker-gpu | `http://198.51.100.36:8642` (UI `:9119`) | `HERMES_API_KEY` (Hermes `API_SERVER_KEY`) |
| **omb** | Windows2 | `http://198.51.100.32:8802` | `OMB_API_KEY` (optional Bearer) |
| **rakazo** | Windows2 | API `http://198.51.100.32:3100`, UI `:5173`, tree `C:\rakazo` | `RAKAZO_API_KEY` and/or `RAKAZO_SESSION_COOKIE` |
| **swarm** | another open-swarm process | stub `http://127.0.0.1:9` (not this listen URL) | `SWARM_REMOTE_API_KEY` (Bearer; env var name only) |

```bash
swarm-cli remotes set hermes --base-url http://198.51.100.36:8642 --api-key-env HERMES_API_KEY
swarm-cli remotes set omb --base-url http://198.51.100.32:8802 --api-key-env OMB_API_KEY
swarm-cli remotes set rakazo --base-url http://198.51.100.32:3100 --ui-url http://198.51.100.32:5173 --api-key-env RAKAZO_API_KEY
swarm-cli remotes set swarm --base-url http://127.0.0.1:9 --api-key-env SWARM_REMOTE_API_KEY
```

Nested swarm is a **normal deploy** (own process, own local DB). Point
`--base-url` at that child's listen URL. v1 refuses a swarm URL that matches
this server's listen URL (`PORT` / `SWARM_LISTEN_URL`). A child is not
required to nest the parent. Tests use `http://127.0.0.1:9` and `CHANGE_ME`.

Equivalent persist:

* `PATCH /v1/remotes/hermes/` `{"base_url":"http://198.51.100.36:8642","api_key":"${HERMES_API_KEY}"}`
* `swarm-cli config add --section remotes --name hermes --json '{...}'`
* Edit `~/.config/swarm/swarm_config.json` → `"remotes"` (or `SWARM_CONFIG_PATH`)

Env overrides win over the file: `HERMES_BASE_URL`, `OMB_BASE_URL`, `RAKAZO_BASE_URL`, `SWARM_REMOTE_BASE_URL`.

Settings → **Remotes** lists only added remotes (secrets redacted). Missing
catalog is empty, not a default Hermes card. `swarm-cli remotes get hermes`
prints the redacted view after add.

## Health

```bash
swarm-cli remotes health
curl -X POST http://127.0.0.1:8000/v1/remotes/hermes/health/
```

One TCP connect + one HTTP GET. **No retries, no crash-loop.** DOWN is a
report, not an exception. Auth-gated 401/403 on a live port counts as **UP**
(endpoint is alive).

| Remote | Probe |
|---|---|
| Hermes | `GET /health` → `{"status":"ok"}`; version via `GET /v1/models` |
| OMB | `GET /api/health` → `{"app":"openmausbot",...}` |
| Rakazo | `GET /health` → `{"ok":true,"runtime":"pi",...}` |
| Nested swarm | `GET /health` → `{"status":"ok"}`; version via `GET /v1/models` |
| **Herdr** | **Not HTTP.** Local: `herdr workspace list`. Remote: `ssh user@host -- herdr workspace list` (stub SSH in tests). |

## Operate today vs not

| Remote | List | Send / start a job | Gap |
|---|---|---|---|
| **Hermes** | `GET /v1/models`, `GET /api/sessions`, `GET /api/jobs` | `POST /v1/runs` `{"input":"..."}` | Needs Bearer `API_SERVER_KEY`. Do not bounce Hermes to read config; do not delete `SKILL.md`. Dashboard `:9119` is not the operate API. |
| **OMB** | `GET /api/bots` | `POST /api/bots/{id}/messages` `{"text":"..."}` (202). Creates a bot if none exist. | HTTP only — no OMB source clone. Upstream default bind is `127.0.0.1:8799`; this LAN install is `:8802`. |
| **Rakazo** | `POST /rpc/bots/list` | `POST /rpc/threads/send` `{botId,text}` | **Better Auth session required** for RPC. Public `GET /health` works without auth. Set `RAKAZO_SESSION_COOKIE` from a signed-in UI session. No unauthenticated job API in upstream. |
| **swarm** | `GET /v1/blueprints/` (fallback `GET /v1/models/`) | `POST /v1/chat/completions/` `{"model":"<blueprint>","messages":[…]}` | Network remote only. Unreachable child is the same DOWN / operate-fail as other remotes (no hang). Do not persist this process listen URL. |
| **Herdr** | `herdr agent list` (local or over SSH) | `herdr agent prompt` / `herdr agent get` (interrogate) | SSH-shaped. Not HTTP like the rows above. Missing ssh_host/ssh_user is a clear error. Stub SSH in tests; no live LAN. |

```bash
swarm-cli remotes operate hermes --op list
swarm-cli remotes operate hermes --op send --prompt "status"
swarm-cli remotes operate omb --op list
swarm-cli remotes operate omb --op send --prompt "hello" --target <botId>
swarm-cli remotes operate rakazo --op list
swarm-cli remotes operate herdr --op list
swarm-cli remotes operate herdr --op send --target w3:p1 --prompt HERDR_PING_OK
```

REST: `POST /v1/remotes/<id>/operate/` `{"op":"list"}` or `{"op":"send","prompt":"…","target":"…"}`.

Blueprint `remote_harness` (chat `model: remote_harness`): grammar `health`, `list omb`, `list swarm`, `send hermes …`. Coordinator uses openai-agents **as_tool** specialists (`consult_hermes` / `consult_omb` / `consult_rakazo` / `consult_swarm` when placed).

`harness_fleet` inventory now names `rakazo-32:3100` and `omb-32:8802` (legacy `rakoza-32` / `openmousbot-32` aliases kept).

## Computer control (not operate yet)

`operate` stays **list / send**. OMB Local VM (`/api/local-computer*`) and Rakazo `rpc.computer.*` are unused. How open-swarm should adapt those local stacks (Playwright vs Docker sibling sandbox vs host via a placed remote; SaaS deferred) is [ADR-007](./adr/007-local-computer-control.md) (REQ-189 / #645). Do not treat a placed remote as a computer until a later Issue adds computer operate ops.

## Out of scope (this change)

* Do not enable `open-swarm-oracle`.
* Do not change Neon.
* Do not POST to Qwen/Comfy as a prove.
* Do not set `SWARM_ALLOW_ANONYMOUS`.
* Do not point remotes at Fly open-litellm (`persist_remote` refuses those URLs).

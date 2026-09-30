# Herdr connectivity (REQ-21)

Operating Swarm can drive **Herdr** as a member `kind=herdr` without owning the TUI.

`os-cli tui` ([REQ-111](https://github.com/matthewhand/open-swarm/issues/481)
/ [ADR-012](./adr/012-swarm-cli-tui.md)) is Operating Swarm’s own API client
(Herdr-*like* chrome). It is not this Herdr hop and does not SSH to a Herdr host.

This is **NOT Hermes**, **NOT OMB**, and **NOT Rakazo**. Those are different
products. Herdr is the pane session server + CLI at [herdr.dev](https://herdr.dev/).

## Same-host default

The default remote is **localhost**. Invoke the official CLI with **no**
`--remote`:

```bash
herdr workspace list
herdr agent list
herdr agent read w3:p1
herdr agent prompt w3:p1 HERDR_PING_OK
herdr agent wait w3:p1 --until idle
```

That talks to the Herdr already on this host (local server + unix sockets,
typically `~/.config/herdr/`). Live `.30` (dev-worker-max) runs `herdr server` plus
the remote-client-bridge. This cloud agent does **not** SSH there.

## Settings Remotes kind (REQ-64 + REQ-100)

Herdr is an **addable remotes kind** (`kind=herdr`). It is **opt-in**
(compatible with REQ-59): it does not appear in Settings Remotes until you add
it. There is **no baked LAN host**.

**Remote Herdr is SSH-shaped**, not an HTTP remote like OpenMousBot / Hermes /
Rakazo.

**Hop model:** one hop. Operating Swarm SSHs to the Herdr host, then talks to Herdr
on that host (official `herdr` CLI). Herdr wraps the CLIs it already manages
there (agy / pi / grok / …). Local Herdr skips SSH and talks to Herdr on this
host. We do not HTTP to a remote Herdr, and we do not SSH past Herdr as a
second product hop.

```bash
# Local Herdr (this host, no SSH). Localhost URL only if you choose that.
os-cli remotes set herdr --herdr-mode local

# Remote Herdr — SSH to the Herdr host (env-var name for a key path; never a private key)
os-cli remotes set herdr --herdr-mode ssh --ssh-host herdr.example.test --ssh-user herdr --ssh-identity-env HERDR_SSH_IDENTITY
```

Settings → Remotes → **+ Add remote** (or Django `/settings/` **Add Herdr remote**)
does the same `PATCH /v1/remotes/herdr/`. After add, Herdr shows in the Remotes
list. Missing SSH config is a clear error — Operating Swarm will not guess a host.

Health / list / send / interrogate (stub SSH in tests; no live LAN in CI):

| Op | Local | Remote (SSH) |
|---|---|---|
| Health | `herdr workspace list` (optional leftover localhost `GET /health`) | `ssh user@host -- herdr workspace list` |
| List | `herdr agent list` (+ workspace list) | same argv over SSH |
| Send | `herdr agent prompt <TARGET> <TEXT>` | same argv over SSH |
| Interrogate CLI X | `herdr agent get <TARGET>` | same argv over SSH |

```bash
os-cli remotes health herdr
os-cli remotes operate herdr --op list
os-cli remotes operate herdr --op send --target w3:p1 --prompt HERDR_PING_OK
os-cli remotes operate herdr --op interrogate --target w3:p1
```

## Querying Herdr from OS (#1728)

The table above is the *write* half. OS also needs to **ask** Herdr what is
happening without sending anything. These are all read-only verbs, wrapped by
`HerdrClient` (`src/swarm/herdr/client.py`), and all proven on `herdr` 0.8.2:

| Question | Command | Wrapper |
|---|---|---|
| Is the server up, and is the client compatible? | `herdr status server --json` | `HerdrClient.server_status()` |
| What is the whole session doing right now? | `herdr api snapshot` | `HerdrClient.session_snapshot()` |
| What is every agent doing? | `herdr agent list` | `HerdrClient.agent_list()` |
| What is this one agent doing? | `herdr agent get <TARGET>` | `HerdrClient.agent_get()` |
| Why is it in that state? | `herdr agent explain <TARGET> --format json` | `HerdrClient.agent_explain()` |

`herdr api snapshot` is the interesting one: it returns the live session
(workspaces / tabs / panes / agents) in **one** process, so a whole-workspace
query costs one subprocess rather than one per pane. Its agent rows carry the
same `agent_status` + `state_change_seq` fields as `agent list`, so
`swarm.herdr.status.pane_statuses()` unwraps both shapes with one parser.

### REST

| Method | Path | Role |
|--------|------|------|
| GET | `/v1/herdr-agents/status/` | Every live pane's normalized status, from one `herdr agent list` |
| GET | `/v1/herdr-agents/status/?remote=<r>` | Same, prefixed `herdr --remote <r>` |

Each row: `target`, `status`, `herdr_status` (the raw value OS mapped from),
`state_change_seq`, `agent`, `workspace_id`. `status` is one of
`unknown` | `idle` | `working` | `waiting` | `finished`.

**Fails open, honestly.** A missing CLI, a stopped server, an SSH hop that
refuses, or a timeout all answer **`200`** with `herdr_available: false`, an
empty `data`, and the real reason in `error` — the same contract as
`/v1/herdr-agents/discover/`. A down Herdr must never produce a 500 (the UI
would break) nor a fabricated `idle` (which reads as "nothing is happening"
when the truth is "we do not know"). `unknown` is the default; only positive
evidence labels a pane.

Note the route order: `/v1/herdr-agents/status/` is registered **before** the
`<str:agent_id>` detail route, or `status` binds as a `HerdrAgent` name lookup.

### The status vocabulary

Herdr's own enum is published in its bundled API schema
(`herdr api schema --json` → `event.$defs.AgentStatus`): `idle` | `working` |
`blocked` | `done`. OS renames exactly two of them and leaves the rest verbatim:

| Herdr `agent_status` | OS seat status | Meaning in the rail |
|---|---|---|
| `working` | `working` | busy — not silent |
| `blocked` | `waiting` | a human question is pending |
| `done` | `finished` | the turn ended with output |
| `idle` | `idle` | nothing running |
| *anything else / absent* | `unknown` | no positive evidence |

One table, one function: `normalize_agent_status()` in
`src/swarm/herdr/status.py`. Every consumer — the REST surface, the status
watcher, the SPA store — calls it. A second hand-written copy of this mapping
is the defect class that makes "blocked means something else here" appear.

Do not commit tokens or private keys. Identity is an env-var *name*
(`HERDR_SSH_IDENTITY`) whose value is a key path. Placeholders only
(`${HERDR_API_KEY}`).

## Optional `--remote`

A persisted Herdr row may set `remote` to a string such as
`matthewh@198.51.100.36`, `workbox`, or `ssh://you@server:2222`. Empty/omitted
means localhost. When set, **every** CLI call is prefixed:

```bash
herdr --remote matthewh@198.51.100.36 agent prompt w3:p1 HERDR_PING_OK
```

See [How to work with Herdr](https://herdr.dev/docs/how-to-work/) and the
[CLI reference](https://herdr.dev/docs/cli-reference/). Operating Swarm does **not**
invent flags or a socket protocol; it wraps `herdr`.

## Proven prompt shape

Engineer proof on dev-worker-max `198.51.100.30`:

```bash
herdr agent prompt w3:p1 HERDR_PING_OK
```

`TEXT` is **one** argv argument. The CLI returned `type: agent_prompted`. The
pane showed user `HERDR_PING_OK` and grok replied that the ping was OK.

Unquoted TEXT is a quoting bug: herdr then reports `unknown option: with`.
The Python wrapper always passes TEXT as a single `argv` element (spaces stay
inside that one argument).

## Blocked and `--wait`

- If the agent is **blocked**, submit is rejected (`HerdrBlockedError` /
  Herdr `agent_blocked`). Input is not sent.
- If the agent is already **working**, `herdr agent prompt --wait` may match
  **that in-flight turn finishing**, not a newly submitted turn. Do not assume
  `--wait` observed your prompt.
- Tests must **mock** `herdr`. Do **not** target a WORKING grok pane in CI.

## Status notifications (#1729)

Herdr's per-pane lifecycle is replicated into OS affordances by
`swarm/core/herdr_status_watch.py`. It is a **sibling** of
`herdr_session_watch.py`, not a replacement:

| Module | Job | Cost |
|---|---|---|
| `herdr_session_watch` | stream the *focused* pane's output into its chat | one `agent get` per focused pane |
| `herdr_status_watch` | every *live* pane's status, seat-wide | one `agent list` for the whole workspace |

### The mapping

| Herdr status | OS seat status | Affordance |
|---|---|---|
| `working` | `working` | busy — the rail already animates it via `lib/agentTurns` |
| `blocked` | `waiting` | a "?" indicator: *this needs you* |
| `done` | `finished` | **unread** on the seat, through the existing `swarm_unread_agents` store |

Reuse, not reinvention: the unread mark goes through `lib/unreadAgents`
(`markAgentUnread`), so the rail's existing blue dot lights with **no rail
change and no second store**. Only the "waiting on a human" state is new,
because the rail had no vocabulary for it.

### Transport

A pane's status belongs to **no conversation**, so it gets its own
**push-only socket** rather than riding the SPA multiplex:

```
ws(s)://<host>/ws/herdr-status/
server → client: {"type": "herdr_status", "seat_id": "herdr:w3:p1", "status": "waiting", …}
```

It deliberately does **not** ride `/ws/spa/`. The multiplex is a strict
per-conversation transport whose contract is that every frame is a reply to
something the client asked for — its tests read an exact number of frames, and
unsolicited seat status would interleave frames nobody requested. Arming a
*chat* socket on a page with no chat is its own kind of lie. The status socket
is registered in `swarm/routing.py` and implemented in
`src/swarm/herdr_status_ws.py`.

The client half is `lib/herdrStatusSocket.ts` (connection lifecycle),
`lib/herdrStatus.ts` (the store) and `lib/useHerdrStatusFeed.ts` (the fold),
armed once in `App`.

### Out-of-order updates

Herdr bumps `state_change_seq` whenever a pane changes state, and that counter
is the only ordering signal available. A frame whose seq is **lower** than the
one already recorded is a late duplicate of a reading OS already acted on, and
is dropped — otherwise a slow poll walks a seat backwards (`finished →
working`) and re-lights a dot the operator just cleared. Equal seqes are
re-reads of the same state. A frame with **no** seq cannot be ordered, so it is
accepted on its own terms and the recorded seq is left intact (Herdr omits the
counter on paths with no state to version).

### Fail-open

A missing CLI, a stopped server, an SSH hop that refuses, or a timeout yields
`unknown` for every tracked pane and **no events**. A tracked seat must stop
claiming to be working when OS can no longer ask — silence would read as "busy"
and keep a stale indicator lit. `HerdrStatusMonitor.failure_count` /
`.last_error` say how long OS has been unable to reach Herdr.

## Addable members

`GET /v1/herdr-agents/discover/` runs `herdr agent list` and
`herdr workspace list` and returns addable members (`kind=herdr`,
`remote=""` = localhost). `POST /v1/herdr-agents/` persists a row
(`name`, optional `remote`). Teams (`/teams/#herdr-members`) and the AGENTS
sidepane list persisted rows so an operator can pick them.

Cloud CI must mock `herdr` (no live TUI). SQLite is the default DB; this
feature does not set `DATABASE_URL` or enable Neon.

## API

| Method | Path | Role |
|--------|------|------|
| GET | `/v1/herdr-agents/` | List persisted members |
| POST | `/v1/herdr-agents/` | Add `{name, remote?}` |
| GET | `/v1/herdr-agents/discover/` | Live agent + workspace list |
| GET | `/v1/herdr-agents/status/` | Normalized per-pane status (#1728) |
| GET/DELETE | `/v1/herdr-agents/<id>/` | Read / remove (id or name) |

Operator UI: `/settings/#group-herdr` and Django admin. The DaisyUI SPA
settings sheet is not in this tree (ADR-001); the SPA sidepane still fetches
`/v1/herdr-agents/` so members appear next to blueprints.

## Python wrapper

```python
from swarm.herdr import HerdrClient, extract_prompt_type

client = HerdrClient()  # localhost, no --remote
payload = client.agent_prompt("w3:p1", "HERDR_PING_OK")
assert extract_prompt_type(payload) == "agent_prompted"

client = HerdrClient(remote="matthewh@198.51.100.36")
client.agent_list()  # herdr --remote matthewh@198.51.100.36 agent list

# Settings operate + sidebar chat share this factory (REQ-171C-5 / #614)
client = HerdrClient.from_remote_config()  # remotes.herdr; raises if not added
client.agent_prompt("w3:p1", "HERDR_PING_OK", check_blocked=True, wait=True, until="idle")
```

`swarm.core.remotes.operate(..., "send")` and `chat_herdr` both call
`HerdrClient.from_remote_config`. Chat preflights a blocked pane
(`check_blocked=True`) and passes a **single** `--until idle` (herdr rejects
two `--until` flags). Tests mock the CLI and lock argv — no live LAN.

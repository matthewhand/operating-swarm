# Herdr connectivity (REQ-21)

Open Swarm can drive **Herdr** as a member `kind=herdr` without owning the TUI.

`swarm-cli tui` ([REQ-111](https://github.com/matthewhand/open-swarm/issues/481)
/ [ADR-012](./adr/012-swarm-cli-tui.md)) is **open-swarm’s own** API client
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

**Hop model:** one hop. Open Swarm SSHs to the Herdr host, then talks to Herdr
on that host (official `herdr` CLI). Herdr wraps the CLIs it already manages
there (agy / pi / grok / …). Local Herdr skips SSH and talks to Herdr on this
host. We do not HTTP to a remote Herdr, and we do not SSH past Herdr as a
second product hop.

```bash
# Local Herdr (this host, no SSH). Localhost URL only if you choose that.
swarm-cli remotes set herdr --herdr-mode local

# Remote Herdr — SSH to the Herdr host (env-var name for a key path; never a private key)
swarm-cli remotes set herdr --herdr-mode ssh --ssh-host herdr.example.test --ssh-user herdr --ssh-identity-env HERDR_SSH_IDENTITY
```

Settings → Remotes → **+ Add remote** (or Django `/settings/` **Add Herdr remote**)
does the same `PATCH /v1/remotes/herdr/`. After add, Herdr shows in the Remotes
list. Missing SSH config is a clear error — Open Swarm will not guess a host.

Health / list / send / interrogate (stub SSH in tests; no live LAN in CI):

| Op | Local | Remote (SSH) |
|---|---|---|
| Health | `herdr workspace list` (optional leftover localhost `GET /health`) | `ssh user@host -- herdr workspace list` |
| List | `herdr agent list` (+ workspace list) | same argv over SSH |
| Send | `herdr agent prompt <TARGET> <TEXT>` | same argv over SSH |
| Interrogate CLI X | `herdr agent get <TARGET>` | same argv over SSH |

```bash
swarm-cli remotes health herdr
swarm-cli remotes operate herdr --op list
swarm-cli remotes operate herdr --op send --target w3:p1 --prompt HERDR_PING_OK
swarm-cli remotes operate herdr --op interrogate --target w3:p1
```

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
[CLI reference](https://herdr.dev/docs/cli-reference/). Open Swarm does **not**
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

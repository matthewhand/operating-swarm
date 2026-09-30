# #1360 — Paperclip AI agent management

**Verdict: adapt (concept adoption, not a seat kind).**

## Implementation

Adapted as an operator control plane, not a seat kind:
`src/swarm/core/operator_plane.py`, API under `/v1/operator-plane/`,
design note [docs/OPERATOR_PLANE.md](../OPERATOR_PLANE.md). `paperclip` is
not in `REMOTE_IMPL_IDS`.

* Per-seat and per-team token and cost-micros budgets. A hard-stop refuses
  the debit that would pass the limit and blocks later routine fires until
  an operator resets usage or raises the limit.
* Atomic routine checkout (in-process lock plus `flock` on this host) so an
  overlapping fire does not run the instruction twice.
* Revisioned approval gates. Rollback appends a new approved revision that
  restores an earlier approved snapshot.
* Portable `os-org-pack` export/import. Secrets are scrubbed. Team id
  collisions rename, skip, or error. Duplicate routines are skipped.

The Paperclip HTTP adapter stays a watch item. Its endpoints were not
verified, and this does not call them.

## What it is

Paperclip is an MIT-licensed, self-hosted **control plane for teams of AI agents**
— "if OpenClaw is an *employee*, Paperclip is the *company*". A Node.js server +
React UI orchestrates agents into an org: goals, an org chart with roles and
reporting lines, per-agent budgets, approval gates, routines, tickets, and
audit logs.

- Repo: <https://github.com/paperclipai/paperclip> (README, MIT, ~87.8k stars as of
  fetch). Site: <https://paperclip.ing>
- Four pillars: agentic task manager, org chart, agent training/evals, "agentic
  OS" (runtime, sandboxing, MCP, cost controls).

Note: `paperclip.inc` is a **different commercial product** and its homepage says
it shuts down 2 Oct 2026 (<https://paperclip.inc>). Do not conflate the two. The
OSS project is `paperclipai/paperclip` / paperclip.ing. *(The relationship
between the two is unverified.)*

## Protocol / SDK / auth surface

From the repo README (primary):

- **Runtime:** Node.js 24.11+, pnpm; `pnpm dev` starts the API server at
  `http://localhost:3100` with an embedded PostgreSQL (production: bring your own
  Postgres). Install via `install.sh`, `npx paperclipai onboard`, or Docker.
- **Auth:** two deployment modes — "trusted local" (loopback, fastest first run)
  or "authenticated/private" (`--bind lan|tailnet`). Model includes board users,
  **agent API keys**, **short-lived run JWTs**, company memberships, invite
  flows. Every mutating request is traced to an actor.
- **Agent integration:** "bring your own agent" via **adapter plugins**
  (`adapter-plugin.md`) and an out-of-process **plugin system**. Documented
  adapters: Claude Code, Codex, CLI agents (Cursor/Gemini/bash), HTTP/webhook
  bots (OpenClaw). "If it can receive a heartbeat, it's hired."
- **Run model:** DB-backed heartbeat wakeup queue (coalescing, budget checks,
  workspace resolution, secret injection, skill loading, adapter invocation);
  event-based triggers (task assignment, @-mentions); scheduled routines
  (cron/webhook/API triggers).
- **Observability:** opt-in OpenTelemetry (traces) and Sentry; anonymous
  telemetry with a documented data contract.
- **Interchange:** "companies.sh" export/import of orgs, agents, skills,
  projects, routines, issues with secret scrubbing + collision handling.

No public REST endpoint reference was fetched, so the exact API paths/headers are
**unverified**.

## Mapping to Operating Swarm

Paperclip is a **peer operator control plane**, not a model provider, so it does
not map onto a seat kind directly. Its concepts map onto existing OS primitives:

| Paperclip concept | OS primitive (in-tree) |
|---|---|
| Org chart, roles, reporting lines | Roles (`docs/AGENT_ROLES.md`) + team rosters (`docs/TEAM_ROSTERS.md`) |
| Heartbeats + routines (cron/webhook) | `src/swarm/core/routines.py`, `schedule_engine.py`, `routine_jobs.py` |
| Tickets / atomic task checkout | Routines + mailbox (`agent_mailbox.py`); no atomic checkout lock |
| Agent budgets + hard stops | **Gap** — no per-seat cost hard-stop primitive found |
| Approval gates / review stages | `tool_gate.py`, gate/skeptic roles, `consensus.py` |
| Portable company templates | Marketplace OS team packs (`marketplace.py`) — partial |
| Activity/audit log | `activity_log.py`, `session_logger.py` |

Model namespace: Paperclip never pins its own models — agents "bring their own
prompts, models, and runtimes". So there is nothing to add to the OS model
namespace; if Paperclip is reached as a remote, its `remote` namespace would only
admit ids its config declares.

## Proposed integration sketch

Two independent options; do the first now, the second only if a concrete need
appears:

1. **Concept adoption (recommended, doc-only).** Add an OS design note proposing:
   - per-seat/per-team **budget + hard-stop** (Paperclip's budget policy model);
   - **atomic task checkout with execution locks** for routines to avoid double-work;
   - **revisioned approval gates with rollback**;
   - **portable, secret-scrubbed org/team export** extending OS team packs.
2. **Remote adapter (watch).** Only if Paperclip exposes a stable programmatic
   agent API: add impl id `paperclip` (HTTP) to `REMOTE_IMPL_IDS` and implement
   health/list/send by mapping OS `send` → Paperclip task creation, `list` →
   its agents/issues. This depends on endpoints we have **not verified**.

## Open questions / unknowns

- Exact Paperclip REST endpoints, auth header format, and agent-adapter wire
  protocol — **unverified** (no API reference fetched).
- Heartbeat wire format and whether an external caller can trigger a heartbeat
  programmatically — **unverified**.
- Whether Paperclip's HTTP/webhook bot surface can accept an OS `send` — **unverified**.
- `paperclipai/paperclip` vs `paperclip.inc` relationship, and the shutdown's
  impact on the OSS project — **unverified**.
- Multi-organization isolation value for OS multi-tenant hosting — needs product decision.

## Sources

- <https://github.com/paperclipai/paperclip>
- <https://paperclip.ing>
- <https://docs.paperclip.ing>
- <https://paperclip.inc>

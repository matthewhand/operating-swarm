# Glossary (v1 product vocabulary)

Short definitions that match the code and APIs. Prefer these names in docs and UI copy.

Related: [ADR-001 — Primary UI is Django; SPA Chat only](./ADR-001-primary-ui.md), [ADR-006 — API vs Blueprint kinds](./adr/006-api-vs-blueprint-kinds.md) (REQ-193).

## Harness kind (CLI / API / Blueprint / Remote)

**Today (`main`):** user-facing kinds are **API | CLI | Remote**. Stored `api` is the leftover bucket — coded blueprints, personality/swarm designs, and the Add-agent “API” form (which writes a custom `BlueprintBase`) all classify as API. There is no first-class “wire this OpenAI-compat endpoint” seat.

**Target (ADR-006):** four kinds.

| Kind | Meaning |
|------|---------|
| **CLI** | Host executable (grok, agy, …). |
| **API** | Inference seat: OpenAI-compat base URL / model / key env. Chat completions. Not a graph. |
| **Blueprint** | Programmatic recipe (`BlueprintBase`: openai-agents handoffs, MoA, custom Python, …). |
| **Remote** | Abstract harness ([ADR-011](./adr/011-remote-harness.md)). Implementations: Hermes, OpenMousBot, Rakazo, Herdr, nested swarm — not extra kinds. |

Until Phase 1/2 land, UI copy and classifiers still say “API” for recipes. Prefer the target names in **new** docs.
Related: [ADR-001 — Primary UI is Django; SPA Chat only](./ADR-001-primary-ui.md);
[ADR-003 — Desktop packaging](./adr/003-desktop-packaging.md) (planned Windows pane of glass).
Chat list windowing: [ADR-004](./adr/004-virtualized-chat-history.md) (REQ-163).

## Harness type (API / CLI / remote)

Three ways an agent runs. **API** (OpenAI-compatible / blueprints) is the only
type that can execute an openai-agents **handoff / as-tool graph**. **CLI**
(`grok` / `agy` / …) and **Remote** (one interface; Hermes / OpenMousBot / Herdr / … implement it) stay
native sessions — the framework is not injected into those harnesses. A
**cross-type team** may still mix all three for coordination; only API
members own the programmatic topology. See
[openai-agents-handoff-graphs](./examples/openai-agents-handoff-graphs/README.md)
(REQ-156). Kind-base templates: [ADR-005](./adr/005-kind-bases.md) (REQ-159).

## Kind base (`ApiKindBase` / `CliKindBase` / `RemoteKindBase`)

Documented subclass templates over `BlueprintBase` (`swarm.core.kind_bases`).
Support and NL builders **prefer these** instead of inventing a fourth
harness from the raw base. Only `ApiKindBase` fully hosts openai-agents
graphs. See [ADR-005](./adr/005-kind-bases.md).

## Handoff graph

A declared list of directed openai-agents `handoff` (or `as_tool`) edges
among API seats. Forced sequence = each seat has only the next hop
(BA → Engineer → Tester). Circular skeptic = last reviewer may punt back
to an earlier role. Tests lock live `Handoff.agent_name` against the JSON.
This is **not** the peer mailbox (`list_agents` / `send_message`, REQ-153 / #561). Mailbox tools are a team-scoped API↔API channel with optional whitelist/blacklist ACL (REQ-162 / #573) and optional rail-section internal-only lock (Issue #163); see [ADR-009](./adr/009-peer-mailbox.md) and [PEER_MAILBOX.md](./PEER_MAILBOX.md).

## Skill (`SKILL.md`)

A directory under `<project>/skills` with a `SKILL.md` (Anthropic Agent Skills format). Discovered by `swarm.core.skills.discover_skills` / `GET /v1/skills/`. Attached with `skill` / `skills` params on CLI and today's Blueprint-backed API seats. Chat chips + popup: [docs/SKILLS.md](./SKILLS.md). Not a harness kind. True inference-only API seats (ADR-006 Phase 2) do not attach skills yet.

## Blueprint

A discoverable `BlueprintBase` subclass (`swarm.core.blueprint_base`) that defines a runnable agent workflow: agents, tools/MCP requirements, coordination, and optional config. Selected by OpenAI-compatible `model` id on `/v1/chat/completions` and `/v1/responses`, or launched with `swarm-cli`. Blueprints are **CLI/API only** — they do not ship a webpage; the Grok-like WebUI is product chrome. Live discovery lives in `swarm.core.blueprint_discovery` (the old `swarm.extensions.blueprint` path was removed). New recipes should subclass a [kind base](#kind-base-apikindbase--clikindbase--remotekindbase) (ADR-005). Do not add `kind=webui`.

A Blueprint **catalog** row is a template. A Blueprint **agent** (ADR-006) is a seat that runs a chosen recipe. The AGENTS rail and Search Bots list only recipes with `metadata.rail: true` (default deny). Catalog stays on `GET /v1/blueprints/`, Settings, and Add-agent ([#595](https://github.com/matthewhand/open-swarm/issues/595) / REQ-170). Add-agent CLI/API creates are merged into that list with `rail: true` so the same filter can show them ([#607](https://github.com/matthewhand/open-swarm/issues/607) / REQ-171B).

**Support NL create (REQ-158 / #567):** the happy path is ask **Support** in natural language. Support persists a custom `ApiKindBase` seat. The user does not write Python; **View / edit code** is optional. See [SUPPORT_NL_BLUEPRINTS.md](./SUPPORT_NL_BLUEPRINTS.md).

## Team (handoff members — REQ-11)

A **Team** wires **API** (inference), **CLI**, **Blueprint** (programmatic), and **remote** agents (Hermes, OpenMausBot, Rakazo, nested open-swarm) so they can **see and talk** to each other via openai-agents **handoff / as_tool**. On `main` today, “API agents” in this sentence still means the conflated recipe bucket — see [ADR-006](./adr/006-api-vs-blueprint-kinds.md). Remotes are Team *members* (`consult_hermes`, `consult_omb`, `consult_rakazo`, `consult_swarm`). Place or unplace them with `swarm-cli remotes place|unplace` / `PATCH /v1/agent-team/` (`agent_team.members` in `swarm_config.json`). Blueprint: `remote_harness`. Nested swarm is a network remote (own process, own DB); do not auto-add this instance as its own remote.

This is **not** the Django `/teams/` + `/v1/teams/` JSON registry.

## Profiles (`/teams/` — name collision)

`/v1/teams/` and the Django `/teams/` admin store **LLM-profile aliases** (`id`, `description`, `llm_profile`) in `teams.json`. They run through `DynamicTeamBlueprint` — a thin chat proxy to a profile. Prefer calling that surface **Profiles** in new copy. Do not call those aliases a Team.

## Team roster (composition) / Chief of Staff

A **team roster** (`team_rosters.json`, `/v1/team-rosters/`) is a composition
of members `{id, name, kind: api\|cli\|remote\|team\|herdr, role, source}`. This is
**not** the `/v1/teams` alias. `kind=team` + `team_id` nests a child roster.
A roster may optionally name one **API or CLI** member as Chief of Staff and
store team-scoped how-to-use-the-roster instructions. The same agent id may
sit on two teams; each team's CoS brief steers that roster only. CoS is not
auto-assigned. Remotes cannot be CoS until runtime can inject a brief.
ADR-006 adds `kind=blueprint` and redefines `kind=api` as an inference seat
(Phase 1/2). Existing `kind=api` roster rows that point at recipes migrate to
`blueprint`.

**Isolation (REQ-28):** members of Team A cannot `handoff` / `as_tool` to Team B
unless B is a **direct child** of A or the caller is `chief_of_staff` (`cos`,
`chief`). Parent talks to the child team as one member (send-to-all on the
child), not automatically every grandchild. See [TEAM_ISOLATION.md](./TEAM_ISOLATION.md).

## Persona / MoA

Two primary multi-agent styles ([SWARM_WORKFLOWS.md](./SWARM_WORKFLOWS.md)):

| Name | Meaning |
|------|---------|
| **MoA** (Mixture of Agents) | Read-only participant seats → orchestrator determination → optional act / scripted `--team` specialists (`swarm.core.moa`, `swarm-cli moa`). |
| **Persona** (agent-as-tool swarm) | A coordinator switches specialists via the `openai-agents` SDK (handoffs / `as_tool()`). Includes blueprints such as `persona_council` (diverse-lens consensus). |

Do not call `/v1/teams` aliases “MoA teams” or “persona teams.”

## Agent role (support / gate / skeptic / engineer / default)

First-class field on an agent spec (`AgentConfig.role`, team `AGENT_SPECS`, `/v1/blueprints/` `role` + `agents[]`). Visual CSS: `os-agent-role-<role>` and `data-role` on the **badge only**. Wiring (openai-agents `as_tool` / handoff only — not extra Grok seats):

* **default** / **none** — ordinary worker / coordinator (no badge)
* **support** — Support seat (REQ-7 / REQ-137). First-run onboarder; also the global create/archive role (REQ-154).
* **gate** (`tool_gate`) — classifies a pending tool call YES/NO (dangerous). Wired → elicit on dangerous. **Unwired → all approved, never prompt.**
* **skeptic** — reviews whether the original prompt was accomplished; on NO, findings go back to the original agent (bounded retries, default 2). On YES, stop — do not nag.
* **chief_of_staff** (`cos`) — talks to any team. API CoS shares Support’s create/archive tools (REQ-154); CLI CoS does not in v1. See [AGENT_LIFECYCLE.md](./AGENT_LIFECYCLE.md).
* **engineer** — implementer seat (software-dev / Chatty). A blueprint may declare this as its default role (REQ-75); the agent editor override still wins.

A blueprint `metadata.role` is applied on create / re-pick unless the operator has explicitly changed Role. Optional `metadata.workflow` is `handoff` or `as_tool` (hint only).

**Invocation (REQ-191):** Mode A = human chat configures/discusses the role (full thread). Mode B = as-tool / handoff uses the caller’s context and the latest message, not the role agent’s configure thread. See [ADR-010](./adr/010-role-agent-invocation-modes.md). Distinct from showoff “Mode A/B” **names** in [SHOWOFF_DEMO_AGENTS.md](./SHOWOFF_DEMO_AGENTS.md).

See [AGENT_ROLES.md](./AGENT_ROLES.md).

## CLI Fusion

Wrapping installed agentic CLIs (`grok` / `claude` / `gemini` / …) behind the OpenAI API and composing them (`cli_agent`, `cli_fusion` panel+judge, `cli_orchestrator`, `cli_map`, …). Config: `cli_agents` (+ fusion blocks) in `swarm_config.json`. Docs: [CLI_FUSION.md](./CLI_FUSION.md). Legacy product phrasing; MoA is the preferred name for read-only consensus.

## Session

A stateful `/v1/responses` record (and related conversation/delegation data) owned by an operator or API-token principal. The Django **Session Explorer** at `/sessions/` is a read-only observability UI over those records — not a chat composer.

**Scale-out chat sessions (REQ-66)** are per-agent websocket conversations (`?session=` on SPA Chat). They are not Session Explorer rows. An agent with more than one of these stays one rail row with stacked avatars.
## CLI session

An id **owned by an agentic CLI** (`--resume` / `--session` / `exec resume` / id file). Open Swarm stores it next to the chat thread (`cli_sessions`) and passes it back so the CLI restores its own context (REQ-52). Select session lists those ids from the CLI’s own list API or session store when supported (#795) — Django recents are not the source of truth for CLI resume. **Quota hop (#531 / REQ-138)** is the opposite move: a CLI/API dropdown switch starts a **new** native session and seeds it from the swarm thread (summary/full, secrets and tool noise omitted). Switching back is also a new session — do not resume the earlier id. Not a Django `conversation_id`, not a `/v1/responses` Session, and not OS `start_new_session` (process-group kill). Remotes keep the remote’s session.

## Herdr member (`kind=herdr`)

A persisted connection to a [Herdr](https://herdr.dev/) pane/agent that Open Swarm drives via the official `herdr` CLI (not a socket protocol). Empty `remote` means localhost (unix sockets, typically `~/.config/herdr/`). **Remote implementation** (REQ-203 / ADR-011): `herdr` is the impl id under user-facing kind **Remote**, not a fifth harness. Add `herdr` in Settings. **Local Herdr** talks to Herdr on this host (no SSH). **Remote Herdr is SSH-shaped** — SSH to the Herdr host, then Herdr’s CLIs there — **not** an HTTP remote like OpenMousBot / Hermes / Rakazo. Missing SSH config is an error, not a silent other-host. Classifiers map `herdr` / `herdr:…` → `remote`. Docs: [HERDR.md](./HERDR.md).

## swarm-cli TUI (REQ-111)

Open Swarm’s own terminal client of the **same HTTP API** as the WebUI: left
agent rail + chat pane ([ADR-012](./adr/012-swarm-cli-tui.md) /
[#481](https://github.com/matthewhand/open-swarm/issues/481)). Interactive in
a TTY (rail sections, hydrate via `GET /chat/thread/`, REST SSE send + stream,
`n`/`s` sessions); `--once` keeps an ASCII dump for CI. No WS cookie jar in
v1 (Wave 3b decided-skip). Distinct from **remote Herdr** (SSH-shaped
`herdr` CLI) and from `swarm-cli launch` (in-process blueprint run).

## Operator UI vs SPA Chat

| Surface | Role (v1) |
|---------|-----------|
| **Operator UI** | Canonical Django/HTMx trailing-slash chrome: `/teams/launch/`, `/teams/`, `/blueprint-library/`, `/agent-creator/`, `/settings/`, `/sessions/`, … ([ADR-001](./ADR-001-primary-ui.md)). |
| **SPA Chat** | React SPA retains `/` (dashboard) and `/chat` (websocket chat) only. Bare `/teams`, `/blueprints`, `/settings`, `/agent-creator` redirect to Django. Do not remount Builder / AgentCreator SPA pages. Large transcripts: planned virtualizer is `@tanstack/react-virtual` ([ADR-004](./adr/004-virtualized-chat-history.md)); not shipped. |

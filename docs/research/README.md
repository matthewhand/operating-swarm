# Research briefs — external agent platforms & templates

Feasibility research for the open research issues #1360, #1363–#1367, plus the
#1378 realtime-voice spike. Platform briefs follow **what it is →
protocol/SDK/auth surface → mapping to Operating Swarm's four seat kinds and
model namespace → verdict → proposed adapter/doc-integration sketch → open
questions**. The #1378 brief is an options matrix against shipped speech
surfaces, not a new seat kind.

Operating Swarm primitives referenced throughout (verified in-tree):

- **Four seat kinds** — `api`, `cli`, `remote`, `team`
  (`src/swarm/core/kind_bases.py`, `KIND_API/CLI/REMOTE/TEAM`).
- **Model namespace rule** — a model id must belong to its provider's namespace:
  `api` = configured LLM profile ids/slugs; `cli` = the CLI's own list/presets/
  configured model; `remote` = only what the remote's config declares; `team` =
  valid iff valid for one member's kind (`src/swarm/core/model_namespace.py`).
- **Remote impl registry** — `REMOTE_IMPL_IDS` = hermes, anythingllm, openwebui,
  flowise, n8n, omb, rakazo, herdr, swarm, trueforge
  (`src/swarm/core/remote_harness.py`, `src/swarm/core/remote_impls/`).
- **Roles** — default, support, gate, skeptic, chief_of_staff, engineer,
  suggestions (`docs/AGENT_ROLES.md`).
- **Team rosters** — `team_rosters.json`, members of kind `api`/`cli`/`remote`
  wired by `handoff`/`as_tool` (`docs/TEAM_ROSTERS.md`).

## Index

| Issue | Brief | Verdict |
|---|---|---|
| #1360 | [Paperclip agent management](./paperclip-agent-management.md) | **adapt** (borrow concepts) |
| #1363 | [Alibaba Open Code Review as agents](./alibaba-code-reviewer.md) | **adapt** (CLI reviewer seat) |
| #1364 | [ORCA AI agents](./orca-ai-agents.md) | **watch** (CLI/skill first) |
| #1365 | [Tencent Octop AI agents](./tencent-octop.md) | **adapt/adopt** (remote impl) |
| #1366 | [Tencent AI templates on GitHub](./tencent-ai-templates.md) | **adapt** (reuse MIT packs) |
| #1367 | [t3code integration](./t3code.md) | **watch** (no stable third-party API) |
| #1378 | [Realtime voice mode (LAN LiteLLM STT/TTS)](./issue-1378-realtime-voice.md) | **adapt** (REQ-77 batch path; no realtime product) |

> Every external claim is cited. Claims that could not be verified from a primary
> source are explicitly marked **unverified**. No APIs were invented.

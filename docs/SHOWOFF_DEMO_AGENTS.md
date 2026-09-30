# Showoff demo agents — two naming modes (REQ-135)

Issue SoT: [REQ-135 #526](https://github.com/matthewhand/open-swarm/issues/526).

**Intent:** Demo roster names make the story obvious at a glance — what
**kind** something is for harness demos; what **role** it plays for team
demos.

Seed is **additive** and labeled **Demo**. It does not rename day-to-day
agents. No secrets: URLs and keys stay placeholders / env. GitHub-only
until an engineer seeds a live box.

Announce GIF [#529](https://github.com/matthewhand/open-swarm/issues/529)
([docs/ANNOUNCE.md](./ANNOUNCE.md), hero
[`docs/assets/readme/announce-bridge.gif`](./assets/readme/announce-bridge.gif))
and near-release media [#456](https://github.com/matthewhand/open-swarm/issues/456)
([`docs/assets/readme/`](./assets/readme/README.md) — posters now, GIF
checklist in [`RECORDING.md`](./assets/readme/RECORDING.md)) should prefer
**Mode A** names on harness rows. The announce film also
shows **OpenCode CLI** (`cli:opencode`) as a Mode A extra — not a default
seed member.

---

## Mode A — mixture of types (kind + backend)

Use when the demo is “CLI vs API vs remote.” Names encode **kind + backend**.
Label **OpenMousBot**, never OMB. Same pattern for Rakazo / Herdr remotes
when those seats are shown.

| Id | Display name | Kind | Source (no secrets) |
|----|--------------|------|---------------------|
| `grok-cli` | Grok CLI | `cli` | `cli:grok` |
| `antigravity-cli` | Antigravity CLI | `cli` | `cli:agy` |
| `litellm-api` | LiteLLM API | `api` | `blueprint:sdlc_handoff` |
| `hermes-remote` | Hermes Remote | `remote` | `placeholder:remote:hermes` |
| `openmousbot-remote` | OpenMousBot Remote | `remote` | `placeholder:remote:omb` |

Roster: [`docs/examples/openai-agents-handoff-graphs/demo-harness-kinds.json`](./examples/openai-agents-handoff-graphs/demo-harness-kinds.json)
(`Demo Harness Kinds`).

Do **not** put role names (`Engineer`, `QA`) on this roster. A harness row
named Engineer hides the type story.

---

## Mode B — teams / blueprints (role / persona)

Use when the demo is a team or blueprint workflow. Names are **roles**,
not kinds. Default seed is the practical set. Funny names are an
alternate only — do not ship both in one roster.

| Id | Default (practical) | Alternate (funny) |
|----|---------------------|-------------------|
| `cos` | Chief of Staff | Ringmaster |
| `ba` | BA | Requirements Nag |
| `engineer` | Engineer | Code Monkey |
| `tester` | Tester | QA Hawk |
| `skeptic` | Skeptic | Professional Doubter |

Rosters:

- [`demo-sdlc-pipeline.json`](./examples/openai-agents-handoff-graphs/demo-sdlc-pipeline.json) — CoS + BA → Engineer → Tester
- [`demo-sdlc-skeptic-loop.json`](./examples/openai-agents-handoff-graphs/demo-sdlc-skeptic-loop.json) — same plus Skeptic punt-back

CoS is selected via `chief_of_staff_id` (team designer, REQ-107 / #475).
The brief is team-scoped and contains no secrets.

Do **not** name a Mode B seat `LiteLLM API` — that confuses the team story.

---

## Intentional mix

[`demo-bridge.json`](./examples/openai-agents-handoff-graphs/demo-bridge.json)
is the one roster that **mixes on purpose**: Chief of Staff (persona)
coordinates **Grok CLI** and **Hermes Remote** (kind-clear). That is the
announce-bridge beat, not a Mode A or Mode B roster.

---

## Seed / reset demo agents

Fixture JSON (rail first-load, labeled Demo):

- [`webui/frontend/public/team_rosters.json`](../webui/frontend/public/team_rosters.json)
- [`src/swarm/static/team_rosters.json`](../src/swarm/static/team_rosters.json)

The empty-state stub `demo-team` (Codey / Stewie) stays so existing
sidepane tests keep a generic team. It is **not** a Mode A/B showoff roster.

Reset / upsert only `demo-*` ids (never day-to-day rosters):

```bash
# See what would be written (no disk write)
uv run python scripts/seed_demo_agents.py --dry-run

# Additive upsert
uv run python scripts/seed_demo_agents.py

# Replace existing demo-* ids only
uv run python scripts/seed_demo_agents.py --reset
```

`scripts/seed_req156_demo.py` is the same path (`--overwrite` = `--reset`).
Do not run this against a live `:8001` / FF box from CI. Engineer seeds
after merge. Placeholders only — no hostnames, tokens, or LAN dumps.

---

## Where names must appear

After seed (or from the fixture JSON):

- **Rail** — team rows `Demo Harness Kinds`, `Demo SDLC Pipeline`,
  `Demo SDLC Skeptic Loop`, `Demo Bridge`. CoS rail injection uses the
  member display name (`Chief of Staff`) when that seat is not already
  a catalog agent.
- **Favourites** — pinning a Demo team keeps that team title.
- **Chat header** — team title plus the unlabeled member dropdown
  (`Grok CLI (cli/default)`, `BA (api/default)`, …).

Member `name` is part of the roster contract and survives
`normalize_member` / `GET /v1/team-rosters/`. Missing name falls back to
`id` (never invents a secret).

---

## OpenCode / Space Bunny dogfood (#1747)

Opt-in roster (not a default seed): [demo-opencode-dogfood.json](./examples/openai-agents-handoff-graphs/demo-opencode-dogfood.json).
Runbook + seat mapping + **cap 3**: [docs/runbooks/GAMINGPC_SPACE_BUNNY_OPENRIG.md](./runbooks/GAMINGPC_SPACE_BUNNY_OPENRIG.md).

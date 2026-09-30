# #1366 — Tencent AI templates on GitHub (reuse for Operating Swarm)

**Verdict: adapt — reuse the MIT template content as OS skill/blueprint packs; watch the teamai-cli distribution model.**

## What it is

Tencent publishes **TeamAI** — a CLI + reference template that makes a team's AI
assets (skills, rules, docs, env, agents, hooks, MCP servers, models) portable
across coding agents by storing them in **one git repo**:

- `Tencent/teamai-cli` (MIT) — "Make Every Team AI Native", npm `teamai-cli`.
  Repo: <https://github.com/Tencent/teamai-cli>
- `teamai-hub/teamai-template` (MIT, **template** repo) — reference template with
  production-ready skills, rules, and review agents.
  Repo: <https://github.com/teamai-hub/teamai-template>
- `teamai-hub/teamai-cli-dev` — dev team repo.

The template bundles (primary source = template README):

- **skills/** namespaced by upstream: `ecc/` (`backend-patterns`, `api-design`,
  `database-migrations`, `error-handling`, `tdd-workflow`, `security-review`) and
  `mattpocock/` (`tdd`, `research`, `domain-modeling`, `grill-me` + `grilling`).
- **rules/common/** — shared baseline (coding style, code review, testing, git
  workflow, security, performance).
- **agents/** — review subagents: `code-reviewer`, `database-reviewer`,
  `security-reviewer`.
- **Environment variables** — examples only.

License/attribution: content adapted from
[`affaan-m/everything-claude-code`](https://github.com/affaan-m/everything-claude-code)
and [`mattpocock/skills`](https://github.com/mattpocock/skills), both **MIT**
(full texts + `ATTRIBUTION.md` mapping included). MIT permits reuse with notice
retention.

## Protocol / SDK / auth surface

- **Distribution:** `npm install -g teamai-cli`; `teamai init <git-repo-url>`
  (project scope default, or `--scope user`). Team members' agents auto-pull the
  latest skills/rules on each session.
- **Git-host auth:** works with GitHub, GitLab, GitCode, CNB, TGit, or a private
  Git service — write access to the shared repo is the only requirement. No
  vendor API or vendor account.
- **Agent support:** Claude Code, Codex, Cursor, GitHub Copilot CLI, CodeBuddy,
  WorkBuddy, **OpenCode**, Pi, OpenClaw, Hermes, DeepSeek Harness, Qoder(+CN),
  Kiro, ZCode, Oh My Pi — capability matrix per asset type in the README.
- **AI-facing entry point:** a `/teamai` skill (`skills/teamai`) that installs and
  manages the team repo from inside an AI tool.

There is **no Tencent Cloud account, API key, or hosted service** implied — it is
a git-distributed configuration layer.

## Mapping to Operating Swarm

TeamAI is **not a seat kind**; it is a **distribution/packaging mechanism** for
agent resources. Each asset type maps onto an OS primitive:

| TeamAI asset | OS primitive |
|---|---|
| skills | Skills system (`src/swarm/core/skills.py`, `skill_attach.py`, `docs/SKILLS.md`) |
| rules | persona/dev prompts + `blueprint_base` system prompts |
| agents (`code-reviewer`, `security-reviewer`, `database-reviewer`) | Roles / blueprints (`docs/AGENT_ROLES.md`, `agent_roles.py`) — reviewer agents fit `skeptic`/`gate`/`engineer` |
| MCP servers | MCP registry (`src/swarm/core/mcp_registry.py`, `mcp_server_config.py`) |
| models | LLM profiles / model namespace (API-side) |
| team repo as a whole | Marketplace **OS team pack** (`marketplace.py`) |

Feasibility of reuse is high because the bundled content is MIT and
agent-agnostic Markdown; the main work is **format translation** (Claude-style
skills/rules/agents → OS skill/blueprint schema).

## Proposed integration sketch

```text
1. Vendor a curated subset (with ATTRIBUTION.md + MIT notices) into:
     docs/ or a skill pack under the OS skills catalog
   - rules/common → a shared baseline persona fragment
   - agents/*     → three reviewer blueprints (skeptic/gate/engineer roles)
   - skills/ecc/* + skills/mattpocock/* → OS skill entries

2. Optional importer: a small routine/tool that reads a teamai repo layout
   (skills/, rules/, agents/, mcp config) and seeds OS skills + blueprints,
   using the same shape as an OS marketplace team pack.
   Do NOT re-implement teamai-cli; consume its directory format.

3. Keep model pins API-namespace only; never merge CLI/remote ids.
```

## Open questions / unknowns

- Exact on-disk format of skills/rules/agents in the template (Anthropic skills
  vs other) — **unverified** (only README inventory fetched).
- Whether teamai "models" config is a model-pin file OS could consume — **unverified**.
- Whether `teamai init` writes files OS could diff/import, or a proprietary layout —
  **unverified**.
- Attribution requirements per file (ATTRIBUTION.md not fetched) — confirm before
  vendoring.
- "Team Context (beta)" / "Team Improvement (beta)" have no API; only git assets
  are reusable today — **unverified**.
- No Tencent-specific templates beyond teamai-hub were found; if the issue meant
  Tencent Cloud ADP agent templates (<https://adp.tencentcloud.com/en>) that is a
  different, hosted product — **needs author confirmation**.

## Implementation

Adapted in-tree. `teamai-cli` stays a packaging layout, not a seat kind.

- Skills: `skills/ecc/`, `skills/mattpocock/`, and `skills/teamai-baseline/`
  (the `rules/common/` persona fragment).
- Reviewer blueprints: `code_reviewer` (skeptic), `security_reviewer` (gate),
  `database_reviewer` (engineer). Prompts are the vendored agent markdown.
- Importer: `src/swarm/core/teamai_import.py`, command `swarm-cli teamai-import`.
  It copies skills, skips hooks, lists MCP servers without installing them,
  and drops model pins that are outside the API namespace (the template's
  `sonnet` pin is dropped).
- Notices: `packs/teamai/ATTRIBUTION.md`, `packs/teamai/LICENSE`,
  `packs/teamai/LICENSE-mattpocock`.

## Sources

- <https://github.com/Tencent/teamai-cli>
- <https://github.com/teamai-hub/teamai-template>
- <https://github.com/teamai-hub/teamai-cli-dev>
- <https://github.com/affaan-m/everything-claude-code>
- <https://github.com/mattpocock/skills>

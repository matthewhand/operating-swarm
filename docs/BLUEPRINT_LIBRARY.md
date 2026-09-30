# Blueprint Library

A menu of the multi-agent workflows ("blueprints") Operating Swarm ships, each chosen
to demonstrate a specific framework feature. Blueprints are **CLI/API only**:
pick one by its `model` name over the OpenAI API, run it with
`swarm-cli launch <name>`, or use it as a starting point for your own. They do
not ship a webpage. The Grok-like WebUI (`/` + `/chat`) is the product chrome.
The AGENTS rail lists **seats** (`metadata.rail: true`), not this whole catalog
(REQ-170 / #595). Add-agent CLI/API customs are merged into `GET /v1/blueprints/`
with `rail: true` (REQ-171B / #607).

**Status legend**

| Mark | Meaning |
|------|---------|
| ✅ | Deep tests + verified live (incl. grok where CLI-backed) |
| 🟢 | Discovered and answers over the API (smoke-matrix verified) — dedicated feature test pending |
| 🔧 | Present in-tree but **not discovered** (needs a fix to join the library) |
| 📋 | Removed in the FOSS cleanup — reintroduction candidate (resurrect, modernize, test) |

This is a living document: the build-out loop adds a dedicated feature test (and
grok verification for CLI-backed ones) to each 🟢 row, fixes the 🔧 rows, and
reintroduces 📋 rows that demonstrate a feature not already covered.

---

## The permutation matrix (the spine of the library)

The library is organized as a progression of permutations — *how many agents* ×
*what backend* — from the trivial (1 agent, 1 endpoint) to the complex (many
agents mixing REST and CLI). Every cell should have at least one working,
tested demonstrator.

| Agents ↓ \ Backend → | **REST** (LLM API, openai-agents) | **CLI** (grok / claude / …) | **Mixed** (REST + CLI) |
|---|---|---|---|
| **1 agent** | `chatbot` — 1 agent, 1 REST endpoint ✅ | `cli_agent` — 1 CLI ✅ | — (n/a for a single agent) |
| **Few agents (team)** | `geese` / `zeus` — REST team, agent-as-tool / handoff 🟢 | `cli_fusion` (consensus) · `cli_orchestrator` (routed) ✅ | **`hybrid_team`** — REST coordinator + grok persona + consensus panel ✅ |
| **Many agents (orchestrated)** | `whiskeytango_foxtrot` — hierarchical REST 🟢 | `cli_map` — decompose/distribute ✅ | **`hybrid_swarm`** — REST orchestrator over REST agents + CLI consensus panel ✅ |

**Every cell now has a working, tested demonstrator.** The CLI column and the
Mixed column are complete; most of the REST column is smoke-verified. The
**Mixed** blueprints prove the headline capability — a REST coordinator reaching
for grok CLI personas and a consensus panel mid-run, via `swarm.core.cli_tools`.
Verified live: `hybrid_team` ran a real grok persona ("Rome") and a real
consensus while the REST coordinator step degraded gracefully (the REST half is
wired to a real openai-agents Agent; it needs your LLM key to produce a live
plan, and falls back cleanly without one).

> Note: `digitalbutlers` and `flock` are present in-tree but don't subclass
> `BlueprintBase`, so they aren't discovered — they're stale stubs, candidates
> for a rebuild into specific matrix cells rather than a quick fix.

---

## CLI Agent Fusion — drive your installed CLIs (claude / grok / gemini / …)

| Blueprint | Feature it demonstrates | Status |
|---|---|---|
| `cli_agent` | One external CLI behind the OpenAI API; streaming; failover | ✅ |
| `cli_fusion` | Multi-CLI **consensus** (panel → judge → synthesize) | ✅ |
| `cli_orchestrator` | **Granular** consensus — cheap router escalates only hard questions | ✅ |
| `cli_map` | **Decompose → distribute → reduce** (map-reduce across CLIs) | ✅ |

All four verified live with **grok** driving every role (panelist, judge, router, planner, worker, reducer).

## Consensus modes (a second axis — partly built, partly roadmap)

Consensus isn't one thing; it's a *mode* you select per call. The same persona
named `coder` can be invoked many ways, and each is a blueprint permutation:

| Mode | How you call it | What happens | Status |
|---|---|---|---|
| **Single** | `coder` | one inference | ✅ `cli_agent` |
| **Agent-designated consensus** | `coder` (config `consensus: true` / `["grok","claude"]` / `{panel,judge}`) | calling the agent runs a heterogeneous **panel of CLIs** and synthesizes; preferred whitelist falls back to all-available | ✅ (0.4.4) |
| **Self-consensus (homogeneous)** | `coder` + `consensus: N` | run the **same persona N times** (sampling variance) and synthesize — "many inferences, one persona" | ✅ (0.4.5) |
| **Call-time flag** | `coder` + `params.consensus` | consensus chosen **per request** (overrides config; falsy forces single) | ✅ (0.4.5) |
| **Native (built-in) consensus** | a CLI whose own flag fans out (grok `--best-of-n N`, `--check`) | the **CLI itself** runs N candidates internally and picks the best — one call | ✅ catalog-aware (0.4.5) |
| **Orchestrated multi-persona** | `coder` + `architect` (+ …) | an **orchestrator** agent runs each *distinct* persona and does the consensus/synthesis across them | 🟢 `cli_fusion` / `cli_orchestrator` already panel distinct agents; formalize "named personas" |

**Framework vs native, and they compose.** Framework consensus (rows 2–4) is the
framework orchestrating multiple calls and synthesizing — works for any CLI.
Native consensus is the CLI's *own* internal fan-out via a flag — only for CLIs
that have one. They stack: a `consensus: 3` agent whose CLI also carries
`--best-of-n 2` runs 3 framework samples × 2 native candidates each.

The shared engine for every mode is `swarm.core.consensus.run_consensus()`; the
modes differ only in how the *panel* is assembled (one CLI, N copies of one CLI,
a whitelist of CLIs, or a set of named personas an orchestrator coordinates).
Each will get a demonstrating blueprint + a grok-verified test, like the rest of
the matrix.

## Hybrid (REST + CLI) and minimal templates

| Blueprint | Feature it demonstrates | Status |
|---|---|---|
| `chatbot` | The minimal single-agent REST template (1 agent, 1 endpoint) | ✅ |
| `hybrid_team` | A REST coordinator delegating to grok CLI personas + a consensus panel | ✅ |
| `hybrid_swarm` | A REST orchestrator routing across REST sub-agents and a CLI consensus panel | ✅ |

The hybrids' REST half is wired to a real openai-agents Agent and degrades
gracefully without an LLM key; the CLI half is verified live with grok.

## Coding & developer workflows

| Blueprint | Feature it demonstrates | Status |
|---|---|---|
| `codey` | Code generation + semantic code search/analysis; approval-mode | 🟢 |
| `rue_code` | Code execution + filesystem interaction | 🟢 |
| `whinge_surf` | Async subprocess job management (launch / poll / review) | 🟢 |

## Multi-agent coordination & delegation

| Blueprint | Feature it demonstrates | Status |
|---|---|---|
| `geese` | Researcher/coordinator pattern with memory | 🟢 |
| `zeus` | General-purpose team launcher (agent-as-tool delegation) | 🟢 |
| `dynamic_team` | Dynamically-registered team from a configured LLM profile | 🟢 |
| `chucks_angels` | Themed task coordination | 🟢 |
| `digitalbutlers` | Butler-style delegation | 🔧 present, not discovered |
| `flock` | Agent flock/swarm coordination | 🔧 present, not discovered |

## Structured output, tools & integrations

| Blueprint | Feature it demonstrates | Status |
|---|---|---|
| `suggestion` | **Structured output** via `Agent(output_type=…)` | 🟢 |
| `jeeves` | Private web search (DuckDuckGo) + home automation delegation | 🟢 |
| `stewie` | **MCP** integration (WordPress CMS via MCP tools) | 🟢 |
| `whiskeytango_foxtrot` | Hierarchical multi-agent + SQLite + web scraping | 🟢 |
| `poets` | SQLite-backed collaborative creative writing | 🟢 |

## Reintroduction candidates (removed in the FOSS cleanup)

Each is a 📋 candidate — resurrect from git history, modernize to current
`BlueprintBase`, add a feature test. Ordered by the feature they'd add:

| Blueprint | Feature it would demonstrate |
|---|---|
| `echocraft` | Minimal "hello world" blueprint (the simplest template) |
| `chatbot` | Bare single-agent chat |
| `mcp_demo` | Focused MCP-server usage demo |
| `nebula_shellz` | Agent-as-tool + `@function_tool` for shell/code |
| `monkai_magic` | External-CLI function tools (AWS/Fly/Vercel cloud ops) |
| `mission_improbable` · `burnt_noodles` · `dilbot_universe` · `gaggle` · `gotchaman` · `omniplex` · `unapologetic_press` | Misc themed multi-agent demos — triage each for a unique feature before resurrecting |

> `family_ties` was **renamed** to `stewie` (already in the library), not removed.

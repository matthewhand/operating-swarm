# Blueprints Overview

Discoverable `BlueprintBase` packages under this tree (OpenAI-compatible `model`
ids). Blueprints are **CLI/API only** — they do not ship a webpage; the
Grok-like WebUI is product chrome. Vocabulary:
[docs/GLOSSARY.md](../../../docs/GLOSSARY.md) (Blueprint vs `/v1/teams`
**LLM-profile alias**). Status evidence:
[FEATURE_STATUS.md](../../../FEATURE_STATUS.md) §9.

Shared helpers live in `common/` (not a blueprint). Empty husk directories without
`blueprint_*.py` were deleted — do not restore.

## Two workflow families

See **[docs/SWARM_WORKFLOWS.md](../../../docs/SWARM_WORKFLOWS.md)**.

| Model | What it is | Write policy | Entry points |
|-------|------------|--------------|--------------|
| **A. Orchestrated consensus (MoA)** | Subagents opine; orchestrator decides | Subagents **read-only**; orchestrator acts | `moa/`, `moa_orchestrator/`, `hybrid_moa/`, `swarm-cli moa`, `swarm.core.moa` |
| **B. Persona / agent-as-tool swarm** | Coordinator switches specialists via `openai-agents` | Specialists **read/write** tools | Most other dirs below (codey, rue_code, geese, zeus, persona_council, …) |

Legacy name **CLI Fusion** still appears as blueprint/alias ids (`cli_fusion`,
`cli_ensemble`, …); prefer **MoA** for read-only consensus ([GLOSSARY](../../../docs/GLOSSARY.md)).

## Discoverable packages (2026-08-18)

Canonical directory names (each has `blueprint_<name>.py`). Discovery also
registers aliases (e.g. `moa` ← `cli_fusion` / `ensemble`; `dynamic_team` ←
`dynamic-team`; `hybrid_moa` ← `moa_hybrid`).

### MoA / hybrid / orchestration

| Dir | Notes |
|-----|--------|
| `moa` | Read-only mixture-of-agents; aliases include `cli_fusion`, `cli_ensemble`, `ensemble`, `fusion`, `mixture_of_agents` |
| `moa_orchestrator` | MoA then scripted team path; aliases `moa-orch`, `agents_moa` |
| `hybrid_moa` | Hybrid consensus; aliases `moa_hybrid`, `hybrid-consensus` |
| `hybrid_team` / `hybrid_swarm` | Hybrid team / swarm variants |
| `cli_agent` / `cli_map` / `cli_orchestrator` / `cli_pipeline` / `cli_planner` / `cli_recurse` / `cli_roundtable` | CLI-wrapping strategy family (also `cli_fusion` / `cli_ensemble` **packages** remain as thin entry points) |
| `fs_introspect` | Filesystem introspection demo |
| `persona_council` | Persona / agent-as-tool council |

### Persona demos & utilities

| Dir | Notes |
|-----|--------|
| `support` | Onboarding (`role=support`); default Chat + top-of-sidebar |
| `gate` | Stub `role=gate` marker (approval classifier; `submit_gate_verdict`) |
| `skeptic` | Stub `role=skeptic` marker (retry check; `submit_skeptic_verdict`) |
| `chatbot` | Minimal single-agent chat |
| `suggestion` | Structured JSON suggestion (`suggestion` CLI) |
| `codey` | Coding workflow (`codey` CLI) |
| `software_dev` | CoS / engineer / skeptic team via openai-agents as-tool (REQ-36; Issue #348). `params.workdir` / `remote_workdir` / SSH keys (and other workspace/context keys) do **not** force the deterministic seat router — only `seat`/`action`, grammar verbs, or `SWARM_TEST_MODE` do. Tip quirk (Issue #150): `bool(self._params)` skipped `Runner.run` whenever any param was set; Chatty Commander #854 worked around that by omitting `workdir`. That workaround is no longer required. **FS-locality (Issue #148):** file tools default to the API-host filesystem — dev-worker-max `:8002` cannot see dev-worker-gpu `~/chatty-commander` unless `remote_workdir` or a remote-shaped `workdir` (`user@host:path` / `ssh://…`) plus SSH is set. Local `..` escapes still refused. [docs/qa/ISSUE-148-software-dev-remote-workdir.md](../../../docs/qa/ISSUE-148-software-dev-remote-workdir.md). |
| `sdlc_handoff` | Forced BA→Engineer→Tester handoff graph + circular skeptic variant (REQ-156; Issue #564). API only. |
| `rue_code` | Multi-agent code workflow |
| `jeeves` | MCP-aware butler demo |
| `geese` | Multi-agent writing/research |
| `zeus` | Large software-dev coordination (`zeus` CLI) |
| `stewie` | WordPress/MCP-oriented demo |
| `poets` | Poet swarm (`poets_cli.py`) |
| `gawd` | Django-ish demo package |
| `whiskeytango_foxtrot` | Hierarchical search/ops demo |
| `chucks_angels` | Minimal experimental coordination |
| `dynamic_team` | Backing implementation for `/v1/teams` **LLM-profile aliases** (not a multi-agent builder) |

## Removed / do not expect on disk

Former stubs or husks with no live `blueprint_*.py` (including EchoCraft,
BurntNoodles, NebulaShellz, MissionImprobable, WhingeSurf, Gaggle, MonkaiMagic,
Omniplex, Dilbot, UnapologeticPress, flock, digitalbutlers, messenger, …) are
**gone**. Historical mentions elsewhere are archival only.

## Configuration & running

- Config: `swarm_config.json` (`llm` profiles, `mcpServers`, optional
  `blueprints` overrides) — [CONFIGURATION.md](../../../CONFIGURATION.md) /
  [docs/SWARM_CONFIG.md](../../../docs/SWARM_CONFIG.md).
- Dev run: `uv run python src/swarm/blueprints/<dir>/blueprint_<dir>.py --instruction "…"`
  (or `swarm-cli launch <id>` / OpenAI client `model: "<id>"`).
- Flags: `--debug`, `--quiet`, `--config-path`, `--profile`, `--markdown` /
  `--no-markdown`.

# Archive — superseded architectures and plans

This folder is the project's memory of paths we have taken and moved past. It is
kept deliberately: it explains *why* the current design looks the way it does.
Nothing here describes the current system — for that, start at
[../VISION.md](../VISION.md).

> Status of everything in this folder: **historical**. Do not treat any document
> here as current guidance.

## What lives here

| Document | Era | What it captured | Superseded by |
|---|---|---|---|
| [IMPLEMENTATION_SUMMARY.md](./IMPLEMENTATION_SUMMARY.md) | 2026-06 | Snapshot of the FOSS-cleanup implementation wave | [ROADMAP.md](../../ROADMAP.md), [FEATURE_STATUS.md](../../FEATURE_STATUS.md) |
| [FEATURE_STATUS_2026-06-10.md](./FEATURE_STATUS_2026-06-10.md) | 2026-06-10 | Point-in-time feature evidence audit during the cleanup wave | [FEATURE_STATUS.md](../../FEATURE_STATUS.md) (live board) |
| [2026-06-cleanup-commit-log.txt](./2026-06-cleanup-commit-log.txt) | 2026-06 | Raw commit log of the cleanup wave (PRs #80–#85) | git history |
| [BASELINE_REPORT.md](./BASELINE_REPORT.md) | 2025-08-03 | Milestone 0 uv/README check | [README.md](../../README.md), [QUICKSTART.md](../QUICKSTART.md) |
| [architecture_marketplace_to_mcp.md](./architecture_marketplace_to_mcp.md) | pre-CLI-fusion | Marketplace → local config → MCP clients | [../VISION.md](../VISION.md), `swarm.core.tool_capabilities` |
| [requirements/](./requirements/) | 2026-08/09 | Full REQ transcripts (parallel SoT) | [GitHub Issues](https://github.com/matthewhand/open-swarm/issues) + [../requirements/](../requirements/) pointers |
| *(removed)* `.grok/workflows/moa-team-megafan-report.md` | 2026-09 | Accidental Grok megafan JSON dump (no secrets; code-audit scratch). Deleted in the #452 safe-N cleanup rather than re-homed. | git history |

## Related historical documents kept in place

These still live under `docs/` for their inbound links, but describe earlier
architectures rather than the current one:

- [../TODO.md](../TODO.md) — the original phase-based "make it run as in the
  README" milestone plan. Superseded as the source of truth by
  [ROADMAP.md](../../ROADMAP.md); retained as history.

## Lineage in one paragraph

Operating Swarm began as a derivative of OpenAI's experimental
[Swarm](https://github.com/openai/swarm), then migrated its runtime to the
[openai-agents SDK](https://github.com/openai/openai-agents-python). An early
emphasis on a blueprint **marketplace** and MCP distribution (the
marketplace-to-MCP doc above) gave way, after a 2026 FOSS-cleanup wave, to the
current focus: an **OpenAI-compatible gateway that adapts and orchestrates
agentic CLIs** (see [../VISION.md](../VISION.md)). The MCP work did not vanish —
it became the tool-capabilities layer — but it is no longer the headline.

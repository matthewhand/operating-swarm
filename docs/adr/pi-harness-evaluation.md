# REQ-1081: Pi agent harness — evaluation & decision record

**Issue:** #1081 · **Status:** Recommended (conditional) · **Prototype:** `src/swarm/core/pi_rpc_driver.py` + `tests/core/test_pi_rpc_driver.py`

## What Pi is

[Earendil's Pi](https://github.com/earendil-works/pi) (MIT) is a modular
agent harness in three npm packages:

| Package | Role |
|---|---|
| `@earendil-works/pi-ai` | Unified multi-provider LLM API (OpenAI, Anthropic, Google, …) |
| `@earendil-works/pi-agent-core` | Agent runtime: tool calling, state management |
| `@earendil-works/pi-coding-agent` | Interactive CLI; **runs headless `--mode rpc`** — long-lived subprocess, JSONL on stdio |

RPC mode (verified against `packages/coding-agent/docs/rpc.md` on `main`,
2026-09-23): stdin JSONL commands (`prompt`, `abort`, `get_state`,
`set_model`, `compact`, …), stdout `response` records correlated by
optional `id`, and a session event stream (`message_update` →
`assistantMessageEvent.text_delta`, `agent_end`, `agent_settled`).
Success response ≠ completion: the run finishes at `agent_settled`.
Framing is strict LF; a `readline`-style splitter is a documented hazard
(`readline` also splits on U+2028/U+2029) — split on bytes.

## What Open Swarm would gain

The issue's motivation holds up on inspection. `ApiKindBase` carries
bespoke provider plumbing (streaming chunking, tool stdout/stderr
formatting, token accounting) that Pi already solves for the *coding*
seat shape:

- 75+ providers via `pi-ai` with one config surface
- Tool-call mechanics + diff/patch execution proven in a terminal agent
- Steering, queueing, compaction, retry — all first-class protocol
  events, matching Swarm's queued-send and compact features
- Process isolation per seat (one `pi --mode rpc` child per conversation)

## What Open Swarm would keep

Orchestration, the rail, roles (incl. Belay), multi-seat coordination,
DB thread mirroring, and the WS surface stay ours. Pi replaces only the
per-seat inference/tool loop — exactly the `ApiKindBase` seam.

## Risks

1. **Permissions.** Pi ships no permission system ("runs with the
   permissions of the user and process that launched it"). Belay's
   `ToolGate` must therefore wire into Pi's **extension lifecycle hooks**
   (`onToolCall`) — Phase 3 — before any production use on a host with
   real credentials. Until then the driver is a *prototype* and must not
   back a routable seat.
2. **Node runtime.** Adds a Node dependency on the host (`pi` binary).
   Acceptable: the CLI seat kind already shells out to CLIs.
3. **Duplicated event models.** Pi events ≠ Swarm chunks. The driver
   defines the mapping table in one place; the UI keeps its existing
   chunk contract.
4. **Upstream pace.** Pi is fast-moving; pin a version per release and
   re-run the contract tests on upgrade.

## Decision

Proceed in phases, gated:

- **Phase 1 — this PR.** Headless Python RPC driver (spawn, strict
  framing, prompt/stream/abort/settle lifecycle) + unit tests with a
  fake `pi` subprocess. No routing changes; nothing can select it yet.
- **Phase 2.** `pi-operating-swarm` TypeScript extension (custom tools,
  lifecycle hooks) in its own package.
- **Phase 3.** Belay `ToolGate` wired as a Pi extension approval barrier;
  driver promoted from prototype once approvals cover every mutating tool.
- **Phase 4.** `PiAgentKind(ApiKindBase)` seat + rail UI + WS bridging.

Each later phase lands behind its own issue. Phase 1 alone changes no
runtime behaviour.

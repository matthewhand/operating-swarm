# pi-operating-swarm

Open Swarm extension for the [Pi agent harness](https://github.com/earendil-works/pi)
(#1081 Phase 2 — prototype).

Registers Swarm-side tools and lifecycle hooks into Pi's extension host so a
`pi --mode rpc` child can act as a Swarm seat's inference/tool engine while
staying observable (and later, gateable) by Swarm:

- `swarm_status` tool — reports the seat's Swarm context (agent id, conversation)
- `swarm_delegate` tool — placeholder seam for inter-seat delegation (#1097 groundwork)
- `onTurnStart` / `onToolCall` / `onTurnEnd` hooks — event taps that mirror Pi
  activity into the Swarm event stream; `onToolCall` **is** the Phase-3 Belay
  ToolGate (landed): fail-closed approval barrier — unwired gate, gate error,
  or parent denial all reject the tool call before execution. The child asks
  the parent over the `belay_gate_request` control channel; the Python side
  answers through REQ-55 `belay_tool_gate` (`swarm.core.pi_belay_gate`).

Phase 3 landed; still nothing in Swarm routes a live seat through it yet —
see `docs/adr/pi-harness-evaluation.md` for the phased gate.

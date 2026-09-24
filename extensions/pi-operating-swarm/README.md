# pi-operating-swarm

Open Swarm extension for the [Pi agent harness](https://github.com/earendil-works/pi)
(#1081 Phase 2 — prototype).

Registers Swarm-side tools and lifecycle hooks into Pi's extension host so a
`pi --mode rpc` child can act as a Swarm seat's inference/tool engine while
staying observable (and later, gateable) by Swarm:

- `swarm_status` tool — reports the seat's Swarm context (agent id, conversation)
- `swarm_delegate` tool — placeholder seam for inter-seat delegation (#1097 groundwork)
- `onTurnStart` / `onToolCall` / `onTurnEnd` hooks — event taps that mirror Pi
  activity into the Swarm event stream; `onToolCall` is the Phase-3 Belay
  ToolGate insertion point (approval barrier before any mutating tool runs).

Prototype status: nothing in Swarm routes here yet. See
`docs/adr/pi-harness-evaluation.md` for the phased gate.

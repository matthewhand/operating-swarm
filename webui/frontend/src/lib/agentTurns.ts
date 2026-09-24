/**
 * ADR-017 PR-2 — the SPA-side turn registry.
 *
 * The server bookends every turn with `turn_started` / `turn_finished`
 * frames carrying `turn_id` + `agent_id` (#1113). This module is the pure
 * state layer:
 *
 * - `applyTurnFrame` folds a bookend into a snapshot (`turnId` → entry),
 *   so the UI can answer "which turn is this agent running right now?"
 * - `activeTurnFor` returns the live turn for an agent (insertion order —
 *   the server serialises turns per agent, so the latest entry wins).
 * - `stopLabelFor` names the button's contract: interrupt *that* turn.
 *
 * Display is intentionally not part of this module — bookends are
 * protocol, not transcript. The working row reads the registry only to
 * scope its stop button.
 */

export interface AgentTurn {
  turnId: string
  agentId: string
  state: 'running' | 'finished'
}

export type TurnSnapshot = Record<string, AgentTurn>

export function applyTurnFrame(
  prev: TurnSnapshot,
  frame: { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
): TurnSnapshot {
  if (frame.kind === 'turn_started') {
    return {
      ...prev,
      [frame.turnId]: {
        turnId: frame.turnId,
        agentId: frame.agentId,
        state: 'running',
      },
    }
  }
  const existing = prev[frame.turnId]
  if (!existing) return prev
  return {
    ...prev,
    [frame.turnId]: { ...existing, state: 'finished' },
  }
}

/** The live (running) turn an agent owns, if any. Last one wins. */
export function activeTurnFor(
  snapshot: TurnSnapshot,
  agentId: string,
): AgentTurn | null {
  let found: AgentTurn | null = null
  for (const turn of Object.values(snapshot)) {
    if (turn.state === 'running' && turn.agentId === agentId) found = turn
  }
  return found
}

/** Copy for the row stop: it stops THIS turn, not the agent's whole queue. */
export function stopLabelFor(turn: AgentTurn | null): string {
  return turn
    ? `Stop this agent's generation (other turns keep running)`
    : `Stop generating`
}

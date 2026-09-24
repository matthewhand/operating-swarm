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

import { useEffect, useState } from 'react'

export interface AgentTurn {
  turnId: string
  agentId: string
  state: 'running' | 'finished'
}

export type TurnSnapshot = Record<string, AgentTurn>

export const AGENT_TURNS_EVENT = 'swarm:agent-turns'

let globalTurns: TurnSnapshot = {}
const listeners = new Set<(snapshot: TurnSnapshot) => void>()

function notifyListeners(): void {
  for (const listener of listeners) {
    try {
      listener(globalTurns)
    } catch {
      /* ignore listener errors */
    }
  }
  if (typeof window !== 'undefined' && window.dispatchEvent) {
    try {
      window.dispatchEvent(
        new CustomEvent(AGENT_TURNS_EVENT, { detail: globalTurns }),
      )
    } catch {
      /* window unavailable */
    }
  }
}

export function getTurnSnapshot(): TurnSnapshot {
  return globalTurns
}

export function resetTurnRegistry(): void {
  globalTurns = {}
  notifyListeners()
}

export function reduceTurnFrame(
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

export function recordTurnFrame(
  frame: { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
): TurnSnapshot {
  globalTurns = reduceTurnFrame(globalTurns, frame)
  notifyListeners()
  return globalTurns
}

export function applyTurnFrame(
  prev: TurnSnapshot,
  frame: { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
): TurnSnapshot
export function applyTurnFrame(
  frame: { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
): TurnSnapshot
export function applyTurnFrame(
  prevOrFrame:
    | TurnSnapshot
    | { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
  maybeFrame?: { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
): TurnSnapshot {
  if (maybeFrame) {
    return reduceTurnFrame(prevOrFrame as TurnSnapshot, maybeFrame)
  }
  return recordTurnFrame(
    prevOrFrame as { kind: 'turn_started' | 'turn_finished'; turnId: string; agentId: string },
  )
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

/** True when the agent has any turn in 'running' state in the given or global snapshot. */
export function isAgentTurnActive(
  agentId?: string | null,
  snapshot: TurnSnapshot = globalTurns,
): boolean {
  if (!agentId) return false
  if (activeTurnFor(snapshot, agentId) !== null) return true
  const stripped = agentId.replace(/^(team|remote|agent|blueprint):/, '')
  if (stripped !== agentId && activeTurnFor(snapshot, stripped) !== null) return true
  return false
}

/** Subscribe to live turn changes. Returns unsubscribe callback. */
export function subscribeAgentTurns(
  handler: (snapshot: TurnSnapshot) => void,
): () => void {
  listeners.add(handler)
  return () => {
    listeners.delete(handler)
  }
}

/** Reactive hook to read the global turn registry. */
export function useAgentTurns(): TurnSnapshot {
  const [snapshot, setSnapshot] = useState<TurnSnapshot>(() => getTurnSnapshot())
  useEffect(() => {
    setSnapshot(getTurnSnapshot())
    return subscribeAgentTurns((next) => setSnapshot(next))
  }, [])
  return snapshot
}

/** Reactive hook to check if a specific agent currently has a live turn. */
export function useAgentTurnActive(agentId?: string | null): boolean {
  const turns = useAgentTurns()
  return isAgentTurnActive(agentId, turns)
}

/** Copy for the row stop: it stops THIS turn, not the agent's whole queue. */
export function stopLabelFor(turn: AgentTurn | null): string {
  return turn
    ? `Stop this agent's generation (other turns keep running)`
    : `Stop generating`
}

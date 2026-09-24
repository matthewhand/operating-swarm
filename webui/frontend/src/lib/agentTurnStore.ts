/**
 * #1118 — the global per-agent turn registry (SPA-wide).
 *
 * Avatar motion must be a property of the **turn**, not of the **focused
 * chat**. This store subscribes to the whole-SPA multiplex socket and folds
 * every conversation's `turn_started` / `turn_finished` bookends into a
 * {agentId → running} map, so the rail can answer "is agent X working?"
 * even when its chat is not the one mounted.
 *
 * Backend provenance: `turn_started` carries `agent_id` (#1113); the
 * SPA socket tags every frame with its conversationId, so bookends from
 * background chats reach this store as long as their session is alive.
 */
import type { ChatWsEvent } from './chatWs'
import { onSpaFrame } from './spaSocket'

/** agentId → true while a turn is running. Pure snapshot for useSyncExternalStore. */
export type AgentTurnMap = Readonly<Record<string, boolean>>

const running = new Map<string, boolean>()
const listeners = new Set<() => void>()

let snapshot: AgentTurnMap = Object.freeze({})
let generation = 0

function emit(): void {
  const next: Record<string, boolean> = {}
  for (const [agentId, isRunning] of running) {
    if (isRunning) next[agentId] = true
  }
  snapshot = Object.freeze(next)
  generation += 1
  for (const listener of listeners) listener()
}

function foldEvent(event: ChatWsEvent): void {
  if (event.kind === 'turn_started' && event.agentId) {
    running.set(event.agentId, true)
    emit()
  } else if (event.kind === 'turn_finished' && event.agentId && running.get(event.agentId)) {
    running.set(event.agentId, false)
    emit()
  }
}

function handleFrame(event: ChatWsEvent, _conversationId: string): void {
  foldEvent(event)
}

let subscription: { release: () => void } | null = null

/** Idempotent: start consuming bookends from the SPA mux tap. */
export function startAgentTurnStore(): void {
  if (subscription) return
  subscription = onSpaFrame(handleFrame)
}

/** Test seam. */
export function resetAgentTurnStoreForTests(): void {
  subscription?.release()
  subscription = null
  running.clear()
  listeners.clear()
  snapshot = Object.freeze({})
  generation += 1
}

export function subscribeAgentTurns(listener: () => void): () => void {
  listeners.add(listener)
  return () => listeners.delete(listener)
}

export function agentTurnSnapshot(): AgentTurnMap {
  return snapshot
}

/** Snapshot generation — lets hooks cache per-version derived values. */
export function agentTurnGeneration(): number {
  return generation
}

export function isAgentTurnRunning(agentId: string): boolean {
  return snapshot[agentId] === true
}

/** Test seam: drive the store's fold directly (no socket). */
export function __foldForTests(event: ChatWsEvent): void {
  foldEvent(event)
}

/**
 * Which agent seat is currently selected — published once, consumed everywhere.
 *
 * REQ-912 (#511), REQ-914 (#513) and REQ-917 (#516) all need to know the
 * selected seat and its kind: the rail footer has to gate API-only entries, the
 * routines calendar has to prefill "the current agent", and the composer plugins
 * panel has to key its toggles per agent. None of them can read that from the
 * URL without re-deriving it, and re-deriving it is how the three would drift —
 * so `ChatPage` publishes it here and consumers subscribe.
 *
 * Deliberately separate from `chatScope`. A chat scope is the **identity of the
 * conversation** (a team thread, a remote session, an explicit `?session=`,
 * or a per-agent conversation id); this is **which seat is selected**. Merging
 * the two is the class of defect recorded in REQ-904 (#502): identity and
 * binding are different axes and must not share an id space.
 *
 * The rail and the calendar are siblings of `ChatPage`, not descendants, so
 * this is published through `localStorage` + a window event — the same pattern
 * as `chatScope` and `agentSessions`. The `storage` listener additionally syncs
 * **other tabs**, which a same-document event cannot do.
 */

import { useEffect, useState } from 'react'
import { classifyAgentKind, isSwarmOwnedAgent, type AgentKind } from './agentKind'

export type CurrentAgentKind = AgentKind

export interface CurrentAgent {
  /**
   * Seat id in the space the rail and the URL use: a blueprint/agent id, or a
   * scope-prefixed `team:<id>` / `remote:<id>`. Prefixes are preserved so
   * callers can tell a seat from a scope — see `isScopedSeatId`.
   *
   * A scoped id is **not** an agent id: a team thread and a remote session are
   * conversation scopes, and per-agent state (REQ-917) must not be keyed by
   * them.
   */
  id: string
  kind: CurrentAgentKind
}

export const CURRENT_AGENT_EVENT = 'swarm:current-agent'
export const CURRENT_AGENT_STORAGE_KEY = 'swarm_current_agent'

const KINDS: ReadonlySet<string> = new Set<CurrentAgentKind>([
  'api',
  'cli',
  'remote',
  'blueprint',
])

/** True when `id` carries a conversation-scope prefix rather than a bare seat id. */
export function isScopedSeatId(id: string | null | undefined): boolean {
  const text = (id ?? '').trim().toLowerCase()
  return text.startsWith('team:') || text.startsWith('remote:')
}

/** Tolerant reader for the persisted payload — never throws on junk. */
export function parseCurrentAgent(raw: unknown): CurrentAgent | null {
  if (raw == null) return null
  let value: unknown = raw
  if (typeof raw === 'string') {
    const text = raw.trim()
    if (!text) return null
    try {
      value = JSON.parse(text)
    } catch {
      return null
    }
  }
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const record = value as Record<string, unknown>
  const id = typeof record.id === 'string' ? record.id.trim() : ''
  if (!id) return null
  const kind = typeof record.kind === 'string' ? record.kind.trim().toLowerCase() : ''
  if (!KINDS.has(kind)) {
    // An unknown kind is still a usable seat — classify from the id instead of
    // discarding the whole payload.
    return { id, kind: classifyAgentKind(id) }
  }
  return { id, kind: kind as CurrentAgentKind }
}

export function loadCurrentAgent(): CurrentAgent | null {
  try {
    return parseCurrentAgent(localStorage.getItem(CURRENT_AGENT_STORAGE_KEY))
  } catch {
    return null
  }
}

/**
 * Publish the selected seat. `null` clears it (e.g. when no seat is resolved
 * yet) so consumers can distinguish "unknown" from a stale previous seat.
 */
export function publishCurrentAgent(agent: CurrentAgent | null): void {
  try {
    if (!agent) {
      localStorage.removeItem(CURRENT_AGENT_STORAGE_KEY)
    } else {
      localStorage.setItem(CURRENT_AGENT_STORAGE_KEY, JSON.stringify(agent))
    }
  } catch {
    /* private mode — subscribers still get the event */
  }
  try {
    window.dispatchEvent(new CustomEvent<CurrentAgent | null>(CURRENT_AGENT_EVENT, { detail: agent }))
  } catch {
    /* jsdom / SSR */
  }
}

/**
 * Subscribe to seat changes: same-document publishes **and** other-tab writes.
 *
 * Both channels are needed. A `storage` event never fires in the document that
 * performed the write, so it cannot carry local changes; the custom event never
 * crosses documents, so it cannot carry other tabs. Neither alone is sufficient.
 */
export function subscribeCurrentAgent(
  handler: (agent: CurrentAgent | null) => void,
): () => void {
  if (typeof window === 'undefined') return () => {}

  const onEvent = (event: Event) => {
    const detail = (event as CustomEvent<CurrentAgent | null>).detail ?? null
    handler(detail ? parseCurrentAgent(detail) : null)
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key && event.key !== CURRENT_AGENT_STORAGE_KEY) return
    handler(loadCurrentAgent())
  }

  window.addEventListener(CURRENT_AGENT_EVENT, onEvent)
  window.addEventListener('storage', onStorage)
  return () => {
    window.removeEventListener(CURRENT_AGENT_EVENT, onEvent)
    window.removeEventListener('storage', onStorage)
  }
}

/** Reactive read of the selected seat. Reads once on mount, then subscribes. */
export function useCurrentAgent(): CurrentAgent | null {
  const [agent, setAgent] = useState<CurrentAgent | null>(() => loadCurrentAgent())
  useEffect(() => {
    setAgent(loadCurrentAgent())
    return subscribeCurrentAgent(setAgent)
  }, [])
  return agent
}

/**
 * Strict reading of "API agent" — matches `isApiRailAgent` in the rail
 * (`kind === 'api' || id === 'api_agent'`). Blueprint seats are excluded.
 *
 * REQ-912 (#511) has an open decision on whether blueprint seats should also
 * count as API for the purposes of gating. That is policy, so this module
 * exports both readings and leaves the choice to the consumer rather than
 * baking one in.
 */
export function isApiSeat(agent: CurrentAgent | null | undefined): boolean {
  return agent?.kind === 'api'
}

/** Wider reading: swarm-owned seats (API **and** blueprint). Delegates to
 * `isSwarmOwnedAgent` so the two definitions cannot drift. */
export function isSwarmOwnedSeat(agent: CurrentAgent | null | undefined): boolean {
  if (!agent) return false
  return isSwarmOwnedAgent(agent.id, agent.kind)
}

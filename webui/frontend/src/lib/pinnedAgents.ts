/**
 * Persist pinned favourite tiles (drag-from-conversation-list).
 *
 * REQ-94: pin is a move, not a copy. The rail list excludes these ids so
 * an agent is never listed in both the favourite grid and the rows below.
 * Unpin restores the row (rail order is unchanged). IDs cache in localStorage.
 * REQ-144 also persists the ordered list on GET/PATCH /v1/preferences/
 * (server wins after a one-time local import).
 */

export const PINNED_AGENTS_STORAGE_KEY = 'swarm_pinned_agents'
export const AGENT_DRAG_MIME = 'application/x-swarm-agent'

/**
 * #1217: fired on every write to the canonical pinned-agents store.
 * The DOM `storage` event only fires in other documents, so same-tab
 * surfaces must listen to this custom event for instant synchronization.
 */
export const PINNED_AGENTS_CHANGED_EVENT = 'swarm:pinned-agents-changed'

function notifyPinnedAgentsChanged(): void {
  try {
    window.setTimeout(() => {
      try {
        window.dispatchEvent(new Event(PINNED_AGENTS_CHANGED_EVENT))
      } catch {
        /* listener gone */
      }
    }, 0)
  } catch {
    /* no window (SSG/tests) */
  }
}

/** First-load favourite when `swarm_pinned_agents` is missing (empty prefs). */
export const DEFAULT_PINNED_SUPPORT: PinnedAgent = { id: 'support', name: 'Support' }

export function hasPinnedAgentsStorage(): boolean {
  try {
    return localStorage.getItem(PINNED_AGENTS_STORAGE_KEY) !== null
  } catch {
    return false
  }
}

export interface PinnedAgent {
  id: string
  name: string
}

let activeDrag: PinnedAgent | null = null

export function beginAgentDrag(agent: PinnedAgent): void {
  if (!agent.id) {
    activeDrag = null
    return
  }
  activeDrag = { id: agent.id, name: agent.name || agent.id }
}

export function endAgentDrag(): void {
  activeDrag = null
}

export function peekAgentDrag(): PinnedAgent | null {
  return activeDrag
}

function normalizePin(value: unknown): PinnedAgent | null {
  if (typeof value === 'string' && value.length > 0) {
    return { id: value, name: value }
  }
  if (!value || typeof value !== 'object') return null
  const rec = value as { id?: unknown; name?: unknown }
  if (typeof rec.id !== 'string' || rec.id.length === 0) return null
  return {
    id: rec.id,
    name: typeof rec.name === 'string' && rec.name.length > 0 ? rec.name : rec.id,
  }
}

export function loadOrSeedPinnedAgents(): PinnedAgent[] {
  if (hasPinnedAgentsStorage()) return loadPinnedAgents()
  const seeded = [DEFAULT_PINNED_SUPPORT]
  savePinnedAgents(seeded)
  return seeded
}

export function loadPinnedAgents(): PinnedAgent[] {
  try {
    const raw = localStorage.getItem(PINNED_AGENTS_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    const seen = new Set<string>()
    const pins: PinnedAgent[] = []
    for (const item of parsed) {
      const pin = normalizePin(item)
      if (!pin || seen.has(pin.id)) continue
      seen.add(pin.id)
      pins.push(pin)
    }
    return pins
  } catch {
    return []
  }
}

export function savePinnedAgents(pins: PinnedAgent[]): void {
  const unique: PinnedAgent[] = []
  const seen = new Set<string>()
  for (const item of pins) {
    const pin = normalizePin(item)
    if (!pin || seen.has(pin.id)) continue
    seen.add(pin.id)
    unique.push(pin)
  }
  try {
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, JSON.stringify(unique))
  } catch {
    /* persistence is best-effort */
  }
  notifyPinnedAgentsChanged()
}

export function pinAgent(agent: PinnedAgent, current: PinnedAgent[]): PinnedAgent[] {
  const pin = normalizePin(agent)
  if (!pin) return current
  if (current.some((item) => item.id === pin.id)) return current
  const next = [...current, pin]
  savePinnedAgents(next)
  return next
}

export function unpinAgent(id: string, current: PinnedAgent[]): PinnedAgent[] {
  if (!id) return current
  const next = current.filter((item) => item.id !== id)
  savePinnedAgents(next)
  return next
}

/** Move an existing favourite so it sits immediately before `beforeId`. */
export function movePinnedAgent(
  fromId: string,
  beforeId: string,
  current: PinnedAgent[],
): PinnedAgent[] {
  if (!fromId || !beforeId || fromId === beforeId) return current
  const from = current.find((item) => item.id === fromId)
  if (!from) return current
  const without = current.filter((item) => item.id !== fromId)
  const index = without.findIndex((item) => item.id === beforeId)
  if (index < 0) return current
  without.splice(index, 0, from)
  savePinnedAgents(without)
  return without
}

/** Ids currently sitting in the favourite grid (hidden pins stay in storage). */
export function pinnedAgentIds(pins: PinnedAgent[]): Set<string> {
  return new Set(pins.map((pin) => pin.id))
}

/** Drop favourited ids from the AGENTS/rail list so pin is a move, not a copy. */
export function excludePinnedFromList<T extends { id: string }>(
  items: T[],
  pins: PinnedAgent[],
): T[] {
  if (!pins.length) return items
  const ids = pinnedAgentIds(pins)
  return items.filter((item) => !ids.has(item.id))
}

export function writeAgentDragPayload(dataTransfer: DataTransfer, agent: PinnedAgent): void {
  const pin = normalizePin(agent)
  if (!pin) return
  beginAgentDrag(pin)
  try {
    // Strip URL formats so Chromium/Edge does not trigger native "Split view" / "Open in split screen" drag UI (#702)
    dataTransfer.clearData('text/uri-list')
    dataTransfer.clearData('URL')
    dataTransfer.clearData('text/html')
  } catch {
    /* clearData might not be supported in some test environments */
  }
  try {
    dataTransfer.setData(AGENT_DRAG_MIME, JSON.stringify(pin))
    dataTransfer.setData('text/plain', pin.id)
    dataTransfer.effectAllowed = 'copyMove'
  } catch {
    /* some test DataTransfers only implement a subset */
  }
  try {
    dataTransfer.clearData('text/uri-list')
    dataTransfer.clearData('URL')
    dataTransfer.clearData('text/html')
  } catch {
    /* ignore */
  }
}

export function parseAgentDragPayload(dataTransfer?: DataTransfer | null): PinnedAgent | null {
  const fromSession = peekAgentDrag()
  if (fromSession) return fromSession
  if (!dataTransfer) return null
  try {
    const typed = dataTransfer.getData(AGENT_DRAG_MIME)
    if (typed) {
      const pin = normalizePin(JSON.parse(typed) as unknown)
      if (pin) return pin
    }
  } catch {
    /* fall through to text/plain */
  }
  try {
    const plain = dataTransfer.getData('text/plain')
    return normalizePin(plain)
  } catch {
    return null
  }
}

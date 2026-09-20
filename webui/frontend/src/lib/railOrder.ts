/**
 * Persist the left-rail conversation/agent row order.
 *
 * Hidden stays a separate list and is not stored here as a drag target.
 * Favourite tiles use `swarm_pinned_agents` and must not share this key.
 * Persistence is best-effort, same as hostname.
 */

export const RAIL_ORDER_STORAGE_KEY = 'swarm_rail_order'
export const GENERATION_COMPLETE_EVENT = 'swarm:generation-complete'

let activeRailDragId: string | null = null

export function beginRailDrag(id: string): void {
  activeRailDragId = id || null
}

export function peekRailDrag(): string | null {
  return activeRailDragId
}

export function endRailDrag(): void {
  activeRailDragId = null
}

function uniqueIds(ids: string[]): string[] {
  const seen = new Set<string>()
  const next: string[] = []
  for (const id of ids) {
    if (typeof id !== 'string' || id.length === 0 || seen.has(id)) continue
    seen.add(id)
    next.push(id)
  }
  return next
}

export function loadRailOrder(): string[] {
  try {
    const raw = localStorage.getItem(RAIL_ORDER_STORAGE_KEY)
    if (!raw) return []
    const parsed: unknown = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return uniqueIds(parsed.filter((id): id is string => typeof id === 'string'))
  } catch {
    return []
  }
}

export function saveRailOrder(ids: string[]): string[] {
  const next = uniqueIds(ids)
  try {
    if (next.length === 0) localStorage.removeItem(RAIL_ORDER_STORAGE_KEY)
    else localStorage.setItem(RAIL_ORDER_STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* persistence is best-effort */
  }
  return next
}

/** Apply a persisted id list to catalog rows; unknown ids keep catalog order. */
export function applyRailOrder<T extends { id: string }>(items: T[], order: string[]): T[] {
  if (order.length === 0) return items
  const byId = new Map(items.map((item) => [item.id, item]))
  const seen = new Set<string>()
  const result: T[] = []
  for (const id of order) {
    const item = byId.get(id)
    if (!item || seen.has(id)) continue
    result.push(item)
    seen.add(id)
  }
  for (const item of items) {
    if (seen.has(item.id)) continue
    result.push(item)
    seen.add(item.id)
  }
  return result
}

export function mergeRailOrder(stored: string[], visibleIds: string[]): string[] {
  return applyRailOrder(
    visibleIds.map((id) => ({ id })),
    stored,
  ).map((item) => item.id)
}

/** Move `fromId` so it sits immediately before `beforeId` in the visible list. */
export function moveRailId(order: string[], fromId: string, beforeId: string): string[] {
  if (!fromId || !beforeId || fromId === beforeId) return order
  const without = order.filter((id) => id !== fromId)
  const index = without.indexOf(beforeId)
  if (index < 0) return order
  without.splice(index, 0, fromId)
  return without
}

/** Insert `newId` immediately after `afterId` in the rail order (or at start if afterId is absent/unfound). */
export function insertRailIdAfter(order: string[], newId: string, afterId?: string): string[] {
  if (!newId) return order
  const without = order.filter((id) => id !== newId)
  if (!afterId) return [newId, ...without]
  const index = without.indexOf(afterId)
  if (index < 0) return [newId, ...without]
  without.splice(index + 1, 0, newId)
  return without
}

/**
 * REQ-128: Bump an active agent to the top of the non-favourites list on generation finish.
 *
 * Stability and tie-breaking:
 * - The most recently finished agent is placed at index 0.
 * - All other agents maintain their existing relative order (stable ordering).
 * - If multiple agents finish in rapid succession, each moves to index 0 as it completes,
 *   so the last one to complete sits at the very top.
 * - If an agent is already at index 0, the order remains unchanged.
 */
export function bumpRailIdToTop(order: string[], id: string): string[] {
  if (!id) return order
  return [id, ...order.filter((item) => item !== id)]
}

export interface GenerationCompleteDetail {
  agentId: string
  snippet?: string
  agentName?: string
  failed?: boolean
}

export function notifyGenerationComplete(
  agentId: string,
  extra?: Omit<GenerationCompleteDetail, 'agentId'>,
): void {
  if (!agentId) return
  try {
    window.dispatchEvent(
      new CustomEvent(GENERATION_COMPLETE_EVENT, {
        detail: { agentId, ...extra },
      }),
    )
  } catch {
    /* window unavailable */
  }
}

export function generationCompleteDetail(event: Event): GenerationCompleteDetail | null {
  const detail = (event as CustomEvent<Partial<GenerationCompleteDetail>>).detail
  if (typeof detail?.agentId !== 'string' || detail.agentId.length === 0) return null
  return {
    agentId: detail.agentId,
    snippet: typeof detail.snippet === 'string' ? detail.snippet : undefined,
    agentName: typeof detail.agentName === 'string' ? detail.agentName : undefined,
    failed: detail.failed === true,
  }
}

export function generationCompleteAgentId(event: Event): string | null {
  return generationCompleteDetail(event)?.agentId ?? null
}

/**
 * #1705 — the rail's Ctrl/Shift multi-select model, as pure functions.
 *
 * The gesture model is the one operators already use in file lists, and the
 * issue asks for it to be *documented* rather than reinvented:
 *
 *   click              → single (navigate/open, unchanged)
 *   Ctrl/Cmd + click   → toggle one row in/out of the selection
 *   Shift + click      → contiguous range from the anchor row
 *   Escape             → clear
 *   Space (on a row)   → toggle (the keyboard equivalent of Ctrl+click)
 *
 * Kept out of the components on purpose: the rail renders five different row
 * shapes (agent link, agent button, herdr anchor, team link, remote link) and
 * they all have to agree on the answer, so there is exactly one answer here.
 *
 * `order` is the RENDERED order of selectable row ids, so Shift+click selects
 * what the user sees between the anchor and the target, not a stale snapshot.
 */

/** Ids in the rail's current rendered order. Duplicates are tolerated. */
export type RailOrder = readonly string[]

export interface RailSelectionState {
  /** Selected ids, in selection order (anchor first). */
  ids: string[]
  /** The row a Shift+click range extends from. `null` after a clear. */
  anchorId: string | null
}

export const EMPTY_RAIL_SELECTION: RailSelectionState = { ids: [], anchorId: null }

function uniq(ids: readonly string[]): string[] {
  return Array.from(new Set(ids.filter((id) => typeof id === 'string' && id.length > 0)))
}

/** Ctrl/Cmd+click (or Space): add the row if absent, drop it if present. */
export function toggleRailSelection(
  current: RailSelectionState,
  id: string,
): RailSelectionState {
  if (!id) return current
  if (current.ids.includes(id)) {
    return { ids: current.ids.filter((item) => item !== id), anchorId: current.anchorId }
  }
  return { ids: [...current.ids, id], anchorId: id }
}

/**
 * Shift+click: every row from the anchor to `id` inclusive, in rail order.
 *
 * With no anchor (the first gesture of a selection) it degrades to a plain
 * toggle, so Shift+click never silently selects nothing.
 */
export function selectRailRange(
  current: RailSelectionState,
  id: string,
  order: RailOrder,
): RailSelectionState {
  if (!id) return current
  const from = current.anchorId
  if (!from || !order.includes(from)) return toggleRailSelection(current, id)
  const start = order.indexOf(from)
  const end = order.indexOf(id)
  if (start === -1 || end === -1) return toggleRailSelection(current, id)
  const [lo, hi] = start <= end ? [start, end] : [end, start]
  const span = uniq(order.slice(lo, hi + 1))
  // The anchor stays put so a second Shift+click re-derives from the same
  // origin, and rows the user already had selected outside the span survive.
  return { ids: uniq([...span, ...current.ids]), anchorId: from }
}

/** Escape / "Clear": the whole selection, anchor included. */
export function clearRailSelection(): RailSelectionState {
  return { ids: [], anchorId: null }
}

/** Drop ids that are no longer rendered (hidden, deleted, or off-page). */
export function pruneRailSelection(
  current: RailSelectionState,
  order: RailOrder,
): RailSelectionState {
  const live = new Set(order)
  const ids = current.ids.filter((id) => live.has(id))
  if (ids.length === current.ids.length && (ids.length > 0) === (current.anchorId !== null)) {
    return current
  }
  return { ids, anchorId: current.anchorId && live.has(current.anchorId) ? current.anchorId : null }
}

/** Bulk chrome appears at two or more, never at one (issue success #5). */
export const RAIL_BULK_MIN = 2

export function railBulkVisible(selection: RailSelectionState): boolean {
  return selection.ids.length >= RAIL_BULK_MIN
}

/**
 * #1740 — keyboard reordering for the rail, as pure functions.
 *
 * The rule the operator asked for is a *scoping* rule, and the whole bug was
 * that one flat list did everything:
 *
 *   Alt+Up / Alt+Down      reorder among SIBLINGS IN THE SAME SECTION
 *   Alt+Left / Alt+Right   move to the ADJACENT SECTION
 *
 * So the two verbs are computed from two different sources — the block's own
 * row list for a reorder, `railMoveToDestinations()` for a section change —
 * and neither can reach the other's data. Alt+Up at the top of a section is a
 * **no-op** (issue §2: "default: no-op at edges"), never a spill into the
 * previous block; the old flat behaviour would have done exactly that.
 *
 * Why it lives here rather than in a component: #1705 already made
 * `features/sidebar/railSelection.ts` the single owner of "what does a rail
 * key do", across all five row shapes. Reorder is the same kind of question
 * and must not become a second one — a divergent list here is exactly the
 * defect #1714 just fixed for Move-to. Every caller composes these with the
 * same stores (`moveRailId`/`moveRailIdAfter` in `lib/railOrder`,
 * `moveAgentToSection` in `lib/railSections`); nothing here writes storage.
 */

import { moveRailId } from '../../lib/railOrder'
import type { RailMoveToDestination } from '../../lib/railSections'

/** The four keys #1740 owns. Nothing else is a reorder gesture. */
export type RailReorderDirection = 'up' | 'down' | 'left' | 'right'

export interface RailReorderIntent {
  direction: RailReorderDirection
  /** Alt+Arrow never carries a second modifier — see {@link railReorderIntent}. */
  pure: true
}

const KEY_DIRECTIONS: Record<string, RailReorderDirection> = {
  ArrowUp: 'up',
  ArrowDown: 'down',
  ArrowLeft: 'left',
  ArrowRight: 'right',
}

/** Announced when the gesture cannot move the row. Never silent. */
export const RAIL_REORDER_EDGE_REASON = 'already at the edge of this section'
export const RAIL_REORDER_NO_SECTIONS_REASON = 'there is no other section to move to'

/**
 * The one place that decides "is this key a rail reorder gesture".
 *
 * Alt must be held and the OTHER modifiers must not, which mirrors
 * `onAltArrow`'s guard in `AgentSidebar` byte for byte: the two handlers can
 * therefore never both claim the same event, and a row that claims it first
 * (React root) is visible to the window handler through
 * `event.defaultPrevented`.
 */
export function railReorderIntent(
  event: { key: string; altKey: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean },
): RailReorderIntent | null {
  if (!event.altKey) return null
  if (event.ctrlKey || event.metaKey || event.shiftKey) return null
  const direction = KEY_DIRECTIONS[event.key]
  if (!direction) return null
  return { direction, pure: true }
}

/** #1714's own destination shape — the rail's blocks, not a rebuilt list. */
export type RailReorderDestination = Pick<RailMoveToDestination, 'id' | 'name' | 'selectable' | 'checked'>

/** The structural minimum this module needs from a rendered section block. */
export interface RailReorderBlockLike {
  id: string
  name: string
  rows: ReadonlyArray<{ id: string }>
}

export interface RailReorderOutcome {
  /** The rail order to persist; `[]`-safe and identity when nothing moved. */
  order: string[]
  /** True only when the operator's gesture actually changed something. */
  moved: boolean
  /** One sentence, for the rail's `role="status"` live region. */
  announcement: string
}

function displayName(id: string, blocks: ReadonlyArray<RailReorderBlockLike>): string {
  return blocks.find((block) => block.id === id)?.name || id
}

/**
 * Alt+Up / Alt+Down — swap with the adjacent sibling **inside one block**.
 *
 * Both ids come from the same block's `rows`, so the result can never place
 * the row in another section; the rail's flat order is only the storage
 * format, and swapping the two positions there is exactly "reorder among
 * siblings". At the first/last sibling the gesture is a no-op that still says
 * so, rather than spilling into the neighbouring block.
 */
export function reorderWithinSection(opts: {
  order: readonly string[]
  blocks: ReadonlyArray<RailReorderBlockLike>
  rowId: string
  direction: 'up' | 'down'
}): RailReorderOutcome {
  const { order, blocks, rowId, direction } = opts
  const block = blocks.find((candidate) => candidate.rows.some((row) => row.id === rowId))
  if (!block) {
    return {
      order: [...order],
      moved: false,
      announcement: `This row is not in a section, so it cannot be reordered.`,
    }
  }
  const siblings = block.rows.map((row) => row.id)
  const from = siblings.indexOf(rowId)
  const to = from + (direction === 'up' ? -1 : 1)
  const blockName = displayName(block.id, blocks)
  if (from < 0 || to < 0 || to >= siblings.length) {
    return {
      order: [...order],
      moved: false,
      announcement: `${rowId} is ${RAIL_REORDER_EDGE_REASON} (${blockName}).`,
    }
  }
  const swapWith = siblings[to]
  // Both positions are real entries in the flat order, so the swap is a swap.
  const fromAt = order.indexOf(rowId)
  const toAt = order.indexOf(swapWith)
  if (fromAt < 0 || toAt < 0) {
    return { order: [...order], moved: false, announcement: `Could not reorder ${rowId}.` }
  }
  const next = [...order]
  next[fromAt] = swapWith
  next[toAt] = rowId
  return {
    order: next,
    moved: true,
    announcement: `Moved ${rowId} ${direction} to position ${to + 1} of ${siblings.length} in ${blockName}.`,
  }
}

export interface RailSectionMoveOutcome {
  /** The destination section id, or null when the gesture could not fire. */
  targetId: string | null
  moved: boolean
  announcement: string
  /**
   * The row's new position in the flat order, or `null` when the caller
   * should leave the order alone. Reusing `moveRailId`/`moveRailIdAfter`
   * (never a hand-rolled splice) is what keeps this consistent with drag.
   */
  order: string[] | null
}

/**
 * Alt+Left / Alt+Right — file the row into the adjacent **selectable**
 * destination, reading the very list the Move-to submenu shows.
 *
 * The scan runs over the whole destination list (auto sections included) so
 * "adjacent" means adjacent *in the rail*, and it skips the non-selectable
 * ones rather than stopping at them: the CLI section an agent is rendered
 * under is a grouping, not a filing choice (#1714), so Alt+Right from it must
 * land on the next real destination, not on the section it is already in.
 */
export function moveToAdjacentSection(opts: {
  order: readonly string[]
  destinations: readonly RailReorderDestination[]
  blocks: ReadonlyArray<RailReorderBlockLike>
  rowId: string
  currentSectionId: string
  direction: 'left' | 'right'
}): RailSectionMoveOutcome {
  const { order, destinations, blocks, rowId, currentSectionId, direction } = opts
  const list = destinations.filter((destination) => Boolean(destination.id))
  if (list.length === 0) {
    return {
      targetId: null,
      moved: false,
      announcement: RAIL_REORDER_NO_SECTIONS_REASON,
      order: null,
    }
  }
  const currentAt = list.findIndex((destination) => destination.id === currentSectionId)
  const start = currentAt < 0 ? 0 : currentAt
  const step = direction === 'right' ? 1 : -1
  let target: RailReorderDestination | undefined
  for (let index = start + step; index >= 0 && index < list.length; index += step) {
    const candidate = list[index]
    if (candidate.selectable) {
      target = candidate
      break
    }
  }
  const fromName = displayName(currentSectionId, blocks)
  if (!target) {
    return {
      targetId: null,
      moved: false,
      announcement: `${rowId} is ${RAIL_REORDER_EDGE_REASON} (${fromName}).`,
      order: null,
    }
  }
  // Land the row at the TOP of the destination block so the rail shows it in
  // the section it was just moved into, using the same two helpers drag uses.
  // A destination with no visible rows (a collapsed block, or one the row
  // itself will be the first member of) has nothing to sit before, so the row
  // goes to the end of the flat order — where the new membership will file it
  // into exactly that block. The alternative — leaving the order untouched —
  // is the silent no-op this whole issue is about: the announcement would say
  // "Moved" while the membership write was skipped.
  const targetBlock = blocks.find((block) => block.id === target.id)
  const firstRowId = targetBlock?.rows[0]?.id
  const nextOrder = firstRowId
    ? moveRailId([...order], rowId, firstRowId)
    : [...order.filter((id) => id !== rowId), rowId]
  const actuallyMoved = nextOrder.some((id, index) => id !== order[index])
  return {
    targetId: target.id,
    moved: target.id !== currentSectionId || actuallyMoved,
    announcement: `Moved ${rowId} to ${target.name}.`,
    order: nextOrder,
  }
}

/* ------------------------------------------------------------------ *
 * The PIN GRID, which is a sibling scope of its own.
 *
 * Pinned tiles are not rows of a section: they are rendered above every
 * section, in their own store (`lib/pinnedAgents`), in their own order. The
 * first land of #1740 gave the section rows a reorder verb and left this grid
 * out, so Alt+Down on a focused pin still fell through to #1088's sequential
 * navigation. These two helpers give the grid the SAME verb by describing it
 * in the same vocabulary — one pseudo-block above the real ones — rather than
 * by teaching the component a second set of rules.
 * ------------------------------------------------------------------ */

/** The pin grid's block id. Not a real section: it owns no membership. */
export const RAIL_PIN_GRID_ID = 'pins'
/** What the operator calls it, and what the announcement says. */
export const RAIL_PIN_GRID_NAME = 'Pinned'

/**
 * The pin grid as one block of the rail, positioned ABOVE the real sections —
 * which is where the rail renders it, and therefore what "adjacent" means for
 * Alt+Left / Alt+Right from a pin.
 */
export function pinGridBlock(
  visiblePins: ReadonlyArray<{ id: string }>,
): RailReorderBlockLike {
  return { id: RAIL_PIN_GRID_ID, name: RAIL_PIN_GRID_NAME, rows: visiblePins }
}

/**
 * Alt+Up / Alt+Down on a pin tile — the identical verb, in the grid's scope.
 *
 * `pins` (not `visiblePins`) is the storage the swap is applied to, so a pin
 * that is currently hidden keeps its stored position while the two VISIBLE
 * tiles exchange theirs. The sibling list stays `visiblePins`, which is what
 * the operator can see: reordering to a position the grid does not render
 * would be a silent no-op, the exact defect #1740 exists to remove.
 */
export function reorderWithinPinGrid(opts: {
  pins: ReadonlyArray<{ id: string }>
  visiblePins: ReadonlyArray<{ id: string }>
  pinId: string
  direction: 'up' | 'down'
}): RailReorderOutcome {
  return reorderWithinSection({
    order: opts.pins.map((pin) => pin.id),
    blocks: [pinGridBlock(opts.visiblePins)],
    rowId: opts.pinId,
    direction: opts.direction,
  })
}

/**
 * Alt+Left / Alt+Right from a pin — file it into the adjacent SECTION, which
 * means it LEAVES the pin grid (the same rule drag-to-section and Move-to
 * already follow, #801: `excludePinnedFromList` strips pinned ids from the
 * section rows, so a pin that stayed would be rendered nowhere).
 *
 * The section destinations are #1714's own list; the pin grid is prepended as
 * a non-selectable entry so "adjacent" is measured from where the pin is
 * rather than from an arbitrary section. `order` is the rail row order — the
 * pin's own id is not in it yet, and the outcome inserts it immediately before
 * the destination's first row, exactly as a drop onto that block's first row
 * does.
 */
export function movePinToAdjacentSection(opts: {
  order: readonly string[]
  sectionDestinations: readonly RailReorderDestination[]
  blocks: ReadonlyArray<RailReorderBlockLike>
  visiblePins: ReadonlyArray<{ id: string }>
  pinId: string
  direction: 'left' | 'right'
}): RailSectionMoveOutcome {
  return moveToAdjacentSection({
    order: opts.order,
    destinations: [
      { id: RAIL_PIN_GRID_ID, name: RAIL_PIN_GRID_NAME, selectable: false, checked: true },
      ...opts.sectionDestinations,
    ],
    blocks: [pinGridBlock(opts.visiblePins), ...opts.blocks],
    rowId: opts.pinId,
    currentSectionId: RAIL_PIN_GRID_ID,
    direction: opts.direction,
  })
}

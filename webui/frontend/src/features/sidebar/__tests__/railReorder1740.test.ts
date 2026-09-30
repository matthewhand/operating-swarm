/**
 * #1740 — Alt+Up/Down reorders WITHIN a section; Alt+Left/Right changes it.
 *
 * The bug was a single flat rail order doing both jobs, so a row dragged to
 * the top of its block silently became the top of the rail. These are the
 * pure model: no DOM, no storage, so each rule is pinned exactly.
 *
 *   §1 Alt+Up/Down swap with a sibling in the SAME block
 *   §2 at a block edge the gesture is a no-op that still SAYS so (never a
 *      spill into the neighbouring block)
 *   §3 Alt+Left/Right cross into the ADJACENT selectable destination
 *   §4 non-Alt keys are not reorder gestures at all
 *
 * The Pinned grid is covered here too: the grid is a sibling scope of its own,
 * so its tiles reorder by the same two verbs, with the same edge rule, over
 * `lib/pinnedAgents` order instead of the rail order.
 */
import { describe, expect, it } from 'vitest'
import {
  RAIL_PIN_GRID_ID,
  RAIL_PIN_GRID_NAME,
  RAIL_REORDER_EDGE_REASON,
  movePinToAdjacentSection,
  moveToAdjacentSection,
  railReorderIntent,
  reorderWithinPinGrid,
  reorderWithinSection,
  type RailReorderBlockLike,
} from '../railReorder'
import { railMoveToDestinations } from '../../../lib/railSections'

// Three sections, four rows, deliberately interleaved in the FLAT order so a
// swap cannot accidentally look like a section move (and vice versa).
const blocks: RailReorderBlockLike[] = [
  { id: 'api', name: 'API', rows: [{ id: 'a1' }, { id: 'b1' }] },
  { id: 'sec_work', name: 'Work', rows: [{ id: 'a2' }, { id: 'b2' }] },
  { id: 'unassigned', name: 'Unassigned', rows: [{ id: 'a3' }] },
]
const order = ['a1', 'b1', 'a2', 'b2', 'a3']

describe('#1740 the gesture gate', () => {
  it('claims exactly Alt + one of the four arrows', () => {
    for (const [key, direction] of [
      ['ArrowUp', 'up'],
      ['ArrowDown', 'down'],
      ['ArrowLeft', 'left'],
      ['ArrowRight', 'right'],
    ] as const) {
      expect(railReorderIntent({ key, altKey: true })).toEqual({ direction, pure: true })
    }
  })

  it('is not a gesture without Alt — plain arrows are the browser/scroll', () => {
    for (const key of ['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight']) {
      expect(railReorderIntent({ key, altKey: false })).toBeNull()
    }
  })

  it('is not a gesture with a second modifier, so #1088 navigation and the browser keep their own combinations', () => {
    for (const mod of ['ctrlKey', 'metaKey', 'shiftKey'] as const) {
      expect(railReorderIntent({ key: 'ArrowUp', altKey: true, [mod]: true })).toBeNull()
    }
  })

  it('ignores keys that are not arrows', () => {
    for (const key of ['Enter', ' ', 'Escape', 'F10', 'a', 'Tab']) {
      expect(railReorderIntent({ key, altKey: true })).toBeNull()
    }
  })
})

describe('#1740 §1 Alt+Up/Down reorder among siblings in the SAME section', () => {
  it('moves a row down one sibling and stops there', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'a2', direction: 'down' })
    expect(outcome.moved).toBe(true)
    expect(outcome.order).toEqual(['a1', 'b1', 'b2', 'a2', 'a3'])
  })

  it('moves a row up one sibling', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'b2', direction: 'up' })
    expect(outcome.moved).toBe(true)
    expect(outcome.order).toEqual(['a1', 'b1', 'b2', 'a2', 'a3'])
  })

  it('never moves a row into another section, even from a block boundary', () => {
    // `a1` is the first API row and `a3` the only Unassigned row; swapping
    // either must not change which block the row is in.
    for (const [rowId, direction] of [
      ['a1', 'up'],
      ['a1', 'down'],
      ['a3', 'up'],
      ['a3', 'down'],
    ] as const) {
      const outcome = reorderWithinSection({ order, blocks, rowId, direction })
      const owningBlock = (id: string) =>
        blocks.find((block) => block.rows.some((row) => row.id === id))?.id
      // Either it did not move, or it swapped with a sibling — never crossed.
      if (outcome.moved) expect(owningBlock(outcome.order[order.indexOf(rowId)])).toBe(owningBlock(rowId))
      else expect(outcome.order).toEqual(order)
    }
  })

  it('is a genuine swap: the row that was above is now below', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'a2', direction: 'down' })
    // Adjacent to the sibling it swapped with, present exactly once, and the
    // set of ids is untouched — a swap, not a splice-and-insert.
    const at = outcome.order.indexOf('a2')
    const siblingAt = outcome.order.indexOf('b2')
    expect(Math.abs(at - siblingAt)).toBe(1)
    expect(at).toBe(order.indexOf('a2') + 1)
    expect(outcome.order.filter((id) => id === 'a2')).toHaveLength(1)
    expect([...outcome.order].sort()).toEqual([...order].sort())
  })
})

describe('#1740 §2 the edge is a no-op that announces itself', () => {
  it('Alt+Up on the first row of a section does not spill into the previous', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'a2', direction: 'up' })
    expect(outcome.moved).toBe(false)
    expect(outcome.order).toEqual(order)
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
    expect(outcome.announcement).toContain('Work')
  })

  it('Alt+Down on the last row of a section does not spill into the next', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'b2', direction: 'down' })
    expect(outcome.moved).toBe(false)
    expect(outcome.order).toEqual(order)
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
  })

  it('a single-row section is an edge in both directions', () => {
    for (const direction of ['up', 'down'] as const) {
      const outcome = reorderWithinSection({ order, blocks, rowId: 'a3', direction })
      expect(outcome.moved).toBe(false)
      expect(outcome.announcement).toContain('Unassigned')
    }
  })

  it('a row that is in no block at all is refused, not guessed at', () => {
    const outcome = reorderWithinSection({ order, blocks, rowId: 'ghost', direction: 'up' })
    expect(outcome.moved).toBe(false)
    expect(outcome.order).toEqual(order)
    expect(outcome.announcement).toMatch(/not in a section/i)
  })
})

describe('#1740 §3 Alt+Left/Right change section, reading the rail\'s own blocks', () => {
  const destinations = railMoveToDestinations({
    blocks: [
      { id: 'api', name: 'API', custom: false },
      { id: 'sec_work', name: 'Work', custom: true },
      { id: 'unassigned', name: 'Unassigned', custom: false },
    ],
    currentSectionId: 'sec_work',
  })

  it('right moves to the NEXT selectable destination', () => {
    const outcome = moveToAdjacentSection({
      order,
      destinations,
      blocks,
      rowId: 'a2',
      currentSectionId: 'sec_work',
      direction: 'right',
    })
    expect(outcome.moved).toBe(true)
    expect(outcome.targetId).toBe('unassigned')
    expect(outcome.announcement).toContain('Unassigned')
  })

  it('left moves to the PREVIOUS selectable destination', () => {
    const twoCustom = railMoveToDestinations({
      blocks: [
        { id: 'sec_ops', name: 'Ops', custom: true },
        { id: 'sec_work', name: 'Work', custom: true },
        { id: 'unassigned', name: 'Unassigned', custom: false },
      ],
      currentSectionId: 'sec_work',
    })
    const outcome = moveToAdjacentSection({
      order,
      destinations: twoCustom,
      blocks,
      rowId: 'a2',
      currentSectionId: 'sec_work',
      direction: 'left',
    })
    expect(outcome.targetId).toBe('sec_ops')
    expect(outcome.moved).toBe(true)
  })

  it('will NOT file a row into an auto section the Move-to submenu refuses', () => {
    // The only block to the left of `sec_work` here is the auto `api` group.
    // #1714 already decided that is not a destination, so Alt+Left must land
    // on the same answer rather than a private one that would move the row
    // straight back.
    const outcome = moveToAdjacentSection({
      order,
      destinations,
      blocks,
      rowId: 'a2',
      currentSectionId: 'sec_work',
      direction: 'left',
    })
    expect(outcome.targetId).toBeNull()
    expect(outcome.moved).toBe(false)
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
  })

  it('skips a non-selectable neighbour rather than stopping at it', () => {
    // The row sits under the auto 'api' block. Alt+Right must find a real
    // destination, not the auto group it is already rendered in.
    const outcome = moveToAdjacentSection({
      order,
      destinations,
      blocks,
      rowId: 'a1',
      currentSectionId: 'api',
      direction: 'right',
    })
    expect(outcome.targetId).toBe('sec_work')
  })

  it('a section change repositions the row, reusing the drag helpers', () => {
    const outcome = moveToAdjacentSection({
      order,
      destinations,
      blocks,
      rowId: 'a2',
      currentSectionId: 'sec_work',
      direction: 'right',
    })
    // Unassigned currently holds only `a3`; the moved row lands at its head,
    // which is the same "immediately before the destination's first row" rule
    // drag-to-row uses.
    const movedAt = outcome.order?.indexOf('a2') ?? -1
    const targetHeadAt = outcome.order?.indexOf('a3') ?? -1
    expect(movedAt).toBe(targetHeadAt - 1)
    expect([...outcome.order!].sort()).toEqual([...order].sort())
  })

  it('the first/last destination is an edge, announced rather than silent', () => {
    const left = moveToAdjacentSection({
      order,
      destinations,
      blocks,
      rowId: 'a1',
      currentSectionId: 'api',
      direction: 'left',
    })
    expect(left.moved).toBe(false)
    expect(left.targetId).toBeNull()
    expect(left.announcement).toContain(RAIL_REORDER_EDGE_REASON)
  })

  it('reuses #1714\'s destination list — a third list is not built here', () => {
    // The model takes the SAME `RailMoveToDestination[]` the Move-to submenu
    // renders, so the two cannot disagree about what is a destination.
    expect(destinations.map((d) => d.id)).toContain('sec_work')
    expect(destinations.find((d) => d.id === 'api')?.selectable).toBe(false)
  })
})

/* ==================================================================== */
/* #1740 — the PIN GRID is the same verb in its own scope                 */
/* ==================================================================== */

describe('#1740 §1 Alt+Up/Down reorder pins within the pin grid', () => {
  const pins = [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }]

  it('swaps a pin with the tile above it', () => {
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'p2',
      direction: 'up',
    })
    expect(outcome.moved).toBe(true)
    expect(outcome.order).toEqual(['p2', 'p1', 'p3'])
  })

  it('swaps a pin with the tile below it', () => {
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'p1',
      direction: 'down',
    })
    expect(outcome.moved).toBe(true)
    expect(outcome.order).toEqual(['p2', 'p1', 'p3'])
  })

  it('never spills into a section: a reorder is confined to the grid', () => {
    // The sections are not even an input here — the grid is the whole scope,
    // so a swap physically cannot reach a row that is filed under a section.
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'p3',
      direction: 'down',
    })
    expect([...outcome.order].sort()).toEqual(['p1', 'p2', 'p3'])
    expect(outcome.moved).toBe(false)
  })

  it('the first tile is an edge, announced with the grid it is stuck in', () => {
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'p1',
      direction: 'up',
    })
    expect(outcome.moved).toBe(false)
    expect(outcome.order).toEqual(['p1', 'p2', 'p3'])
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
    expect(outcome.announcement).toContain(RAIL_PIN_GRID_NAME)
  })

  it('the last tile is an edge in the other direction', () => {
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'p3',
      direction: 'down',
    })
    expect(outcome.moved).toBe(false)
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
  })

  it('a single pin is an edge in both directions — never a silent nothing', () => {
    for (const direction of ['up', 'down'] as const) {
      const one = [{ id: 'p1' }]
      const outcome = reorderWithinPinGrid({ pins: one, visiblePins: one, pinId: 'p1', direction })
      expect(outcome.moved).toBe(false)
      expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
    }
  })

  it('reorders against the tiles the grid SHOWS, while a hidden pin keeps its own slot', () => {
    // `p0` is stored but not rendered (hidden / deleted). The operator sees
    // p1, p2, p3 — so Alt+Up on p2 must swap p1 and p2, and p0 must not be
    // dragged into the middle of a visible order nobody asked for.
    const stored = [{ id: 'p0' }, { id: 'p1' }, { id: 'p2' }, { id: 'p3' }]
    const outcome = reorderWithinPinGrid({
      pins: stored,
      visiblePins: [{ id: 'p1' }, { id: 'p2' }, { id: 'p3' }],
      pinId: 'p2',
      direction: 'up',
    })
    expect(outcome.moved).toBe(true)
    expect(outcome.order).toEqual(['p0', 'p2', 'p1', 'p3'])
  })

  it('a tile that is not in the grid is refused, not guessed at', () => {
    const outcome = reorderWithinPinGrid({
      pins,
      visiblePins: pins,
      pinId: 'stray',
      direction: 'down',
    })
    expect(outcome.moved).toBe(false)
    expect(outcome.order).toEqual(['p1', 'p2', 'p3'])
    expect(outcome.announcement).toMatch(/not in a section/i)
  })
})

describe('#1740 §3 Alt+Right files a pin into the adjacent SECTION, and leaves the grid', () => {
  const sectionDestinations = railMoveToDestinations({
    blocks: [
      { id: 'api', name: 'API', custom: false },
      { id: 'sec_work', name: 'Work', custom: true },
      { id: 'unassigned', name: 'Unassigned', custom: false },
    ],
    currentSectionId: RAIL_PIN_GRID_ID,
  })
  const visiblePins = [{ id: 'p1' }, { id: 'p2' }]
  const sectionBlocks: RailReorderBlockLike[] = [
    { id: 'api', name: 'API', rows: [{ id: 'a1' }] },
    { id: 'sec_work', name: 'Work', rows: [{ id: 'w1' }] },
    { id: 'unassigned', name: 'Unassigned', rows: [] },
  ]
  const order = ['a1', 'w1']

  it('right lands on the FIRST selectable section below the grid', () => {
    const outcome = movePinToAdjacentSection({
      order,
      sectionDestinations,
      blocks: sectionBlocks,
      visiblePins,
      pinId: 'p1',
      direction: 'right',
    })
    expect(outcome.moved).toBe(true)
    // The auto `api` group is skipped, exactly as Move-to refuses it (#1714).
    expect(outcome.targetId).toBe('sec_work')
    expect(outcome.announcement).toContain('Work')
  })

  it('left is the grid\'s own edge — there is nothing above the pin grid', () => {
    const outcome = movePinToAdjacentSection({
      order,
      sectionDestinations,
      blocks: sectionBlocks,
      visiblePins,
      pinId: 'p1',
      direction: 'left',
    })
    expect(outcome.moved).toBe(false)
    expect(outcome.targetId).toBeNull()
    expect(outcome.order).toBeNull()
    expect(outcome.announcement).toContain(RAIL_REORDER_EDGE_REASON)
    expect(outcome.announcement).toContain(RAIL_PIN_GRID_NAME)
  })

  it('inserts the pin at the TOP of the destination, reusing the drag placement', () => {
    const outcome = movePinToAdjacentSection({
      order,
      sectionDestinations,
      blocks: sectionBlocks,
      visiblePins,
      pinId: 'p1',
      direction: 'right',
    })
    // Immediately before Work's first row — the same "above the target's first
    // row" rule a drop onto that row makes.
    expect(outcome.order?.indexOf('p1')).toBe(outcome.order?.indexOf('w1')! - 1)
    // The pin id was NOT in the rail order and now is: that is the unpin.
    expect(outcome.order).toContain('p1')
  })

  it('a grid whose next destination is empty still gets the pin, appended', () => {
    const outcome = movePinToAdjacentSection({
      order,
      sectionDestinations: [
        { id: RAIL_PIN_GRID_ID, name: RAIL_PIN_GRID_NAME, selectable: false, checked: true },
        { id: 'unassigned', name: 'Unassigned', selectable: true, checked: false },
      ],
      blocks: [{ id: 'unassigned', name: 'Unassigned', rows: [] }],
      visiblePins,
      pinId: 'p1',
      direction: 'right',
    })
    expect(outcome.targetId).toBe('unassigned')
    expect(outcome.order).toEqual(['a1', 'w1', 'p1'])
  })
})

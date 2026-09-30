/**
 * #1683 — the rail is rigid according to the NUMBER of pinned agents.
 *
 * The predecessor shipped a fixed 1/2/3 column ladder and treated "3" as a cap.
 * It was never a cap, it was the last number anyone wrote down:
 * `railWidthForColumns(4)` = 394 ≤ `MAX_RAIL_WIDTH` (420), and the grid really
 * does grow a 4th track (measured ~387px, `scripts/measure-pinned-grid.mjs`).
 * Meanwhile with 2 pins the 3-column detent described nothing on screen, so the
 * operator could not see what the rail had snapped to.
 *
 * The rule under test:
 *
 *     the rigid column detents are the widths that exactly fit
 *     1..min(pins, MAX_PINNED_COLUMNS) columns, and above the topmost of them
 *     the rail free-tracks to the ceiling.
 *
 * These are pure-function contracts. The wobble-vs-free-tracking claim underneath
 * them is a browser fact and is gated separately by
 * `scripts/measure-pinned-grid.mjs --by-pins`.
 */
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it } from 'vitest'
import { declarations, rule } from './helpers/cssRules'
import {
  AVATAR_ONLY_THRESHOLD,
  COLLAPSED_RAIL_WIDTH,
  FAV_GRID_GAP_PX,
  FAV_GRID_MARGIN_PX,
  FAV_TILE_TRACK_PX,
  FOUR_COL_RAIL_WIDTH,
  MAX_PINNED_COLUMNS,
  MAX_RAIL_WIDTH,
  ONE_COL_RAIL_WIDTH,
  RAIL_CHROME_PX,
  RAIL_COLUMN_GEOMETRY_CSS,
  RAIL_DETENT_ALWAYS,
  RAIL_SNAP_POINTS,
  RAIL_SNAP_THRESHOLD,
  RAIL_UNPINNED_SNAP_POINTS,
  THREE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  railColumnDetents,
  railSnapPointsForPins,
  railSnapStep,
  railSnapThresholdForPins,
  railWidthForColumns,
  snapRailWidth,
  snapRailWidthToPoints,
  topColumnDetent,
} from '../railResize'

beforeEach(() => localStorage.clear())

// The whole rule is "be rigid to the widths the pinned grid reflows at", so the
// numbers above are only meaningful while index.css still says this. jsdom never
// applies the stylesheet, so without this the geometry could drift silently.
//
// PARSED, not grepped: `declaration`/`declarations` read the brace-matched body
// of the `.os-fav-grid` rule and normalise whitespace, so a reformat is not a
// failure while a genuinely different VALUE is. `expect(css).toContain(...)` over
// a 6,400-line sheet would also pass on the same literal declared under an
// unrelated selector, which is the defect class this avoids.
const CSS = readFileSync(join(__dirname, '..', '..', 'index.css'), 'utf8')
const favGrid = () => declarations(rule(CSS, '.os-fav-grid'))

/** The stylesheet writes lengths in rem; the rail maths is in px at a 16px root. */
const ROOT_FONT_PX = 16
const px = (value: string): number => {
  const bare = value.trim().replace(/[)]+$/, '')
  const isRem = bare.endsWith('rem')
  return Number.parseFloat(bare) * (isRem ? ROOT_FONT_PX : 1)
}

describe('#1683 the detent math still matches the stylesheet', () => {
  it('.os-fav-grid still declares the track, gap, margin and anchoring it assumes', () => {
    const grid = favGrid()
    expect(grid['grid-template-columns']).toBe('repeat(auto-fill, 5.25rem)')
    expect(grid['gap']).toBe('0.5rem')
    expect(grid['margin']).toBe('0.35rem 0.75rem 0.5rem')
    // #1683 load-bearing: `start` is what makes free-tracking above the topmost
    // column detent safe — a tile's x must not depend on the container width.
    expect(grid['justify-content']).toBe('start')
    expect(grid['justify-items']).toBe('center')
  })

  it('the module derives its track/gap/margin constants FROM the stylesheet', () => {
    // Stronger than the "the inlined snippet is a substring" check this
    // replaces: recompute the column widths straight from the parsed
    // declarations and require the exported maths to agree. A stylesheet edit
    // that changes any of these three values now fails HERE, with a number, and
    // the old assertion could not tell a changed value from a reformatted one.
    const grid = favGrid()
    const track = px(grid['grid-template-columns'].split(',')[1].trim())
    const gap = px(grid['gap'])
    const [marginTop, marginX, marginBottom] = grid['margin'].split(/\s+/).map(px)
    expect(track).toBe(FAV_TILE_TRACK_PX)
    expect(gap).toBe(FAV_GRID_GAP_PX)
    expect(marginX * 2).toBe(FAV_GRID_MARGIN_PX)
    expect(marginTop).toBeGreaterThan(0)
    expect(marginBottom).toBeGreaterThan(0)
    // …and the detent ladder really is "N tracks, N-1 gaps, plus the margins".
    for (const cols of [1, 2, 3, 4]) {
      expect(railWidthForColumns(cols)).toBe(
        Math.ceil(cols * track + (cols - 1) * gap + marginX * 2 + RAIL_CHROME_PX),
      )
    }
  })

  it('the CSS the module inlines is a subset of the real rule', () => {
    // RAIL_COLUMN_GEOMETRY_CSS is documentation + a drift tripwire. Parsed
    // comparison, property by property: each `prop: value` line in the inlined
    // snippet must be the value the stylesheet actually gives that property.
    const grid = favGrid()
    for (const line of RAIL_COLUMN_GEOMETRY_CSS.trim().split('\n')) {
      const [prop, value] = line.split(':').map((part) => part.trim())
      expect(grid[prop.toLowerCase()]).toBe(value.replace(/;$/, ''))
    }
  })

  it('MAX_PINNED_COLUMNS is what the geometry seats under the ceiling, not a written-down 3', () => {
    const grid = favGrid()
    const track = px(grid['grid-template-columns'].split(',')[1].trim())
    const gap = px(grid['gap'])
    const marginX = px(grid['margin'].split(/\s+/)[1])
    // Recount from the parsed stylesheet: the largest N whose grid fits.
    let expected = 1
    while (Math.ceil((expected + 1) * track + expected * gap + marginX * 2 + RAIL_CHROME_PX) <= MAX_RAIL_WIDTH) {
      expected += 1
    }
    expect(MAX_PINNED_COLUMNS).toBe(expected)
    expect(MAX_PINNED_COLUMNS).toBe(4)
    // The next column genuinely does not fit, so the ceiling is real.
    expect(
      Math.ceil((expected + 1) * track + expected * gap + marginX * 2 + RAIL_CHROME_PX),
    ).toBeGreaterThan(MAX_RAIL_WIDTH)
  })
})

/** The exact detent set for each pin count, written out longhand on purpose. */
const BY_PINS: ReadonlyArray<{ pins: number; label: string; detents: readonly number[] }> = [
  { pins: 0, label: 'no pins', detents: [0, 88, 420] },
  { pins: 1, label: 'one pin', detents: [0, 88, 118, 420] },
  { pins: 2, label: 'two pins', detents: [0, 88, 118, 210, 420] },
  { pins: 3, label: 'three pins', detents: [0, 88, 118, 210, 302, 420] },
  // #1683: 4 columns is the measured ceiling, so 5 and 12 pins are identical.
  { pins: 5, label: 'five pins (past the 4-column ceiling)', detents: [0, 88, 118, 210, 302, 394, 420] },
  { pins: 12, label: 'twelve pins (a full pool)', detents: [0, 88, 118, 210, 302, 394, 420] },
]

describe('#1683 rigid detents are derived from the pin count', () => {
  it.each(BY_PINS)('$label → $detents', ({ pins, detents }) => {
    expect(railSnapPointsForPins(pins)).toEqual([...detents])
    expect(railSnapPointsForPins(pins)).toStrictEqual([...detents])
  })

  it('the detent set is {0, 88} ∪ {1..min(pins, MAX_PINNED_COLUMNS)} ∪ {420}', () => {
    for (const { pins, detents } of BY_PINS) {
      const columns = railColumnDetents(pins)
      expect(columns.length).toBe(Math.min(pins, MAX_PINNED_COLUMNS))
      expect(detents).toEqual([0, ULTRACOMPACT_RAIL_WIDTH, ...columns, MAX_RAIL_WIDTH])
      // 0 and 88 are in every state; 420 closes every state.
      expect(detents).toContain(COLLAPSED_RAIL_WIDTH)
      expect(detents).toContain(ULTRACOMPACT_RAIL_WIDTH)
      expect(detents).toContain(MAX_RAIL_WIDTH)
    }
  })

  it('the 3-column detent is not a stop for 2 pins — it describes nothing on screen', () => {
    expect(railSnapPointsForPins(2)).not.toContain(THREE_COL_RAIL_WIDTH)
    // …and it IS a stop as soon as a third pin asks for three columns.
    expect(railSnapPointsForPins(3)).toContain(THREE_COL_RAIL_WIDTH)
  })

  it('a 4-column detent exists, because 4 columns fit inside MAX_RAIL_WIDTH', () => {
    // The whole point: "3" was never the cap. 394 ≤ 420, so four columns are
    // seatable and get a detent; five (486) do not and cannot.
    expect(FOUR_COL_RAIL_WIDTH).toBeLessThanOrEqual(MAX_RAIL_WIDTH)
    expect(MAX_PINNED_COLUMNS).toBe(4)
    expect(railSnapPointsForPins(4)).toContain(FOUR_COL_RAIL_WIDTH)
    // Every set is a subset of the full ladder, which now has 7 entries.
    expect(RAIL_SNAP_POINTS).toEqual([0, 88, 118, 210, 302, 394, 420])
    for (const { detents } of BY_PINS) {
      for (const point of detents) expect(RAIL_SNAP_POINTS).toContain(point)
    }
  })

  it('column counts beyond the ceiling clamp instead of inventing widths', () => {
    expect(railColumnDetents(MAX_PINNED_COLUMNS)).toHaveLength(MAX_PINNED_COLUMNS)
    expect(railColumnDetents(5)).toEqual(railColumnDetents(4))
    expect(railColumnDetents(12)).toEqual(railColumnDetents(4))
    expect(railColumnDetents(99)).toEqual(railColumnDetents(4))
    // A nonsense count is a caller bug, not a licence to drop the guard.
    expect(railColumnDetents(-3)).toEqual([])
  })

  it('0 pins is the existing unpinned contract, unchanged', () => {
    expect(railSnapPointsForPins(0)).toEqual(RAIL_UNPINNED_SNAP_POINTS)
    expect(railColumnDetents(0)).toEqual([])
    for (const gone of [ONE_COL_RAIL_WIDTH, TWO_COL_RAIL_WIDTH, THREE_COL_RAIL_WIDTH, FOUR_COL_RAIL_WIDTH]) {
      expect(RAIL_UNPINNED_SNAP_POINTS).not.toContain(gone)
    }
  })

  it('every detent set is strictly ascending — the arrow lane has no duplicates', () => {
    for (const { pins } of BY_PINS) {
      const points = railSnapPointsForPins(pins)
      for (let i = 1; i < points.length; i += 1) {
        expect(points[i]).toBeGreaterThan(points[i - 1])
      }
    }
  })
})

describe('the topmost column detent never exceeds what the pins need', () => {
  it('it is exactly the width that seats every pin in one row', () => {
    // 0 pins is its own case: no grid, so the rigid region ends at the
    // ultra-compact tier, which is meaningful without pins.
    expect(topColumnDetent(0)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    for (const { pins } of BY_PINS.filter((p) => p.pins > 0)) {
      const columns = Math.min(pins, MAX_PINNED_COLUMNS)
      expect(topColumnDetent(pins)).toBe(railWidthForColumns(columns))
      expect(topColumnDetent(pins)).toBe(railSnapPointsForPins(pins).at(-2))
      // It is a detent, and it is the highest one below the ceiling.
      const points = railSnapPointsForPins(pins)
      expect(points).toContain(topColumnDetent(pins))
      expect(points.filter((p) => p < MAX_RAIL_WIDTH).at(-1)).toBe(topColumnDetent(pins))
    }
  })

  it('more pins never make the rail rigid to a NARROWER width', () => {
    // Monotone: the topmost detent is non-decreasing in the pin count, so
    // pinning more agents never yanks a wide rail back in.
    let previous = 0
    for (let pins = 0; pins <= 12; pins += 1) {
      const top = topColumnDetent(pins)
      expect(top).toBeGreaterThanOrEqual(previous)
      previous = top
    }
  })

  it('free-tracking begins strictly above the topmost column detent', () => {
    for (const { pins } of BY_PINS) {
      if (pins === 0) continue
      const top = topColumnDetent(pins)
      // At the detent itself: still rigid.
      expect(railSnapThresholdForPins(top, pins)).toBe(RAIL_DETENT_ALWAYS)
      // One pixel above: free. "Strictly" is the load-bearing word.
      expect(railSnapThresholdForPins(top + 1, pins)).toBe(RAIL_SNAP_THRESHOLD)
      // And it stays free all the way to the ceiling.
      expect(railSnapThresholdForPins(MAX_RAIL_WIDTH, pins)).toBe(RAIL_SNAP_THRESHOLD)
    }
  })

  it('2 pins: rigid at 0 / 88 / 118 / 210, free from 210 to 420', () => {
    expect(railSnapPointsForPins(2)).toEqual([0, 88, 118, 210, 420])
    // Anywhere in the free band, a mid-detent release is left where it was let
    // go — with 2 pins there is no 3-column stop to snap to.
    for (const width of [240, 260, 275, 301, 340, 395]) {
      expect(snapRailWidthToPoints(width, undefined, RAIL_SNAP_THRESHOLD, 2)).toBe(width)
    }
    // …and at/below 210 the drag is quantised onto a real stop.
    expect(snapRailWidthToPoints(130, undefined, RAIL_DETENT_ALWAYS, 2)).toBe(ONE_COL_RAIL_WIDTH)
    expect(snapRailWidthToPoints(180, undefined, RAIL_DETENT_ALWAYS, 2)).toBe(TWO_COL_RAIL_WIDTH)
    expect(snapRailWidthToPoints(210, undefined, RAIL_DETENT_ALWAYS, 2)).toBe(TWO_COL_RAIL_WIDTH)
  })
})

describe('#1262 (not regressed) RAIL_DETENT_ALWAYS still guards the rigid region', () => {
  it('is used at and below the topmost column detent for every pin count', () => {
    // 0 pins: no grid to protect — the whole range free-tracks. That is the
    // #1683 empty-pool behaviour, and it is the same rule with no column detents.
    for (const width of [AVATAR_ONLY_THRESHOLD + 1, ONE_COL_RAIL_WIDTH, 150, 200, 250, 300, 350, 400]) {
      expect(railSnapThresholdForPins(width, 0)).toBe(RAIL_SNAP_THRESHOLD)
    }
    for (const { pins } of BY_PINS.filter((p) => p.pins > 0)) {
      for (const width of [AVATAR_ONLY_THRESHOLD + 1, ONE_COL_RAIL_WIDTH, 150, 200, 250, 300, 350, 400]) {
        const top = topColumnDetent(pins)
        const expected = width > top ? RAIL_SNAP_THRESHOLD : RAIL_DETENT_ALWAYS
        expect(railSnapThresholdForPins(width, pins)).toBe(expected)
      }
    }
  })

  it('is NOT used above the topmost column detent, for any pin count', () => {
    for (const { pins } of BY_PINS) {
      for (let width = topColumnDetent(pins) + 1; width <= MAX_RAIL_WIDTH; width += 7) {
        expect(railSnapThresholdForPins(width, pins)).not.toBe(RAIL_DETENT_ALWAYS)
      }
    }
  })

  it('two widths on either side of a column boundary agree inside the rigid region', () => {
    // The wobble itself: 1→2 columns happens at ~201px. Quantised, widths on
    // both sides of that boundary resolve to the same detent, so the grid
    // cannot reflow under the cursor.
    expect(snapRailWidthToPoints(150, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(ONE_COL_RAIL_WIDTH)
    expect(snapRailWidthToPoints(200, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(TWO_COL_RAIL_WIDTH)
    expect(snapRailWidthToPoints(202, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(TWO_COL_RAIL_WIDTH)
    // Unquantised, the same widths are free-floating — which is the bug #1262
    // named. (190 is clear of the 14px slop around 210; 150 and 190 straddle the
    // ~201px boundary and both hold, so the grid cannot reflow mid-drag.)
    expect(snapRailWidthToPoints(150, undefined, RAIL_SNAP_THRESHOLD, 3)).toBe(150)
    expect(snapRailWidthToPoints(190, undefined, RAIL_SNAP_THRESHOLD, 3)).toBe(190)
  })

  it('the exported constant is intact and the CSS still has the geometry it is derived from', () => {
    expect(RAIL_DETENT_ALWAYS).toBe(Number.POSITIVE_INFINITY)
    expect(RAIL_COLUMN_GEOMETRY_CSS).toContain('repeat(auto-fill, 5.25rem)')
    expect(RAIL_COLUMN_GEOMETRY_CSS).toContain('justify-content: start')
  })
})

describe('#1683 arrow keys walk the same lane the drag walks, per pin count', () => {
  it('walks exactly the pin-dependent detent set, in order', () => {
    for (const { pins, detents } of BY_PINS) {
      const walked = [detents[0]]
      let width = detents[0]
      for (let i = 1; i < detents.length; i += 1) {
        width = railSnapStep(width, 1, undefined, pins)
        walked.push(width)
      }
      expect(walked).toEqual([...detents])
      // …and back down again, off the same set, ending on the narrowest stop.
      const back: number[] = []
      for (let i = 1; i < detents.length; i += 1) {
        width = railSnapStep(width, -1, undefined, pins)
        back.push(width)
      }
      expect(back).toEqual([...detents].reverse().slice(1))
    }
  })

  it('the ceiling floors the walk: ArrowRight past the widest detent does nothing', () => {
    for (const { pins, detents } of BY_PINS) {
      const widest = detents[detents.length - 1]
      const narrowest = detents[0]
      expect(railSnapStep(widest, 1, undefined, pins)).toBe(widest)
      expect(railSnapStep(narrowest, -1, undefined, pins)).toBe(narrowest)
    }
  })

  it('2 pins: 88 → 118 → 210 → 420, never touching the 3-column stop', () => {
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, 2)).toBe(ONE_COL_RAIL_WIDTH)
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, 1, undefined, 2)).toBe(TWO_COL_RAIL_WIDTH)
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, 1, undefined, 2)).toBe(MAX_RAIL_WIDTH)
    expect(railSnapStep(MAX_RAIL_WIDTH, 1, undefined, 2)).toBe(MAX_RAIL_WIDTH)
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, -1, undefined, 2)).toBe(ONE_COL_RAIL_WIDTH)
  })

  it('3 pins keeps the 3-column stop the 2-pin rail skipped', () => {
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(THREE_COL_RAIL_WIDTH)
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(MAX_RAIL_WIDTH)
  })

  it('4+ pins reaches the 4-column detent', () => {
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 4)).toBe(FOUR_COL_RAIL_WIDTH)
    expect(railSnapStep(FOUR_COL_RAIL_WIDTH, 1, undefined, 4)).toBe(MAX_RAIL_WIDTH)
    // 5 and 12 pins cannot seat a 5th column, so the lane is the same.
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 12)).toBe(FOUR_COL_RAIL_WIDTH)
  })

  it('0 pins: 88 → 420 directly', () => {
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, 0)).toBe(MAX_RAIL_WIDTH)
    expect(railSnapStep(MAX_RAIL_WIDTH, -1, undefined, 0)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, -1, undefined, 0)).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('arrow and drag agree above the collapse zone', () => {
    for (const { pins, detents } of BY_PINS) {
      for (const point of detents.filter((p) => p > ONE_COL_RAIL_WIDTH)) {
        // A drag released exactly on a detent must settle there, whatever the
        // width-aware threshold resolves to for that width.
        expect(snapRailWidthToPoints(point, undefined, railSnapThresholdForPins(point, pins), pins)).toBe(point)
      }
    }
  })

  it('the 1-column detent is a keyboard/load stop, not a drag stop (pre-existing #1289)', () => {
    // `snapRailWidthToPoints` owns the collapse zone for widths <= ONE_COL: a
    // drag to 118 settles on the ultra-compact tier (88) rather than the 1-col
    // detent. That predates #1683 and is deliberately not changed here — the
    // operator did not ask for it, and the arrow lane plus `loadRailWidth` and
    // `defaultRailWidth` already put the rail on 118. Pinned so the
    // asymmetry is deliberate and visible rather than a surprise.
    for (const pins of [0, 1, 2, 3, 12]) {
      expect(snapRailWidthToPoints(ONE_COL_RAIL_WIDTH, undefined, railSnapThresholdForPins(ONE_COL_RAIL_WIDTH, pins), pins)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    }
    // The keyboard and the loader both reach it.
    for (const pins of [1, 2, 3]) {
      expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, pins)).toBe(ONE_COL_RAIL_WIDTH)
    }
  })

  it('a right-docked rail walks the same pin-dependent set (#816)', () => {
    // The set, not the direction: `detentsForSide` reverses the in-flow order
    // for a right-docked rail, but `railSnapStep` re-sorts ascending before
    // stepping, so the keyboard lane is the same set of widths on both sides.
    // Direction mirroring lives in `useRailResize` (`growDelta`), which is
    // asserted in the #816 rail-side tests, not here.
    for (const { pins, detents } of BY_PINS) {
      const walked: number[] = [detents[0]]
      let width = detents[0]
      for (let i = 1; i < detents.length; i += 1) {
        width = railSnapStep(width, 1, 'right', pins)
        walked.push(width)
      }
      expect(walked).toEqual([...detents])
      // The mirror is symmetric: opposite sign, same adjacent stop.
      for (let i = 1; i < detents.length; i += 1) {
        expect(railSnapStep(detents[i], -1, 'right', pins)).toBe(detents[i - 1])
      }
    }
  })

  it('a right-docked rail snaps to the same pin-dependent widths', () => {
    // This IS the direction-sensitive path (`detentsForSide` feeds a nearest
    // search), so it must land on the same widths a left-docked rail does.
    // (Above the collapse zone only — see the 1-column-detent test for why.)
    for (const { pins, detents } of BY_PINS) {
      for (const point of detents.filter((p) => p > ONE_COL_RAIL_WIDTH)) {
        expect(snapRailWidthToPoints(point + 5, 'right', railSnapThresholdForPins(point, pins), pins)).toBe(point)
      }
      expect(snapRailWidthToPoints(10, 'right', railSnapThresholdForPins(10, pins), pins)).toBe(COLLAPSED_RAIL_WIDTH)
    }
  })

})

describe('#1683 the fail-safe default is unchanged', () => {
  it('omitting the pin count keeps the #1262 guard armed', () => {
    // Default pinnedCount = 1 ("the grid is on screen"). With 1 pin the topmost
    // column detent is 118, so the guard is armed up to 118 and free-tracking
    // starts above it. The fail-safe is a *narrower* rigid region than the old
    // fixed ladder, but never an absent one.
    expect(railSnapThresholdForPins(ONE_COL_RAIL_WIDTH)).toBe(RAIL_DETENT_ALWAYS)
    expect(railSnapThresholdForPins(ULTRACOMPACT_RAIL_WIDTH)).toBe(RAIL_DETENT_ALWAYS)
    expect(railSnapThresholdForPins(ONE_COL_RAIL_WIDTH + 1)).toBe(RAIL_SNAP_THRESHOLD)
    // The default set is the 1-pin set, not the empty-pool one — a caller that
    // forgot to thread the count does not silently lose the grid's detents.
    expect(railSnapPointsForPins(1)).toEqual([0, 88, 118, 420])
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, 1)).toBe(MAX_RAIL_WIDTH)
    // …and it is NOT the widest set: that would be a caller bug, not a default.
    expect(railSnapPointsForPins(1).length).toBeLessThan(RAIL_SNAP_POINTS.length)
  })

  it('a caller that omits it never gets a wider detent set than one pin earns', () => {
    // 1 pin is the narrowest pinned state, so it is the most conservative.
    for (const pins of [2, 3, 4, 12]) {
      expect(railSnapPointsForPins(pins).length).toBeGreaterThanOrEqual(railSnapPointsForPins(1).length)
      for (const point of railSnapPointsForPins(1)) {
        expect(railSnapPointsForPins(pins)).toContain(point)
      }
    }
  })

  it('the legacy snapRailWidth helper takes the same pin count', () => {
    expect(snapRailWidth(260, undefined, 0)).toBe(260)
    expect(snapRailWidth(260, undefined, 2)).toBe(260)
    expect(snapRailWidth(200, undefined, 2)).toBe(TWO_COL_RAIL_WIDTH)
    expect(snapRailWidth(200, undefined, 1)).toBe(200)
    expect(snapRailWidth(100, undefined, 0)).toBe(ULTRACOMPACT_RAIL_WIDTH)
  })
})

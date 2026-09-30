/**
 * #1683 — the rail is rigid only where pinning gives it a reason, and only up
 * to the width those pins need.
 *
 * Two things follow from the grid being on screen:
 *
 *  - a column detent is only a stop if the pin count earns it, so 2 pins do not
 *    stop at the 3-column width, and there is now a 4-column detent at all
 *    (394px) because four columns genuinely fit inside `MAX_RAIL_WIDTH`;
 *  - the #1262 quantisation is armed at or below the topmost column detent and
 *    released strictly above it, because a tile's column is `index % columns`:
 *    a pin that is not in row 1 jumps sideways on every track boundary, and
 *    above the topmost detent no pin is.
 *
 * These are the hook-level contracts:
 *
 *  - unpinned: a release at ~180px lands at ~180px, mid-drag and on release,
 *    and still settles on 0 / 88 / 420;
 *  - 2 pins: the identical gesture lands on the 2-column detent, but 240px —
 *    above the topmost detent those pins earn — holds verbatim;
 *  - the same widths quantise or free-track purely as a function of the pin
 *    count, and the arrow keys walk exactly the set the drag sticks to.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { act, renderHook } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { useRailResize } from '../sidebar/useRailResize'
import {
  ONE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  THREE_COL_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  COLLAPSED_RAIL_WIDTH,
  FOUR_COL_RAIL_WIDTH,
  RAIL_DETENT_ALWAYS,
  RAIL_SNAP_THRESHOLD,
  railSnapPointsForPins,
  railSnapThresholdForPins,
  topColumnDetent,
  RAIL_WIDTH_STORAGE_KEY,
} from '../../lib/railResize'

const SIDEBAR_SRC = readFileSync(join(__dirname, '..', 'AgentSidebar.tsx'), 'utf8')

/** Start every drag from the one-column detent so the maths is unambiguous. */
const START_WIDTH = ONE_COL_RAIL_WIDTH
const TARGET_WIDTH = 180

function dragTo(clientX: number, pinnedCount?: number) {
  localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(START_WIDTH))
  const view = renderHook(() => useRailResize({ narrow: false, pinnedCount }))
  act(() => view.result.current.beginResizeDrag(0, 1, null))
  act(() => {
    window.dispatchEvent(new PointerEvent('pointermove', { clientX, pointerId: 1 }))
  })
  // Mid-drag, before the pointer is released.
  const midDrag = view.result.current.railWidth
  act(() => {
    window.dispatchEvent(new PointerEvent('pointerup', { clientX, pointerId: 1 }))
  })
  return { result: view.result, midDrag }
}

describe('#1683 unpinned rail free-tracks between the two real stops', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => localStorage.clear())

  it('an unpinned drag to ~180px stays at ~180px, live and on release', () => {
    const delta = TARGET_WIDTH - START_WIDTH
    const { result, midDrag } = dragTo(delta, 0)
    expect(result.current.railWidth).toBe(TARGET_WIDTH)
    expect(midDrag).toBe(TARGET_WIDTH)
    // …and persistence agrees with the rendered width.
    expect(localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBe(String(TARGET_WIDTH))
  })

  it('the identical drag with pins rendered settles on a column detent', () => {
    // 180px is below the 2-column detent (210) and above the 1-column detent
    // (118), so 2 pins — which earn exactly those two — quantise it onto 210.
    // 1 pin earns only the 1-column detent, whose whole region is the collapse
    // zone, so a 1-pin rail has nothing to quantise 180 onto and free-tracks.
    const delta = TARGET_WIDTH - START_WIDTH
    const two = dragTo(delta, 2)
    expect(two.result.current.railWidth).toBe(TWO_COL_RAIL_WIDTH)
    expect(two.midDrag).toBe(TWO_COL_RAIL_WIDTH)
    expect(localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBe(String(TWO_COL_RAIL_WIDTH))

    const one = dragTo(delta, 1)
    expect(one.result.current.railWidth).toBe(TARGET_WIDTH)
  })

  it('free-tracking starts strictly above the topmost column detent (#1683)', () => {
    // 2 pins: rigid up to 210, free above it. 240 is above the topmost detent
    // and more than the 14px slop away from it, so it is held verbatim — the
    // operator chose it, and no pin is at risk of re-flowing.
    const free = dragTo(240 - START_WIDTH, 2)
    expect(free.result.current.railWidth).toBe(240)
    expect(free.midDrag).toBe(240)

    // 3 pins: the topmost detent moves to 302, so 240 is now INSIDE the rigid
    // region and quantises onto 210. Same width, same drag, different pin count.
    const rigid = dragTo(240 - START_WIDTH, 3)
    expect(rigid.result.current.railWidth).toBe(TWO_COL_RAIL_WIDTH)

    // 3 pins: topmost detent 302, so 340 free-tracks (38px clear of 302, 80px
    // from the ceiling) and 250 (inside the rigid region, nearer 210 than 302)
    // snaps to 210.
    const free3 = dragTo(340 - START_WIDTH, 3)
    expect(free3.result.current.railWidth).toBe(340)
    const below3 = dragTo(250 - START_WIDTH, 3)
    expect(below3.result.current.railWidth).toBe(TWO_COL_RAIL_WIDTH)
  })

  it('with 4+ pins the free band closes — the ladder fills the rail (#1683)', () => {
    // The topmost column detent for 4 pins is the 4-column width (394), and the
    // ceiling is 420: a 26px band, with 14px of snap slop at each end. So there
    // is NO width a 4-pin rail can free-track to — it is rigid end to end.
    //
    // That is the rule working, not failing. Four columns is all the rail can
    // seat, so a rail holding four pins has nothing left to scale into: the
    // operator's own pins have consumed the whole range. Worth pinning because
    // it is a real behaviour of the design, and because it falls out of
    // MAX_PINNED_COLUMNS rather than anything hand-written.
    expect(topColumnDetent(4)).toBe(FOUR_COL_RAIL_WIDTH)
    expect(MAX_RAIL_WIDTH - FOUR_COL_RAIL_WIDTH).toBeLessThan(2 * RAIL_SNAP_THRESHOLD)
    // 340 is below 394 → rigid → the nearest earned detent is 302.
    const below = dragTo(340 - START_WIDTH, 4)
    expect(below.result.current.railWidth).toBe(THREE_COL_RAIL_WIDTH)
    // 410 is above 394, but only 10px from the ceiling → still a detent.
    const near = dragTo(410 - START_WIDTH, 4)
    expect(near.result.current.railWidth).toBe(MAX_RAIL_WIDTH)
  })

  it('unpinned still settles on collapsed, ultra-compact and max', () => {
    // Dragged width 30 → below the collapse threshold (52) → divider only.
    const shut = dragTo(30 - START_WIDTH, 0)
    expect(shut.result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
    expect(shut.result.current.isCollapsed).toBe(true)

    // Dragged width 100 → the avatar-only tier.
    const compact = dragTo(100 - START_WIDTH, 0)
    expect(compact.result.current.railWidth).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(compact.result.current.isAvatarOnly).toBe(true)

    // Dragged width 412 → within the 14px slop of the ceiling.
    const wide = dragTo(412 - START_WIDTH, 0)
    expect(wide.result.current.railWidth).toBe(MAX_RAIL_WIDTH)

    // Dragged past the ceiling → clamped, never parked beyond it.
    const over = dragTo(900 - START_WIDTH, 0)
    expect(over.result.current.railWidth).toBe(MAX_RAIL_WIDTH)
  })

  it('#1262: with pins the arrow keys still walk every detent the pin count earns', () => {
    // #1683: the lane is a function of the pin count. 3 pins earn the 1/2/3
    // column detents, so the walk is the six-stop ladder.
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(MAX_RAIL_WIDTH))
    const { result } = renderHook(() => useRailResize({ narrow: false, pinnedCount: 3 }))
    const step = (key: string) =>
      act(() => {
        result.current.handleResizeKeyDown({
          key,
          preventDefault: () => {},
        } as unknown as React.KeyboardEvent<HTMLDivElement>)
      })

    const walked: number[] = [result.current.railWidth]
    for (let i = 0; i < railSnapPointsForPins(3).length; i += 1) {
      step('ArrowLeft')
      walked.push(result.current.railWidth)
    }
    // Walking down from the ceiling visits every stop below it, in order.
    expect(walked).toEqual([
      MAX_RAIL_WIDTH,
      THREE_COL_RAIL_WIDTH,
      TWO_COL_RAIL_WIDTH,
      ONE_COL_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      COLLAPSED_RAIL_WIDTH,
      COLLAPSED_RAIL_WIDTH,
    ])

    // 2 pins: the same keys skip the 3-column stop the 3-pin lane had.
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(MAX_RAIL_WIDTH))
    const { result: twoPins } = renderHook(() =>
      useRailResize({ narrow: false, pinnedCount: 2 }),
    )
    act(() => {
      twoPins.current.handleResizeKeyDown({
        key: 'ArrowLeft',
        preventDefault: () => {},
      } as unknown as React.KeyboardEvent<HTMLDivElement>)
    })
    expect(twoPins.current.railWidth).toBe(TWO_COL_RAIL_WIDTH)

    // Unpinned, the same keys skip the column stops entirely.
    const { result: freeResult } = renderHook(() =>
      useRailResize({ narrow: false, pinnedCount: 0 }),
    )
    act(() => freeResult.current.setRailWidth(ULTRACOMPACT_RAIL_WIDTH))
    act(() => {
      freeResult.current.handleResizeKeyDown({
        key: 'ArrowRight',
        preventDefault: () => {},
      } as unknown as React.KeyboardEvent<HTMLDivElement>)
    })
    expect(freeResult.current.railWidth).toBe(MAX_RAIL_WIDTH)
  })

  it('the hook defaults to the pinned ladder, so a caller that omits the count keeps the guard', () => {
    // No `pinnedCount` at all → the default is 1, i.e. "the grid is on screen".
    // 1 pin's topmost column detent is 118, which sits inside the collapse zone
    // that `snapRailWidthToPoints` owns outright, so a drag above 118 free-tracks
    // — the fail-safe is "1 pin", the most conservative pinned state, not the
    // widest ladder. The guard is still armed for that state: assert the
    // threshold directly rather than inferring it from a drag.
    const { result } = dragTo(TARGET_WIDTH - START_WIDTH)
    expect(result.current.railWidth).toBe(TARGET_WIDTH)
    expect(railSnapPointsForPins(1)).toEqual([
      COLLAPSED_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      ONE_COL_RAIL_WIDTH,
      MAX_RAIL_WIDTH,
    ])
    expect(railSnapThresholdForPins(ONE_COL_RAIL_WIDTH, 1)).toBe(RAIL_DETENT_ALWAYS)
    // Not the empty-pool set — omitting the count must not read as "unpinned".
    expect(railSnapPointsForPins(1).length).toBeGreaterThan(
      railSnapPointsForPins(0).length,
    )
  })

  it('the rail feeds the hook its own pin count — no second source of truth', () => {
    // AgentSidebar owns the canonical `pins` state (the list RailSections
    // renders `.os-fav-grid` from); it is handed to the resize hook verbatim.
    expect(SIDEBAR_SRC).toMatch(/useRailResize\(\{[^}]*pinnedCount: pins\.length[^}]*\}\)/)
    expect(SIDEBAR_SRC).toMatch(/const \[pins, setPins\] = useState<PinnedAgent\[\]>/)
  })
})

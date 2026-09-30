/**
 * #1712 — expanding out of ultra-compact lands on `min(pins, 3)` columns.
 *
 * Two layers, deliberately:
 *  - the pure helper, which is the arithmetic the ticket asks for; and
 *  - the rendered Expand control, so the wiring cannot drift from the helper.
 *
 * #1683 is the regression this rides on: the drag ladder is pin-derived
 * (1..min(pins, 4)) and `railSnapStep` walks the *next* detent. Expand is a
 * different verb — it opens to the width that FITS the pins, which is why it
 * does not reuse the step.
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import {
  COLLAPSED_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  ONE_COL_RAIL_WIDTH,
  RAIL_EXPAND_MAX_COLUMNS,
  RAIL_SNAP_POINTS,
  RAIL_WIDTH_STORAGE_KEY,
  THREE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  railExpandWidthForPins,
  railSnapPointsForPins,
  railSnapStep,
  railWidthForColumns,
} from '../railResize'
import { useRailResize } from '../../components/sidebar/useRailResize'

const DESKTOP = 1920

function openRail(pinnedCount: number) {
  return renderHook(() => useRailResize({ narrow: false, pinnedCount }))
}

describe('#1712 expand snaps to min(pins, 3) pinned-grid columns', () => {
  beforeEach(() => {
    localStorage.clear()
    Object.defineProperty(window, 'innerWidth', { configurable: true, value: DESKTOP })
  })

  it('1 pin opens 1 column, 2 pins open 2, 3 pins open 3', () => {
    expect(railExpandWidthForPins(1, DESKTOP)).toBe(ONE_COL_RAIL_WIDTH)
    expect(railExpandWidthForPins(2, DESKTOP)).toBe(TWO_COL_RAIL_WIDTH)
    expect(railExpandWidthForPins(3, DESKTOP)).toBe(THREE_COL_RAIL_WIDTH)
  })

  it('4+ pins stay 3 columns wide — the 4th pin wraps, the pane does not grow', () => {
    for (const pins of [4, 5, 12]) {
      expect(railExpandWidthForPins(pins, DESKTOP)).toBe(THREE_COL_RAIL_WIDTH)
    }
  })

  it('never grows past 3 columns, and never lands on a 4-column drag detent', () => {
    expect(RAIL_EXPAND_MAX_COLUMNS).toBe(3)
    for (let pins = 1; pins <= 32; pins += 1) {
      const width = railExpandWidthForPins(pins, DESKTOP)
      expect(width).toBeLessThanOrEqual(THREE_COL_RAIL_WIDTH)
      // The 4-column stop (394) exists on the DRAG ladder (#1683) and must
      // stay unreachable from expand, or the owner's "never past 3" is a lie.
      expect(RAIL_SNAP_POINTS.filter((point) => point > THREE_COL_RAIL_WIDTH)).toContain(
        railWidthForColumns(4),
      )
      expect(width).not.toBe(railWidthForColumns(4))
    }
  })

  it('differs from the next-detent step for 2+ pins — that is the bug it fixes', () => {
    // The old behaviour walked one rung: 88 → 118 for every pin count.
    for (const pins of [2, 3, 4, 9]) {
      expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, pins)).toBe(
        ONE_COL_RAIL_WIDTH,
      )
      expect(railExpandWidthForPins(pins, DESKTOP)).not.toBe(ONE_COL_RAIL_WIDTH)
    }
  })

  it('0 pins earn no column detent, so expand keeps the viewport default (#1683)', () => {
    // The desktop default is 256 — deliberately NOT a detent, and NOT the
    // 420px ceiling: one click should not widen the pane five-fold.
    expect(railExpandWidthForPins(0, DESKTOP)).toBe(256)
    expect(railExpandWidthForPins(0, DESKTOP)).not.toBe(MAX_RAIL_WIDTH)
    // A laptop default is the 1-column detent, unchanged by #1712.
    expect(railExpandWidthForPins(0, 1280)).toBe(ONE_COL_RAIL_WIDTH)
  })

  it('every expanded width is a real stop on the drag ladder for that pin count', () => {
    for (const pins of [1, 2, 3, 4, 9]) {
      const width = railExpandWidthForPins(pins, DESKTOP)
      expect(railSnapPointsForPins(pins)).toContain(width)
    }
  })

  it('the rendered Expand control lands on min(pins, 3) columns from ultra-compact', () => {
    // Behavioural, through the real control: collapse to 0, expand, read the
    // width the hook published. The rail shell is not needed — the hook is the
    // control's only width authority.
    for (const [pins, expected] of [
      [1, ONE_COL_RAIL_WIDTH],
      [2, TWO_COL_RAIL_WIDTH],
      [3, THREE_COL_RAIL_WIDTH],
      [4, THREE_COL_RAIL_WIDTH],
    ] as const) {
      localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(COLLAPSED_RAIL_WIDTH))
      const { result } = openRail(pins)
      expect(result.current.isCollapsed).toBe(true)
      act(() => result.current.handlePillToggle())
      expect(result.current.railWidth).toBe(expected)
      // And it persists, so a reload does not snap back.
      expect(Number(localStorage.getItem(RAIL_WIDTH_STORAGE_KEY))).toBe(expected)
      act(() => result.current.concealSidebar())
      expect(result.current.railWidth).toBe(COLLAPSED_RAIL_WIDTH)
    }
  })

  it('a rail already at the 1-column detent expands to the pin-fit width too', () => {
    // Ultra-compact is the filed entry point, but the control is reachable at
    // any collapsed width, so both edges must agree.
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(ULTRACOMPACT_RAIL_WIDTH))
    const { result } = openRail(4)
    expect(result.current.isAvatarOnly).toBe(true)
    act(() => result.current.handlePillToggle())
    expect(result.current.railWidth).toBe(THREE_COL_RAIL_WIDTH)
  })

  it('leaves the drag and keyboard lanes untouched (#1683 guard)', () => {
    // The expand cap is scoped to the expand verb. The ladder still reaches 4
    // columns on a drag, or #1683's measured ceiling would be silently undone.
    expect(railSnapPointsForPins(4)).toContain(railWidthForColumns(4))
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 4)).toBe(railWidthForColumns(4))
  })
})

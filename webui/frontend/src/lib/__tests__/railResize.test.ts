import { describe, it, expect, beforeEach } from 'vitest'
import {
  clampRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  isFullyCollapsedWidth,
  snapRailWidth,
  snapRailWidthToPoints,
  RAIL_DETENT_ALWAYS,
  RAIL_SNAP_THRESHOLD,
  railColumnDetents,
  railSnapStep,
  railSnapPointsForPins,
  railSnapThresholdForPins,
  railWidthForColumns,
  RAIL_SNAP_POINTS,
  RAIL_UNPINNED_SNAP_POINTS,
  MAX_PINNED_COLUMNS,
  ONE_COL_RAIL_WIDTH,
  TWO_COL_RAIL_WIDTH,
  THREE_COL_RAIL_WIDTH,
  FOUR_COL_RAIL_WIDTH,
  ULTRACOMPACT_RAIL_WIDTH,
  defaultRailWidth,
  LAPTOP_MAX_WIDTH,
  MIN_RAIL_WIDTH,
  MAX_RAIL_WIDTH,
  DEFAULT_RAIL_WIDTH,
  AVATAR_ONLY_THRESHOLD,
  COLLAPSED_RAIL_WIDTH,
  RAIL_WIDTH_STORAGE_KEY,
} from '../railResize'

describe('railResize (REQ-116)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('clamps rail width within min and max boundaries', () => {
    expect(clampRailWidth(50)).toBe(MIN_RAIL_WIDTH)
    expect(clampRailWidth(100)).toBe(100)
    expect(clampRailWidth(500)).toBe(MAX_RAIL_WIDTH)
  })

  it('clamps rail width to viewport ceiling when specified', () => {
    // 45% of 600px is 270px, which is below MAX_RAIL_WIDTH (420px)
    expect(clampRailWidth(350, 600)).toBe(270)
  })

  it('loads default width when nothing is stored or value is invalid', () => {
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)

    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, 'invalid')
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
  })

  it('persists and retrieves valid width from localStorage', () => {
    saveRailWidth(180)
    expect(localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBe('180')
    expect(loadRailWidth()).toBe(180)
  })

  it('identifies avatar-only width threshold', () => {
    expect(isAvatarOnlyWidth(MIN_RAIL_WIDTH)).toBe(true)
    expect(isAvatarOnlyWidth(AVATAR_ONLY_THRESHOLD)).toBe(true)
    expect(isAvatarOnlyWidth(AVATAR_ONLY_THRESHOLD + 1)).toBe(false)
    expect(isAvatarOnlyWidth(256)).toBe(false)
  })
})

// #765 — full edge collapse: the rail can now be dragged shut to 0px
// (divider-only state), with snap physics avatar-width → 0px.
describe('#765 edge collapse (0px divider-only state)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('COLLAPSED_RAIL_WIDTH is 0 and isAvatarOnlyWidth treats it as collapsed', () => {
    expect(COLLAPSED_RAIL_WIDTH).toBe(0)
    expect(isAvatarOnlyWidth(COLLAPSED_RAIL_WIDTH)).toBe(true)
  })

  it('isFullyCollapsedWidth is true only at exactly 0px', () => {
    expect(isFullyCollapsedWidth(0)).toBe(true)
    expect(isFullyCollapsedWidth(1)).toBe(false)
    expect(isFullyCollapsedWidth(MIN_RAIL_WIDTH)).toBe(false)
  })

  it('snapRailWidth snaps below the collapse threshold to 0px', () => {
    expect(snapRailWidth(24)).toBe(COLLAPSED_RAIL_WIDTH)
    expect(snapRailWidth(0)).toBe(COLLAPSED_RAIL_WIDTH)
    // The collapse threshold (52) is the frontier between collapsed and the
    // ultra-compact (avatar-only) detent; at/above it the rail is 88px.
    expect(snapRailWidth(90)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(snapRailWidth(68)).toBe(ULTRACOMPACT_RAIL_WIDTH)
  })

  it('dragging open from 0px snaps to the nearest collapse-zone detent', () => {
    expect(snapRailWidth(40)).toBe(COLLAPSED_RAIL_WIDTH)
    expect(snapRailWidth(60)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(snapRailWidth(88)).toBe(ULTRACOMPACT_RAIL_WIDTH)
  })

  it('loadRailWidth persists and restores a collapsed 0px rail', () => {
    saveRailWidth(COLLAPSED_RAIL_WIDTH)
    expect(localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)).toBe('0')
    expect(loadRailWidth()).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('loadRailWidth still clamps legacy garbage to the default', () => {
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, 'invalid')
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, '-5')
    expect(loadRailWidth()).toBe(COLLAPSED_RAIL_WIDTH)
  })
})

describe('#1083 laptop viewport default rail width', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaultRailWidth returns the one-column laptop rail on laptop viewports (<= 1440px) (#1098, one-column default)', () => {
    // #1083 set the laptop default to MIN_RAIL_WIDTH (68), below
    // AVATAR_ONLY_THRESHOLD (88): avatar-only CSS hides section headers, so
    // the #1094 Subagents section vanished on laptops. #1098 floored it at
    // threshold+1 (97px), but 97 is narrower than the rail's own chrome — the
    // horizontal search row and the "Routines" footer label overflow it
    // The laptop default is now the 1-column pinned-grid detent:
    // still compact, above the avatar line, and wide enough to seat the
    // search controls and footer labels.
    expect(LAPTOP_MAX_WIDTH).toBe(1440)
    for (const vw of [1440, 1280, 1024, 800]) {
      expect(defaultRailWidth(vw)).toBe(ONE_COL_RAIL_WIDTH)
    }
    // strictly above the avatar-only threshold: headers and labels stay visible
    expect(defaultRailWidth(1280)).toBeGreaterThan(AVATAR_ONLY_THRESHOLD)
    // and exactly the narrowest rail whose horizontal chrome fits
    expect(ONE_COL_RAIL_WIDTH).toBe(railWidthForColumns(1))
  })

  it('defaultRailWidth returns DEFAULT_RAIL_WIDTH on desktop viewports (> 1440px)', () => {
    expect(defaultRailWidth(1441)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(1920)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(2560)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(undefined)).toBe(DEFAULT_RAIL_WIDTH)
  })

  it('loadRailWidth returns the one-column laptop rail when nothing is stored (#1098, one-column default)', () => {
    expect(loadRailWidth(1440)).toBe(ONE_COL_RAIL_WIDTH)
    expect(loadRailWidth(1280)).toBe(ONE_COL_RAIL_WIDTH)
  })

  it('loadRailWidth lifts a stale sub-one-column width out of the overflow dead zone', () => {
    // The snap physics never settles between the avatar-only detent (96) and
    // the one-column detent (118); only the old 97px laptop default landed
    // there. It must not be restored, or the footer labels bleed past the
    // rail edge again.
    saveRailWidth(97)
    expect(loadRailWidth(1280)).toBe(ONE_COL_RAIL_WIDTH)
    expect(loadRailWidth(1920)).toBe(ONE_COL_RAIL_WIDTH)
    saveRailWidth(AVATAR_ONLY_THRESHOLD)
    expect(loadRailWidth(1280)).toBe(AVATAR_ONLY_THRESHOLD)
    saveRailWidth(ONE_COL_RAIL_WIDTH)
    expect(loadRailWidth(1280)).toBe(ONE_COL_RAIL_WIDTH)
  })

  it('loadRailWidth returns DEFAULT_RAIL_WIDTH on desktop viewports when nothing is stored', () => {
    expect(loadRailWidth(1920)).toBe(DEFAULT_RAIL_WIDTH)
    expect(loadRailWidth()).toBe(DEFAULT_RAIL_WIDTH)
  })

  it('loadRailWidth respects valid stored width even on laptop viewports', () => {
    saveRailWidth(200)
    expect(loadRailWidth(1280)).toBe(200)

    saveRailWidth(COLLAPSED_RAIL_WIDTH)
    expect(loadRailWidth(1280)).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('loadRailWidth falls back to defaultRailWidth when stored value is invalid (#1098 laptop floor)', () => {
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, 'invalid')
    expect(loadRailWidth(1280)).toBe(ONE_COL_RAIL_WIDTH)
    expect(loadRailWidth(1920)).toBe(DEFAULT_RAIL_WIDTH)
  })
})

// #1289 — pinned-grid column snap points.
describe('#1289 rail snap points (pinned-grid columns)', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('derives column widths from the grid geometry (5.25rem track, 0.5rem gap)', () => {
    // gridContent(N) = N·84 + (N-1)·8; rail = content + 24 margin + 10 chrome.
    expect(railWidthForColumns(1)).toBe(84 + 24 + 10)
    expect(railWidthForColumns(2)).toBe(176 + 24 + 10)
    expect(railWidthForColumns(3)).toBe(268 + 24 + 10)
    expect(ONE_COL_RAIL_WIDTH).toBe(118)
    expect(TWO_COL_RAIL_WIDTH).toBe(210)
    expect(THREE_COL_RAIL_WIDTH).toBe(302)
  })

  it('exposes the ordered, strictly ascending detent list', () => {
    // #1651: every detent is a real geometric stop — collapsed, avatar-only,
    // a whole pinned-grid column count, or max. The desktop default width
    // (256) is an initial/persisted value, NOT a detent.
    //
    // #1683: FOUR columns, not three. `railWidthForColumns(4)` = 394 ≤
    // MAX_RAIL_WIDTH (420), so a 4th column always fit — the old ladder just
    // had no detent for it. The full ladder is the superset every pin count
    // draws from; a given rail uses `railSnapPointsForPins(pinnedCount)`.
    expect(RAIL_SNAP_POINTS).toEqual([
      COLLAPSED_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      ONE_COL_RAIL_WIDTH,
      TWO_COL_RAIL_WIDTH,
      THREE_COL_RAIL_WIDTH,
      FOUR_COL_RAIL_WIDTH,
      MAX_RAIL_WIDTH,
    ])
    expect(RAIL_SNAP_POINTS).not.toContain(DEFAULT_RAIL_WIDTH)
    for (let i = 1; i < RAIL_SNAP_POINTS.length; i += 1) {
      expect(RAIL_SNAP_POINTS[i]).toBeGreaterThan(RAIL_SNAP_POINTS[i - 1])
    }
  })

  it('mirrors the in-flow detents for a right-docked rail (#816)', () => {
    // right rail: collapsed first, then the widest in-flow detent.
    // #1683: the pin count must be threaded here too — with the default (1 pin)
    // the 2/3-column stops are not in the set at all.
    expect(snapRailWidthToPoints(TWO_COL_RAIL_WIDTH + 5, 'right', undefined, 3)).toBe(
      TWO_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(THREE_COL_RAIL_WIDTH + 5, 'right', undefined, 3)).toBe(
      THREE_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(10, 'right')).toBe(COLLAPSED_RAIL_WIDTH)
  })

  it('railSnapStep walks detent-to-detent for keyboard resize', () => {
    // The lane is strictly ascending by pixel value. #1683: which lane depends
    // on the pin count, so this walks the 3-pin lane (0, 88, 118, 210, 302,
    // 420) — arrows step neighbours (#1651: no 256 stop).
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(TWO_COL_RAIL_WIDTH)
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(THREE_COL_RAIL_WIDTH)
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(MAX_RAIL_WIDTH)
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, -1, undefined, 3)).toBe(ONE_COL_RAIL_WIDTH)
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, -1, undefined, 3)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, -1, undefined, 3)).toBe(COLLAPSED_RAIL_WIDTH)
    // Ends are floors/ceilings.
    expect(railSnapStep(COLLAPSED_RAIL_WIDTH, -1, undefined, 3)).toBe(COLLAPSED_RAIL_WIDTH)
    expect(railSnapStep(MAX_RAIL_WIDTH, 1, undefined, 3)).toBe(MAX_RAIL_WIDTH)
  })

  it('railSnapStep mirrors direction for a right-docked rail (#816)', () => {
    // Right rail: a leftward (negative) pointer/arrow grows the rail, which
    // in mirrored pixel order means stepping to the next-lower value in the
    // lane. -1 on 210 → 118 (the adjacent step).
    expect(railSnapStep(TWO_COL_RAIL_WIDTH, -1, 'right', 3)).toBe(ONE_COL_RAIL_WIDTH)
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, -1, 'right', 3)).toBe(TWO_COL_RAIL_WIDTH)
  })

  it('snapRailWidth (legacy helper) keeps the detent contract', () => {
    expect(snapRailWidth(TWO_COL_RAIL_WIDTH + 6, undefined, 3)).toBe(TWO_COL_RAIL_WIDTH)
    expect(snapRailWidth(ONE_COL_RAIL_WIDTH - 30)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(snapRailWidth(10)).toBe(COLLAPSED_RAIL_WIDTH)
    // 160 free-tracks at the legacy 14px slop; only 2 detents are in the gap
    // between 118 and 210, and neither is within 14px of it.
    expect(snapRailWidth(160, undefined, 3)).toBe(160)
  })

  it('#1262 RAIL_DETENT_ALWAYS quantizes a free-tracking drag onto detents', () => {
    // Two widths inside the same 1-col gap resolve to the SAME detent, so the
    // pinned grid does not drift while dragging between them.
    expect(snapRailWidthToPoints(130, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(
      ONE_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(160, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(
      ONE_COL_RAIL_WIDTH,
    )
    // Past the midpoint it steps to the next detent (a column-count reflow).
    expect(snapRailWidthToPoints(200, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(
      TWO_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(400, undefined, RAIL_DETENT_ALWAYS, 3)).toBe(
      MAX_RAIL_WIDTH,
    )
    // The default threshold still free-tracks between detents (contract kept).
    expect(snapRailWidthToPoints(160, undefined, RAIL_SNAP_THRESHOLD, 3)).toBe(160)
  })
})

/**
 * #1683 — the detent set is a property of the pinned grid, not of the rail.
 *
 * `RAIL_SNAP_POINTS` reads "the width that exactly fits N pinned columns". With
 * nothing pinned there is no grid, so those stops are invisible and the drag
 * free-tracks. Collapsed (0) and ultra-compact (88) mean something in every
 * state and stay.
 */
describe('#1683 the detent set follows the pinned grid', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  const CASES: ReadonlyArray<{ pins: number; label: string; detents: readonly number[] }> = [
    {
      pins: 0,
      label: 'no pins',
      detents: [COLLAPSED_RAIL_WIDTH, ULTRACOMPACT_RAIL_WIDTH, MAX_RAIL_WIDTH],
    },
    // #1683: the column stops are earned per pin count, so 1 and 3 pins no
    // longer share a set. Past MAX_PINNED_COLUMNS (4) the ladder is full.
    { pins: 1, label: 'one pin', detents: [0, 88, ONE_COL_RAIL_WIDTH, MAX_RAIL_WIDTH] },
    {
      pins: 3,
      label: 'three pins',
      detents: [0, 88, ONE_COL_RAIL_WIDTH, TWO_COL_RAIL_WIDTH, THREE_COL_RAIL_WIDTH, MAX_RAIL_WIDTH],
    },
    { pins: 12, label: 'a full pool', detents: RAIL_SNAP_POINTS },
  ]

  it.each(CASES)('$label → $detents', ({ pins, detents }) => {
    expect(railSnapPointsForPins(pins)).toEqual(detents)
    expect(railSnapPointsForPins(pins)).toStrictEqual([...detents])
  })

  it('the set grows with the pin count, one column detent at a time', () => {
    // #1683: the operator's rule made arithmetic. Each additional pin adds
    // exactly the detent that seats it, and nothing else changes.
    for (let pins = 1; pins <= MAX_PINNED_COLUMNS; pins += 1) {
      expect(railColumnDetents(pins)).toEqual(
        [1, 2, 3, 4].slice(0, pins).map(railWidthForColumns),
      )
      expect(railSnapPointsForPins(pins)).toEqual([
        COLLAPSED_RAIL_WIDTH,
        ULTRACOMPACT_RAIL_WIDTH,
        ...railColumnDetents(pins),
        MAX_RAIL_WIDTH,
      ])
    }
  })

  it('pinned rails earn exactly their column detents; unpinned settles on {0, 88, 420}', () => {
    // #1683: 1 pin earns the 1-column detent and no more.
    expect(railSnapPointsForPins(1)).toEqual([
      COLLAPSED_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      ONE_COL_RAIL_WIDTH,
      MAX_RAIL_WIDTH,
    ])
    // 4+ pins earn the whole ladder, including the 4th column (394).
    expect(railSnapPointsForPins(4)).toEqual([...RAIL_SNAP_POINTS])
    expect(FOUR_COL_RAIL_WIDTH).toBeLessThanOrEqual(MAX_RAIL_WIDTH)
    expect(MAX_PINNED_COLUMNS).toBe(4)
    expect(railSnapPointsForPins(0)).toEqual([
      COLLAPSED_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      MAX_RAIL_WIDTH,
    ])
    // The column stops must be GONE when unpinned, not merely reordered.
    for (const gone of railColumnDetents(MAX_PINNED_COLUMNS)) {
      expect(RAIL_UNPINNED_SNAP_POINTS).not.toContain(gone)
    }
  })

  it('unpinned: a release beside a former column stop stays where it was let go', () => {
    for (const width of [125, 200, 250, 290, 395]) {
      expect(snapRailWidthToPoints(width, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(width)
    }
    // …and the same widths, with enough pins to earn those detents, snap to
    // the ladder. #1683: 200 needs ≥2 pins (the 2-col detent) and 290 needs ≥3.
    expect(snapRailWidthToPoints(200, undefined, RAIL_SNAP_THRESHOLD, 2)).toBe(
      TWO_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(290, undefined, RAIL_SNAP_THRESHOLD, 3)).toBe(
      THREE_COL_RAIL_WIDTH,
    )
  })

  it('unpinned: collapsed, ultra-compact and max still settle', () => {
    // Those three stops are meaningful in every state: a divider-only pane,
    // the one-avatar-per-row tier, and the rail's ceiling.
    expect(railSnapPointsForPins(0)).toEqual(RAIL_UNPINNED_SNAP_POINTS)
    expect(snapRailWidthToPoints(40, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      COLLAPSED_RAIL_WIDTH,
    )
    // 60 is past the collapse threshold (52) — the divider-only state and the
    // ultra-compact tier split it, in every pin state.
    expect(snapRailWidthToPoints(60, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      ULTRACOMPACT_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(100, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      ULTRACOMPACT_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(118, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      ULTRACOMPACT_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(410, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      MAX_RAIL_WIDTH,
    )
    // The ceiling holds even for a drag that overshoots it.
    expect(snapRailWidthToPoints(900, undefined, RAIL_SNAP_THRESHOLD, 0)).toBe(
      MAX_RAIL_WIDTH,
    )
  })

  it('#1262 RAIL_DETENT_ALWAYS is still the snap threshold whenever pins exist', () => {
    // The wobble guard is conditional on the grid, never deleted: with the grid
    // on screen every drag frame is quantised onto the nearest detent.
    //
    // #1683: quantisation now lands on the nearest detent the PIN COUNT earns,
    // not on a fixed ladder. 1 pin has no 2-column detent, so 200 resolves to
    // the 1-column width it does have. That is the rule, not a weakening: the
    // guard is still Infinity-wide, it just has fewer targets to aim at.
    for (const pins of [1, 2, 5]) {
      expect(snapRailWidthToPoints(130, undefined, RAIL_DETENT_ALWAYS, pins)).toBe(
        ONE_COL_RAIL_WIDTH,
      )
    }
    // The ceiling wins only while the 4-column detent is not the nearer one.
    // #1683: with ≥4 pins, 400 is closer to 394 than to 420 — and 394 is a
    // detent only because four columns genuinely fit inside the rail.
    for (const pins of [1, 2, 3]) {
      expect(snapRailWidthToPoints(400, undefined, RAIL_DETENT_ALWAYS, pins)).toBe(
        MAX_RAIL_WIDTH,
      )
    }
    for (const pins of [4, 5]) {
      expect(snapRailWidthToPoints(400, undefined, RAIL_DETENT_ALWAYS, pins)).toBe(
        FOUR_COL_RAIL_WIDTH,
      )
    }
    // Every width the guard produces is a detent this pin count earned.
    for (const pins of [1, 2, 3, 4, 5, 12]) {
      for (const width of [130, 160, 200, 250, 290, 340, 400]) {
        expect(railSnapPointsForPins(pins)).toContain(
          snapRailWidthToPoints(width, undefined, RAIL_DETENT_ALWAYS, pins),
        )
      }
    }
    // ≥2 pins earn the 2-column detent, so 200 resolves to it.
    expect(snapRailWidthToPoints(200, undefined, RAIL_DETENT_ALWAYS, 2)).toBe(
      TWO_COL_RAIL_WIDTH,
    )
    expect(snapRailWidthToPoints(160, undefined, RAIL_DETENT_ALWAYS, 2)).toBe(
      ONE_COL_RAIL_WIDTH,
    )
  })

  it('defaults to the pinned ladder so a caller that omits the count cannot lose the guard', () => {
    // #1683: the default is 1 pin, so the default set is the 1-PIN set — the
    // narrowest pinned one, not the full ladder and not the empty-pool one.
    expect(railSnapPointsForPins(1)).toEqual([
      COLLAPSED_RAIL_WIDTH,
      ULTRACOMPACT_RAIL_WIDTH,
      ONE_COL_RAIL_WIDTH,
      MAX_RAIL_WIDTH,
    ])
    // The guard is armed up to the 1-column detent — but `snapRailWidthToPoints`
    // short-circuits the whole collapse zone (width <= 118 → 0 or 88) before any
    // threshold is consulted, so for 1 pin the armed region is only ever reached
    // via the collapse branch. Above 118 it free-tracks, which is correct: 1
    // pin earns no column detent wider than 118, so there is nothing to snap to.
    // (See RailDetentByPinCount1683.test.ts for the 2+-pin case, where the rigid
    // region is a real, reachable band.)
    expect(railSnapThresholdForPins(118)).toBe(RAIL_DETENT_ALWAYS)
    expect(railSnapThresholdForPins(119)).toBe(RAIL_SNAP_THRESHOLD)
    expect(snapRailWidthToPoints(160)).toBe(160)
    expect(snapRailWidthToPoints(200)).toBe(200)
    // The default is still "pinned", not "empty": the empty-pool set is smaller.
    expect(railSnapPointsForPins(0).length).toBeLessThan(railSnapPointsForPins(1).length)
  })

  it('keyboard steps walk the pin-dependent lane in both states', () => {
    // Pinned: the lane the pins earn. #1683: 3 pins → 88, 118, 210, 302, 420.
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, 3)).toBe(
      ONE_COL_RAIL_WIDTH,
    )
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(TWO_COL_RAIL_WIDTH)
    expect(railSnapStep(THREE_COL_RAIL_WIDTH, 1, undefined, 3)).toBe(MAX_RAIL_WIDTH)
    // 1 pin: 88 → 118 → 420 (the 1-col detent is the topmost one it earns).
    expect(railSnapStep(ONE_COL_RAIL_WIDTH, 1, undefined, 1)).toBe(MAX_RAIL_WIDTH)
    // Unpinned: 88 steps straight to the ceiling — no invisible stops.
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, 1, undefined, 0)).toBe(MAX_RAIL_WIDTH)
    expect(railSnapStep(MAX_RAIL_WIDTH, -1, undefined, 0)).toBe(ULTRACOMPACT_RAIL_WIDTH)
    expect(railSnapStep(ULTRACOMPACT_RAIL_WIDTH, -1, undefined, 0)).toBe(
      COLLAPSED_RAIL_WIDTH,
    )
  })

  it('the legacy snapRailWidth helper takes the same pin count', () => {
    expect(snapRailWidth(160, undefined, 0)).toBe(160)
    // #1683: 200 is within the 14px slop of the 2-col detent, which 2 pins earn
    // and 1 pin does not.
    expect(snapRailWidth(200, undefined, 2)).toBe(TWO_COL_RAIL_WIDTH)
    expect(snapRailWidth(200, undefined, 1)).toBe(200)
    expect(snapRailWidth(100, undefined, 0)).toBe(ULTRACOMPACT_RAIL_WIDTH)
  })
})

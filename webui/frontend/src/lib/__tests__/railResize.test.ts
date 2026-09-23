import { describe, it, expect, beforeEach } from 'vitest'
import {
  clampRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  isFullyCollapsedWidth,
  snapRailWidth,
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
    // avatar snap point still holds above the collapse threshold
    expect(snapRailWidth(68)).toBe(MIN_RAIL_WIDTH)
    expect(snapRailWidth(90)).toBe(MIN_RAIL_WIDTH)
  })

  it('dragging open from 0px snaps first to avatar width', () => {
    expect(snapRailWidth(40)).toBe(COLLAPSED_RAIL_WIDTH)
    expect(snapRailWidth(60)).toBe(MIN_RAIL_WIDTH)
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

  it('defaultRailWidth returns the compact laptop floor on laptop viewports (<= 1440px) (#1098)', () => {
    // #1083 set the laptop default to MIN_RAIL_WIDTH (68), but that is below
    // AVATAR_ONLY_THRESHOLD (96): avatar-only CSS hides section headers, so
    // the #1094 Subagents section was unreachable on laptops. The default is
    // now floored at threshold+1 — still the compact rail, headers intact.
    const LAPTOP_FLOOR = AVATAR_ONLY_THRESHOLD + 1
    expect(LAPTOP_MAX_WIDTH).toBe(1440)
    expect(defaultRailWidth(1440)).toBe(LAPTOP_FLOOR)
    expect(defaultRailWidth(1280)).toBe(LAPTOP_FLOOR)
    expect(defaultRailWidth(1024)).toBe(LAPTOP_FLOOR)
    expect(defaultRailWidth(800)).toBe(LAPTOP_FLOOR)
    // strictly above the avatar-only threshold: headers stay visible
    expect(defaultRailWidth(1280)).toBeGreaterThan(AVATAR_ONLY_THRESHOLD)
  })

  it('defaultRailWidth returns DEFAULT_RAIL_WIDTH on desktop viewports (> 1440px)', () => {
    expect(defaultRailWidth(1441)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(1920)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(2560)).toBe(DEFAULT_RAIL_WIDTH)
    expect(defaultRailWidth(undefined)).toBe(DEFAULT_RAIL_WIDTH)
  })

  it('loadRailWidth returns the laptop floor when nothing is stored (#1098)', () => {
    expect(loadRailWidth(1440)).toBe(AVATAR_ONLY_THRESHOLD + 1)
    expect(loadRailWidth(1280)).toBe(AVATAR_ONLY_THRESHOLD + 1)
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
    expect(loadRailWidth(1280)).toBe(AVATAR_ONLY_THRESHOLD + 1)
    expect(loadRailWidth(1920)).toBe(DEFAULT_RAIL_WIDTH)
  })
})

import { describe, it, expect, beforeEach } from 'vitest'
import {
  clampRailWidth,
  loadRailWidth,
  saveRailWidth,
  isAvatarOnlyWidth,
  isFullyCollapsedWidth,
  snapRailWidth,
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

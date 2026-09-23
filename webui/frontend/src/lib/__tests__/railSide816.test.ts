/**
 * #816 — the rail-side preference contract.
 *
 * Pure module: load/save round-trip through localStorage, unknown/absent
 * values stay 'left', the CustomEvent fires with the new side, and the
 * resize math mirrors on the right (delta sign flips).
 */
import { describe, expect, it, beforeEach } from 'vitest'
import {
  loadRailSide,
  saveRailSide,
  sideAwareWidthDelta,
  RAIL_SIDE_EVENT,
  RAIL_SIDE_STORAGE_KEY,
} from '../railSide'

describe('#816 rail side preference', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('defaults to left', () => {
    expect(loadRailSide()).toBe('left')
  })

  it('round-trips right through localStorage', () => {
    saveRailSide('right')
    expect(localStorage.getItem(RAIL_SIDE_STORAGE_KEY)).toBe('right')
    expect(loadRailSide()).toBe('right')
  })

  it('falls back to left on garbage values', () => {
    localStorage.setItem(RAIL_SIDE_STORAGE_KEY, 'diagonal')
    expect(loadRailSide()).toBe('left')
  })

  it('announces changes on a CustomEvent', () => {
    const seen: string[] = []
    const handler = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener(RAIL_SIDE_EVENT, handler)
    saveRailSide('right')
    window.removeEventListener(RAIL_SIDE_EVENT, handler)
    expect(seen).toEqual(['right'])
  })

  it('mirrors the resize math on the right side', () => {
    // Left (historical): grow intent = +12; right rail: same intent = -12.
    expect(sideAwareWidthDelta('left', true)).toBe(12)
    expect(sideAwareWidthDelta('left', false)).toBe(-12)
    expect(sideAwareWidthDelta('right', true)).toBe(-12)
    expect(sideAwareWidthDelta('right', false)).toBe(12)
  })
})

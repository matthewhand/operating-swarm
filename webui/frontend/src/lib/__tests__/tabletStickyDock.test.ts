/**
 * #1073 — tablet sticky dock preference.
 *
 * Contracts:
 * - Persisted under `os.tabletStickyDock`; load reflects the stored flag.
 * - save() dispatches the change event with the new value; subscribers fire.
 * - storage events from other tabs update subscribers too.
 * - Corrupt/absent storage never throws (private-mode safe).
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  TABLET_STICKY_DOCK_EVENT,
  TABLET_STICKY_DOCK_STORAGE_KEY,
  loadTabletStickyDock,
  saveTabletStickyDock,
  subscribeTabletStickyDock,
} from '../tabletStickyDock'

describe('#1073 tablet sticky dock persistence', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('defaults to undocked when nothing is stored', () => {
    expect(loadTabletStickyDock()).toBe(false)
  })

  it('round-trips a saved docked preference', () => {
    saveTabletStickyDock(true)
    expect(loadTabletStickyDock()).toBe(true)
    saveTabletStickyDock(false)
    expect(loadTabletStickyDock()).toBe(false)
    expect(window.localStorage.getItem(TABLET_STICKY_DOCK_STORAGE_KEY)).toBe('0')
  })

  it('notifies subscribers on save with the new value', () => {
    const seen: boolean[] = []
    const stop = subscribeTabletStickyDock((docked) => seen.push(docked))
    saveTabletStickyDock(true)
    stop()
    expect(seen).toEqual([true])
    expect(TABLET_STICKY_DOCK_EVENT).toBe('os-tablet-sticky-dock-changed')
  })

  it('stops notifying after unsubscribe', () => {
    const seen: boolean[] = []
    const stop = subscribeTabletStickyDock((docked) => seen.push(docked))
    stop()
    saveTabletStickyDock(true)
    expect(seen).toEqual([])
  })

  it('survives storage failures (private mode)', () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    expect(() => saveTabletStickyDock(true)).not.toThrow()
    setItem.mockRestore()
  })
})

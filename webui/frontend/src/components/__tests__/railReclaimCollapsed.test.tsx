/**
 * #1289 — collapsed sidepane must reclaim its space.
 *
 * The rail is in-flow chrome on desktop (`lg:relative` in AgentSidebar plus
 * the in-flow flex row in App.tsx), so a 0px width lets `<main>` stretch.
 * The hook mirrors the reserved width onto the shell root as
 * `--os-rail-width` (0px when collapsed) so any positioned chrome follows the
 * same 0px instead of leaving a dead gap.
 */
import { describe, expect, it } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
  COLLAPSED_RAIL_WIDTH,
  DEFAULT_RAIL_WIDTH,
  ONE_COL_RAIL_WIDTH,
} from '../../lib/railResize'
import { useRailResize } from '../sidebar/useRailResize'

describe('#1289 collapsed rail reclaims content space', () => {
  it('mirrors the live width as --os-rail-width on the shell root', () => {
    localStorage.clear()
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.setRailWidth(ONE_COL_RAIL_WIDTH))
    expect(
      document.documentElement.style.getPropertyValue('--os-rail-width'),
    ).toBe(`${ONE_COL_RAIL_WIDTH}px`)
  })

  it('drops the reserved width to 0px when collapsed (no dead gap)', () => {
    localStorage.clear()
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => result.current.setRailWidth(DEFAULT_RAIL_WIDTH))
    expect(
      document.documentElement.style.getPropertyValue('--os-rail-width'),
    ).toBe(`${DEFAULT_RAIL_WIDTH}px`)

    act(() => result.current.concealSidebar())
    expect(result.current.isCollapsed).toBe(true)
    expect(
      document.documentElement.style.getPropertyValue('--os-rail-width'),
    ).toBe(`${COLLAPSED_RAIL_WIDTH}px`)
  })

  it('removes the reserved width entirely on narrow (mobile drawer) viewports', () => {
    localStorage.clear()
    renderHook(() => useRailResize({ narrow: true }))
    expect(
      document.documentElement.style.getPropertyValue('--os-rail-width'),
    ).toBe('')
  })

  it('follows keyboard resize so the reserved space never lags a snap point', () => {
    localStorage.clear()
    const { result } = renderHook(() => useRailResize({ narrow: false }))
    act(() => {
      result.current.handleResizeKeyDown({
        key: 'ArrowLeft',
        preventDefault: () => {},
      } as unknown as React.KeyboardEvent<HTMLDivElement>)
    })
    expect(
      document.documentElement.style.getPropertyValue('--os-rail-width'),
    ).toBe(`${result.current.railWidth}px`)
  })
})

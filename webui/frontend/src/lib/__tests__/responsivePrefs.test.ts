/**
 * #833 — viewport-tiered responsive preferences.
 *
 * Contracts:
 * - Tier mapping: mobile < 640px, tablet 640–1023px, desktop ≥ 1024px.
 * - Touch-aware defaults: action rows always visible on mobile/tablet,
 *   hover-reveal on desktop; sidepane placement defaults to `left` on ALL
 *   tiers (right is opt-in only).
 * - The tier updates live on resize / orientation change.
 */
import { renderHook, act } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

// #1098: innerWidth is a getter-only accessor in this jsdom/Node pair; bare
// assignment throws once anything redefines it. Always defineProperty.
function setInnerWidth(px: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: px })
}
import {
  DEFAULT_ACTIONS_ALWAYS_VISIBLE,
  DEFAULT_SIDEPANE_PLACEMENT,
  MOBILE_MAX_PX,
  TABLET_MAX_PX,
  useResponsivePref,
  useViewportTier,
  viewportDataAttribute,
  viewportTierFromWidth,
} from '../responsivePrefs'

describe('#833 — viewport tier detection', () => {
  it('maps widths to the three standard tiers', () => {
    expect(viewportTierFromWidth(375)).toBe('mobile')
    expect(viewportTierFromWidth(MOBILE_MAX_PX)).toBe('mobile')
    expect(viewportTierFromWidth(640)).toBe('tablet')
    expect(viewportTierFromWidth(TABLET_MAX_PX)).toBe('tablet')
    expect(viewportTierFromWidth(1024)).toBe('desktop')
    expect(viewportTierFromWidth(1920)).toBe('desktop')
  })

  it('updates live on resize / orientation change', () => {
    const { result } = renderHook(() => useViewportTier())
    expect(result.current).toBe('desktop') // jsdom default 1024
    act(() => {
      setInnerWidth(390)
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current).toBe('mobile')
    act(() => {
      setInnerWidth(768)
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current).toBe('tablet')
    act(() => {
      setInnerWidth(1440)
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current).toBe('desktop')
  })

  it('evaluates a ResponsivePref for the active tier', () => {
    const { result } = renderHook(() =>
      useResponsivePref(DEFAULT_ACTIONS_ALWAYS_VISIBLE),
    )
    expect(result.current).toBe(false) // desktop default: hover-reveal
    act(() => {
      setInnerWidth(390)
      window.dispatchEvent(new Event('resize'))
    })
    expect(result.current).toBe(true) // mobile: always visible
  })

  it('ships touch-aware defaults', () => {
    expect(DEFAULT_ACTIONS_ALWAYS_VISIBLE).toEqual({
      mobile: true,
      tablet: true,
      desktop: false,
    })
    // Sidepane is left on every tier — right placement is opt-in only.
    expect(DEFAULT_SIDEPANE_PLACEMENT).toEqual({
      mobile: 'left',
      tablet: 'left',
      desktop: 'left',
    })
  })

  it('exposes the shell data attribute contract', () => {
    expect(viewportDataAttribute('tablet')).toBe('data-viewport="tablet"')
  })

  afterEach(() => {
    setInnerWidth(1024)
    vi.restoreAllMocks()
  })
})

describe('#833 — persisted per-tier overrides', () => {
  afterEach(() => {
    localStorage.removeItem('os.actionsAlwaysVisible')
  })

  it('falls back to shipped defaults when nothing is stored', async () => {
    const { loadActionsAlwaysVisible, saveActionsAlwaysVisible } = await import('../responsivePrefs')
    expect(loadActionsAlwaysVisible()).toEqual({
      mobile: true,
      tablet: true,
      desktop: false,
    })
    // Touch-aware default flips on the desktop tier…
    const next = saveActionsAlwaysVisible({
      mobile: true,
      tablet: false,
      desktop: true,
    })
    expect(next).toEqual({ mobile: true, tablet: false, desktop: true })
    expect(loadActionsAlwaysVisible()).toEqual({ mobile: true, tablet: false, desktop: true })
  })

  it('notifies listeners on save', async () => {
    const { saveActionsAlwaysVisible, ACTIONS_PREFS_CHANGED_EVENT } = await import('../responsivePrefs')
    const listener = vi.fn()
    window.addEventListener(ACTIONS_PREFS_CHANGED_EVENT, listener)
    saveActionsAlwaysVisible({ mobile: true, tablet: true, desktop: true })
    expect(listener).toHaveBeenCalled()
    window.removeEventListener(ACTIONS_PREFS_CHANGED_EVENT, listener)
  })
})

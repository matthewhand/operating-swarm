/**
 * #833 — viewport-tiered responsive preferences (Mobile / Tablet / Desktop).
 *
 * Three standard tiers keyed off window width (matching Tailwind's `sm` and
 * `lg` breaks): mobile < 640px, tablet 640–1023px, desktop ≥ 1024px. A
 * {@link ResponsivePref} carries a value per tier so touch devices (no
 * hover) can default to always-visible controls while desktop keeps
 * hover-reveal — without ad-hoc Tailwind classes scattered per component.
 *
 * Defaults ship touch-aware values; the shell stamps `data-viewport` on
 * `<html>` so CSS can adapt instantly without re-render latency, and
 * {@link useResponsivePref} re-evaluates live on resize / orientation
 * change.
 */
import { useEffect, useState } from 'react'

export type ViewportTier = 'mobile' | 'tablet' | 'desktop'

export type ResponsivePref<T> = Record<ViewportTier, T>

export const VIEWPORT_TIERS: readonly ViewportTier[] = ['mobile', 'tablet', 'desktop']

export const MOBILE_MAX_PX = 639
export const TABLET_MAX_PX = 1023

export function viewportTierFromWidth(width: number): ViewportTier {
  if (width <= MOBILE_MAX_PX) return 'mobile'
  if (width <= TABLET_MAX_PX) return 'tablet'
  return 'desktop'
}

export function currentViewportTier(): ViewportTier {
  if (typeof window === 'undefined') return 'desktop'
  return viewportTierFromWidth(window.innerWidth)
}

/** Live tier updates on resize / orientation change. */
export function subscribeViewportTier(onChange: (tier: ViewportTier) => void): () => void {
  if (typeof window === 'undefined') return () => undefined
  const handler = () => onChange(currentViewportTier())
  window.addEventListener('resize', handler)
  return () => window.removeEventListener('resize', handler)
}

/** Reactive hook: the active tier for the current window. */
export function useViewportTier(): ViewportTier {
  const [tier, setTier] = useState<ViewportTier>(() => currentViewportTier())
  useEffect(() => subscribeViewportTier(setTier), [])
  return tier
}

/** Evaluate a pref for the active tier. */
export function useResponsivePref<T>(pref: ResponsivePref<T>): T {
  return pref[useViewportTier()]
}

// ----------------------------------------------------------- shipped prefs

/**
 * Message row actions (copy/reply/react/edit): always visible on touch
 * tiers, hover-reveal on desktop. This is the declared #833 default.
 */
export const DEFAULT_ACTIONS_ALWAYS_VISIBLE: ResponsivePref<boolean> = {
  mobile: true,
  tablet: true,
  desktop: false,
}

/**
 * #833 sidepane doctrine: left across ALL tiers; right placement is purely
 * an opt-in customization.
 */
export const DEFAULT_SIDEPANE_PLACEMENT: ResponsivePref<'left' | 'right'> = {
  mobile: 'left',
  tablet: 'left',
  desktop: 'left',
}

/** Shell attribute for CSS keyed on the active tier. */
export function viewportDataAttribute(tier: ViewportTier): string {
  return `data-viewport="${tier}"`
}

// --------------------------------------------------- persisted overrides

export const ACTIONS_VISIBLE_STORAGE_KEY = 'os.actionsAlwaysVisible'
export const ACTIONS_PREFS_CHANGED_EVENT = 'swarm:responsive-prefs-changed'

/** Load the per-tier action-row visibility override, or the shipped default. */
export function loadActionsAlwaysVisible(): ResponsivePref<boolean> {
  try {
    const raw = localStorage.getItem(ACTIONS_VISIBLE_STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<ResponsivePref<boolean>>
      if (typeof parsed === 'object' && parsed !== null) {
        return {
          mobile: parsed.mobile ?? DEFAULT_ACTIONS_ALWAYS_VISIBLE.mobile,
          tablet: parsed.tablet ?? DEFAULT_ACTIONS_ALWAYS_VISIBLE.tablet,
          desktop: parsed.desktop ?? DEFAULT_ACTIONS_ALWAYS_VISIBLE.desktop,
        }
      }
    }
  } catch {}
  return { ...DEFAULT_ACTIONS_ALWAYS_VISIBLE }
}

/** Persist the per-tier action-row visibility override and notify listeners. */
export function saveActionsAlwaysVisible(pref: ResponsivePref<boolean>): ResponsivePref<boolean> {
  try {
    localStorage.setItem(ACTIONS_VISIBLE_STORAGE_KEY, JSON.stringify(pref))
    window.dispatchEvent(new CustomEvent(ACTIONS_PREFS_CHANGED_EVENT))
  } catch {}
  return { ...pref }
}

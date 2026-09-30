/**
 * #1244 — global avatar motion preference.
 *
 * Browsers broadcast `prefers-reduced-motion: reduce` to suppress decorative
 * motion. On several desktop Linux setups (e.g. Omarchy) that flag is on by
 * default, which silently froze every avatar animation. This module is the
 * single source of truth for the avatar case:
 *
 * - system reduce is respected by default (accessibility preserved), and
 * - the operator can explicitly opt avatar motion back in from
 *   Settings → Aesthetics → Animate avatars.
 *
 * The preference is mirrored onto the document root as
 * `data-avatar-motion="always"`. The reduced-motion blocks in index.css are
 * gated on `html:not([data-avatar-motion='always']) …`, so when the opt-in is
 * on the suppression simply stops matching and the base animations resume.
 * The same rule feeds the JS schedulers in RobotAvatar/BeeAvatar through
 * `useAvatarMotionEnabled()`.
 */

import { useEffect, useState } from 'react'

export type AvatarMotionPreference = 'system' | 'always'

export const AVATAR_MOTION_STORAGE_KEY = 'os.avatarMotion'
export const AVATAR_MOTION_EVENT = 'os:avatar-motion'
export const AVATAR_MOTION_ATTRIBUTE = 'data-avatar-motion'

function safeStorage(): Storage | null {
  try {
    if (typeof globalThis.localStorage !== 'undefined') return globalThis.localStorage
  } catch {
    /* storage unavailable / blocked */
  }
  return null
}

/** Stored preference. Anything other than the explicit opt-in reads 'system'. */
export function loadAvatarMotionPreference(): AvatarMotionPreference {
  const storage = safeStorage()
  try {
    return storage?.getItem(AVATAR_MOTION_STORAGE_KEY) === 'always' ? 'always' : 'system'
  } catch {
    return 'system'
  }
}

/** Persist the preference, mirror it onto the root element, and notify. */
export function saveAvatarMotionPreference(
  preference: AvatarMotionPreference,
): AvatarMotionPreference {
  const next: AvatarMotionPreference = preference === 'always' ? 'always' : 'system'
  const storage = safeStorage()
  try {
    storage?.setItem(AVATAR_MOTION_STORAGE_KEY, next)
  } catch {
    /* storage unavailable / blocked */
  }
  applyAvatarMotionPreference()
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    try {
      window.dispatchEvent(new CustomEvent(AVATAR_MOTION_EVENT, { detail: next }))
    } catch {
      /* window unavailable */
    }
  }
  return next
}

/**
 * Reflect the stored preference onto the document root. `data-avatar-motion`
 * is present only for the explicit opt-in, so the default (absent) honours the
 * system reduced-motion setting.
 */
export function applyAvatarMotionPreference(
  root: HTMLElement | null = typeof document !== 'undefined' ? document.documentElement : null,
): AvatarMotionPreference {
  const preference = loadAvatarMotionPreference()
  if (root) {
    if (preference === 'always') root.setAttribute(AVATAR_MOTION_ATTRIBUTE, 'always')
    else root.removeAttribute(AVATAR_MOTION_ATTRIBUTE)
  }
  return preference
}

/** True when the operator has explicitly opted avatar motion back in. */
export function avatarMotionForced(): boolean {
  return loadAvatarMotionPreference() === 'always'
}

/** Raw OS/browser reduced-motion flag, independent of the opt-in. */
export function systemPrefersReducedMotion(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return false
  try {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches
  } catch {
    return false
  }
}

/**
 * True when motion should actually be suppressed for avatars: the system asks
 * for reduce *and* the operator has not opted back in.
 */
export function prefersReducedMotion(): boolean {
  return !avatarMotionForced() && systemPrefersReducedMotion()
}

/** Reactive preference; re-applies the root attribute and follows other tabs. */
export function useAvatarMotionPreference(): AvatarMotionPreference {
  const [preference, setPreference] = useState<AvatarMotionPreference>(
    loadAvatarMotionPreference,
  )
  useEffect(() => {
    const sync = () => {
      applyAvatarMotionPreference()
      setPreference(loadAvatarMotionPreference())
    }
    window.addEventListener(AVATAR_MOTION_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(AVATAR_MOTION_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return preference
}

/**
 * Whether avatar schedulers may run motion right now. Used by RobotAvatar and
 * BeeAvatar JS-driven blinks/wobbles so the opt-in covers them too (the CSS
 * loops are covered by the `html:not([data-avatar-motion='always'])` gate).
 */
export function useAvatarMotionEnabled(): boolean {
  const preference = useAvatarMotionPreference()
  const [systemReduce, setSystemReduce] = useState(systemPrefersReducedMotion)
  useEffect(() => {
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return
    const media = window.matchMedia('(prefers-reduced-motion: reduce)')
    const apply = () => setSystemReduce(media.matches)
    apply()
    if (typeof media.addEventListener === 'function') {
      media.addEventListener('change', apply)
      return () => media.removeEventListener('change', apply)
    }
    media.addListener(apply)
    return () => media.removeListener(apply)
  }, [])
  return preference === 'always' || !systemReduce
}

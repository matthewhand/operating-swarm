/**
 * Avatar theme preference (REQ-155 / #801).
 * Catalog of optional choices: Default (static / bland), Blobs (slit eyes),
 * Bee (googly geometric marks). Factory pick stays Blobs so existing users
 * are not switched; Bee is never auto-applied.
 * Persist is best-effort localStorage, same contract as the rail hostname override.
 */

export const AVATAR_THEME_STORAGE_KEY = 'swarm_avatar_theme'
export const AVATAR_THEME_SET_EVENT = 'swarm:set-avatar-theme'

/** REQ-194 key. Active since Phase 1; kept exported for back-compat with the
 * pre-Phase-1 disabled picker stub. */
export const ROBOT3D_THEME_RESERVED = 'robot3d'
export const ROBOT3D_ADR_HREF =
  'https://github.com/matthewhand/open-swarm/blob/main/docs/adr/008-3d-robot-avatar-theme.md'

export const AVATAR_THEMES = ['blobs', 'bland', 'default', 'bee', 'robot3d'] as const
export type AvatarTheme = (typeof AVATAR_THEMES)[number]

export function isAvatarTheme(value: unknown): value is AvatarTheme {
  return (
    value === 'blobs' ||
    value === 'bland' ||
    value === 'default' ||
    value === 'bee' ||
    value === 'robot3d'
  )
}

export function defaultAvatarTheme(): AvatarTheme {
  return 'blobs'
}

export function loadAvatarTheme(): AvatarTheme {
  try {
    const stored = localStorage.getItem(AVATAR_THEME_STORAGE_KEY)
    if (isAvatarTheme(stored)) {
      return stored === 'default' ? 'bland' : stored
    }
  } catch {
    /* storage unavailable */
  }
  return defaultAvatarTheme()
}

export function saveAvatarTheme(value: string): AvatarTheme {
  const normalized = value === 'default' ? 'bland' : value
  const next = isAvatarTheme(normalized) ? normalized : defaultAvatarTheme()
  try {
    if (next === defaultAvatarTheme()) {
      localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    } else {
      localStorage.setItem(AVATAR_THEME_STORAGE_KEY, next)
    }
  } catch {
    /* persistence is best-effort */
  }
  dispatchAvatarTheme(next)
  return next
}

export function dispatchAvatarTheme(theme: AvatarTheme): void {
  try {
    window.dispatchEvent(new CustomEvent<AvatarTheme>(AVATAR_THEME_SET_EVENT, { detail: theme }))
  } catch {
    /* window unavailable */
  }
}

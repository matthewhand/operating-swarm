/**
 * Avatar theme preference (REQ-155 / #801 / REQ-828).
 * Settings installs a set of themes; each agent picks from that set.
 * Persist is best-effort localStorage, same contract as the rail hostname override.
 */

import { GITHUB_REPO } from './githubRelease'

export const AVATAR_THEME_STORAGE_KEY = 'swarm_avatar_theme'
export const AVATAR_THEME_SET_EVENT = 'swarm:set-avatar-theme'
export const AVATAR_THEMES_ENABLED_KEY = 'swarm_avatar_themes_enabled'
export const AVATAR_THEMES_ENABLED_EVENT = 'swarm:set-avatar-themes-enabled'

/** REQ-194 key. Active since Phase 1; kept exported for back-compat with the
 * pre-Phase-1 disabled picker stub. */
export const ROBOT3D_THEME_RESERVED = 'robot3d'
export const ROBOT3D_ADR_HREF =
  `https://github.com/${GITHUB_REPO}/blob/main/docs/adr/008-3d-robot-avatar-theme.md`

export const FACE_AVATAR_THEMES = ['blobs', 'bland', 'default', 'bee', 'robot3d'] as const
export const ROBOT_PACK_THEME_IDS = [
  'chassis',
  'pixel',
  'glyph',
  'orb',
  'antenna',
  'cube',
  'mask',
  'beetle',
  'ghost',
  'crystal',
] as const

export const AVATAR_THEMES = [...FACE_AVATAR_THEMES, ...ROBOT_PACK_THEME_IDS] as const
export type AvatarTheme = (typeof AVATAR_THEMES)[number]

const THEME_SET = new Set<string>(AVATAR_THEMES)

export const AVATAR_THEME_FAMILY_IDS = ['bee', 'blobs', 'bland', 'robot3d', 'robots'] as const
export type AvatarThemeFamily = (typeof AVATAR_THEME_FAMILY_IDS)[number]

const ROBOT_PACK_AVATARS: { id: AvatarTheme; label: string }[] = [
  { id: 'chassis', label: 'Chassis' },
  { id: 'pixel', label: 'Pixel' },
  { id: 'glyph', label: 'Glyph' },
  { id: 'orb', label: 'Orb' },
  { id: 'antenna', label: 'Antenna' },
  { id: 'cube', label: 'Cube' },
  { id: 'mask', label: 'Mask' },
  { id: 'beetle', label: 'Beetle' },
  { id: 'ghost', label: 'Ghost' },
  { id: 'crystal', label: 'Crystal' },
]

/** Installable themes. Robot bodies are avatars inside the Robots theme, not themes. */
export const AVATAR_THEME_FAMILIES: {
  id: AvatarThemeFamily
  label: string
  avatars: { id: AvatarTheme; label: string }[]
}[] = [
  { id: 'bee', label: 'Bee', avatars: [{ id: 'bee', label: 'Bee' }] },
  { id: 'blobs', label: 'Blobs', avatars: [{ id: 'blobs', label: 'Blobs' }] },
  { id: 'bland', label: 'Default', avatars: [{ id: 'bland', label: 'Default' }] },
  { id: 'robot3d', label: '3D robot', avatars: [{ id: 'robot3d', label: '3D robot' }] },
  { id: 'robots', label: 'Robots', avatars: ROBOT_PACK_AVATARS },
]

export const INSTALLABLE_AVATAR_THEMES = AVATAR_THEME_FAMILIES.flatMap((family) =>
  family.avatars.map((avatar) => ({ id: avatar.id, label: avatar.label })),
)

export function isAvatarTheme(value: unknown): value is AvatarTheme {
  return typeof value === 'string' && THEME_SET.has(value)
}

export function isRobotPackTheme(value: string): boolean {
  return (ROBOT_PACK_THEME_IDS as readonly string[]).includes(value)
}

export function isAvatarThemeFamily(value: unknown): value is AvatarThemeFamily {
  return typeof value === 'string' && (AVATAR_THEME_FAMILY_IDS as readonly string[]).includes(value)
}

export function familyForAvatarTheme(theme: AvatarTheme): AvatarThemeFamily {
  if (isRobotPackTheme(theme)) return 'robots'
  if (theme === 'default') return 'bland'
  return theme
}

export function avatarsForFamily(
  family: AvatarThemeFamily,
): { id: AvatarTheme; label: string }[] {
  return AVATAR_THEME_FAMILIES.find((item) => item.id === family)?.avatars ?? []
}

export function expandAvatarFamilies(families: AvatarThemeFamily[]): AvatarTheme[] {
  const out: AvatarTheme[] = []
  const seen = new Set<AvatarTheme>()
  for (const id of families) {
    const family = AVATAR_THEME_FAMILIES.find((item) => item.id === id)
    if (!family) continue
    for (const avatar of family.avatars) {
      if (seen.has(avatar.id)) continue
      seen.add(avatar.id)
      out.push(avatar.id)
    }
  }
  return out
}

export function uniqueAvatarFamilies(themes: AvatarTheme[]): AvatarThemeFamily[] {
  const seen = new Set<AvatarThemeFamily>()
  const out: AvatarThemeFamily[] = []
  for (const theme of themes) {
    const family = familyForAvatarTheme(theme)
    if (seen.has(family)) continue
    seen.add(family)
    out.push(family)
  }
  return out
}

export function normalizeAvatarFamily(value: unknown): AvatarThemeFamily | null {
  if (isAvatarThemeFamily(value)) return value
  const theme = normalizeAvatarTheme(value)
  return theme ? familyForAvatarTheme(theme) : null
}

/** Factory default stays Blobs (#820): existing users are not switched to Bee.
 * Bee and the other packs are optional installs — never auto-applied. */
export function defaultAvatarTheme(): AvatarTheme {
  return 'blobs'
}

export function normalizeAvatarTheme(value: unknown): AvatarTheme | null {
  if (value === 'default') return 'bland'
  return isAvatarTheme(value) ? value : null
}

export function loadAvatarTheme(): AvatarTheme {
  try {
    const stored = localStorage.getItem(AVATAR_THEME_STORAGE_KEY)
    const normalized = normalizeAvatarTheme(stored)
    if (normalized) return normalized
  } catch {
    /* storage unavailable */
  }
  return defaultAvatarTheme()
}

export function saveAvatarTheme(value: string): AvatarTheme {
  const next = normalizeAvatarTheme(value) ?? defaultAvatarTheme()
  try {
    if (next === defaultAvatarTheme()) {
      localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
    } else {
      localStorage.setItem(AVATAR_THEME_STORAGE_KEY, next)
    }
    ensureThemeEnabled(next)
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

function sanitizeFamilies(parsed: unknown): AvatarThemeFamily[] {
  if (!Array.isArray(parsed)) return []
  const seen = new Set<AvatarThemeFamily>()
  const out: AvatarThemeFamily[] = []
  for (const item of parsed) {
    const family = normalizeAvatarFamily(item)
    if (!family || seen.has(family)) continue
    seen.add(family)
    out.push(family)
  }
  return out
}

export function loadEnabledAvatarFamilies(): AvatarThemeFamily[] {
  try {
    const stored = localStorage.getItem(AVATAR_THEMES_ENABLED_KEY)
    if (stored) {
      const families = sanitizeFamilies(JSON.parse(stored))
      if (families.length) return families
    }
  } catch {
    /* storage unavailable or invalid JSON */
  }
  return uniqueAvatarFamilies([loadAvatarTheme()])
}

function dispatchEnabledAvatarThemes(themes: AvatarTheme[]): void {
  try {
    window.dispatchEvent(
      new CustomEvent<AvatarTheme[]>(AVATAR_THEMES_ENABLED_EVENT, { detail: themes }),
    )
  } catch {
    /* window unavailable */
  }
}

/** When the enabled key is unset, derive from the global theme so existing
 * single-theme users keep their look. Default / empty global → blobs. */
export function loadEnabledAvatarThemes(): AvatarTheme[] {
  return expandAvatarFamilies(loadEnabledAvatarFamilies())
}

export function saveEnabledAvatarThemes(values: unknown): AvatarTheme[] {
  const families = sanitizeFamilies(values)
  const enabledFamilies = families.length
    ? families
    : [familyForAvatarTheme(defaultAvatarTheme())]
  try {
    localStorage.setItem(AVATAR_THEMES_ENABLED_KEY, JSON.stringify(enabledFamilies))
  } catch {
    /* persistence is best-effort */
  }
  const enabled = expandAvatarFamilies(enabledFamilies)
  dispatchEnabledAvatarThemes(enabled)
  const global = loadAvatarTheme()
  if (enabled.length === 1 || !enabled.includes(global)) {
    saveAvatarTheme(enabled[0])
  }
  return enabled
}

function ensureThemeEnabled(theme: AvatarTheme): void {
  try {
    if (localStorage.getItem(AVATAR_THEMES_ENABLED_KEY) === null) return
    const families = loadEnabledAvatarFamilies()
    const family = familyForAvatarTheme(theme)
    if (families.includes(family)) return
    saveEnabledAvatarThemes([...families, family])
  } catch {
    /* persistence is best-effort */
  }
}

export function toggleEnabledAvatarTheme(id: string, on?: boolean): AvatarTheme[] {
  const families = loadEnabledAvatarFamilies()
  const family = normalizeAvatarFamily(id)
  if (!family) return expandAvatarFamilies(families)
  const has = families.includes(family)
  const enable = on ?? !has
  if (enable && !has) return saveEnabledAvatarThemes([...families, family])
  if (!enable && has) {
    if (families.length === 1) return expandAvatarFamilies(families)
    return saveEnabledAvatarThemes(families.filter((item) => item !== family))
  }
  return expandAvatarFamilies(families)
}

/** Per-agent (if still installed) → the sole enabled theme → global if installed → first enabled. */
export function resolveAvatarTheme(
  perAgent?: string | null,
  enabled: AvatarTheme[] = loadEnabledAvatarThemes(),
  global: AvatarTheme = loadAvatarTheme(),
): AvatarTheme {
  const installed = enabled.length ? enabled : [defaultAvatarTheme()]
  const per = normalizeAvatarTheme(perAgent ?? null)
  if (per && installed.includes(per)) return per
  if (installed.length === 1) return installed[0]
  if (installed.includes(global)) return global
  return installed[0] ?? defaultAvatarTheme()
}

/** Sole remaining enabled theme, else brand default if still installed, else first enabled. */
export function fallbackEnabledAvatarTheme(enabled: AvatarTheme[]): AvatarTheme {
  const installed = enabled.length ? enabled : [defaultAvatarTheme()]
  if (installed.length === 1) return installed[0]
  const def = defaultAvatarTheme()
  return installed.includes(def) ? def : installed[0]
}

/** Rewrite per-agent packs that are no longer installed (REQ-841). Same object if unchanged. */
export function stripDisabledAvatarThemes(
  byAgent: Record<string, AvatarTheme>,
  enabled: AvatarTheme[],
): Record<string, AvatarTheme> {
  const installed = enabled.length ? enabled : [defaultAvatarTheme()]
  const fallback = fallbackEnabledAvatarTheme(installed)
  let changed = false
  const next: Record<string, AvatarTheme> = {}
  for (const [agentId, theme] of Object.entries(byAgent)) {
    if (installed.includes(theme)) {
      next[agentId] = theme
    } else {
      next[agentId] = fallback
      changed = true
    }
  }
  return changed ? next : byAgent
}

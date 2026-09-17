export const THEME_STORAGE_KEY = 'swarm_theme'
export const THEME_SET_EVENT = 'swarm:set-theme'
export const THEME_TOGGLE_EVENT = 'swarm:toggle-theme'
export const THEME_NAVBAR_STORAGE_KEY = 'swarm_theme_navbar'
export const THEME_NAVBAR_SET_EVENT = 'swarm:set-theme-navbar'

/** #529: a strict two-state light ↔ dark switch — no 'system' option. */
export type Theme = 'dark' | 'light'
export type ResolvedTheme = Theme

export function resolveSystemTheme(): ResolvedTheme {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'dark'
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  return theme
}

export function subscribeSystemTheme(onChange: (resolved: ResolvedTheme) => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return () => {}
  }
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const listener = (event: MediaQueryListEvent | MediaQueryList) => {
    onChange(event.matches ? 'dark' : 'light')
  }
  if (typeof media.addEventListener === 'function') {
    media.addEventListener('change', listener)
    return () => media.removeEventListener('change', listener)
  }
  if (typeof (media as any).addListener === 'function') {
    ;(media as any).addListener(listener)
    return () => (media as any).removeListener(listener)
  }
  return () => {}
}

export function initialTheme(): Theme {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    // 'system' was accepted by the old 3-state cycle (#529): migrate it to its
    // current resolved value so nobody's stored preference is lost.
    if (stored === 'light' || stored === 'dark') return stored
    if (stored === 'system') return resolveSystemTheme()
  } catch {
    /* storage unavailable — fall through to the dark default */
  }
  return 'dark'
}

export function nextTheme(theme: Theme): Theme {
  return theme === 'dark' ? 'light' : 'dark'
}

export function persistTheme(theme: Theme): void {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
  } catch {
    /* persistence is best-effort */
  }
}

export function dispatchSetTheme(theme: Theme): void {
  persistTheme(theme)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<Theme>(THEME_SET_EVENT, { detail: theme }))
  }
}

export function dispatchToggleTheme(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent(THEME_TOGGLE_EVENT))
  }
}

export function initialNavbarThemeVisible(): boolean {
  try {
    const stored = localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)
    if (stored === 'false') return false
    if (stored === 'true') return true
  } catch {
    /* storage unavailable — default is on */
  }
  return true
}

export function persistNavbarThemeVisible(visible: boolean): void {
  try {
    localStorage.setItem(THEME_NAVBAR_STORAGE_KEY, String(visible))
  } catch {
    /* persistence is best-effort */
  }
}

export function dispatchSetNavbarThemeVisible(visible: boolean): void {
  persistNavbarThemeVisible(visible)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<boolean>(THEME_NAVBAR_SET_EVENT, { detail: visible }),
    )
  }
}

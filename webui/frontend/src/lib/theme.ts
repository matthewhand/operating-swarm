export const THEME_STORAGE_KEY = 'swarm_theme'
export const THEME_SET_EVENT = 'swarm:set-theme'
export const THEME_TOGGLE_EVENT = 'swarm:toggle-theme'
export const THEME_NAVBAR_STORAGE_KEY = 'swarm_theme_navbar'
export const THEME_NAVBAR_SET_EVENT = 'swarm:set-theme-navbar'
export const THEME_NAVBAR_MODE_STORAGE_KEY = 'swarm_theme_navbar_mode'
export const THEME_NAVBAR_MODE_SET_EVENT = 'swarm:set-theme-navbar-mode'

/** #847: 'system' is the default across all views; users can lock to 'dark' or 'light'. */
export type Theme = 'system' | 'dark' | 'light'
export type ResolvedTheme = 'dark' | 'light'
export const DEFAULT_THEME: Theme = 'system'

/** #847: 3-way top navbar theme toggle visibility mode. */
export type NavbarThemeToggleMode = 'if_not_system' | 'always' | 'never'
export const DEFAULT_NAVBAR_THEME_TOGGLE_MODE: NavbarThemeToggleMode = 'if_not_system'

export function resolveSystemTheme(): ResolvedTheme {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'dark'
}

export function resolveTheme(theme: Theme): ResolvedTheme {
  if (theme === 'system') return resolveSystemTheme()
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
    if (stored === 'light' || stored === 'dark' || stored === 'system') return stored
  } catch {
    /* storage unavailable — fall through to system default */
  }
  return DEFAULT_THEME
}

export function nextTheme(theme: Theme): Theme {
  if (theme === 'system') {
    const current = resolveSystemTheme()
    return current === 'dark' ? 'light' : 'dark'
  }
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

export function isNavbarThemeToggleVisible(
  mode: NavbarThemeToggleMode,
  theme: Theme,
): boolean {
  if (mode === 'never') return false
  if (mode === 'always') return true
  return theme !== 'system'
}

export function initialNavbarThemeMode(): NavbarThemeToggleMode {
  try {
    const storedMode = localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)
    if (storedMode === 'if_not_system' || storedMode === 'always' || storedMode === 'never') {
      return storedMode
    }
    const legacy = localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)
    if (legacy === 'false') return 'never'
    if (legacy === 'true') return 'always'
  } catch {
    /* storage unavailable */
  }
  return DEFAULT_NAVBAR_THEME_TOGGLE_MODE
}

export function persistNavbarThemeMode(mode: NavbarThemeToggleMode): void {
  try {
    localStorage.setItem(THEME_NAVBAR_MODE_STORAGE_KEY, mode)
    localStorage.setItem(THEME_NAVBAR_STORAGE_KEY, String(mode !== 'never'))
  } catch {
    /* persistence is best-effort */
  }
}

export function dispatchSetNavbarThemeMode(mode: NavbarThemeToggleMode): void {
  persistNavbarThemeMode(mode)
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<NavbarThemeToggleMode>(THEME_NAVBAR_MODE_SET_EVENT, { detail: mode }),
    )
  }
}

export function initialNavbarThemeVisible(): boolean {
  return initialNavbarThemeMode() !== 'never'
}

export function persistNavbarThemeVisible(visible: boolean): void {
  persistNavbarThemeMode(visible ? 'always' : 'never')
}

export function dispatchSetNavbarThemeVisible(visible: boolean): void {
  dispatchSetNavbarThemeMode(visible ? 'always' : 'never')
  if (typeof window !== 'undefined') {
    window.dispatchEvent(
      new CustomEvent<boolean>(THEME_NAVBAR_SET_EVENT, { detail: visible }),
    )
  }
}

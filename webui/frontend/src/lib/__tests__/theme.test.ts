import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  dispatchSetNavbarThemeVisible,
  dispatchSetTheme,
  initialNavbarThemeVisible,
  initialTheme,
  nextTheme,
  persistNavbarThemeVisible,


  resolveTheme,
  subscribeSystemTheme,
  THEME_NAVBAR_SET_EVENT,
  THEME_NAVBAR_STORAGE_KEY,
  THEME_SET_EVENT,
  THEME_STORAGE_KEY,
} from '../theme'

describe('theme helpers (REQ-110)', () => {
  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('initialTheme defaults to dark when nothing stored', () => {
    expect(initialTheme()).toBe('dark')
  })

  it('initialTheme reads light or dark from localStorage; a stored system migrates to its resolved value', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    expect(initialTheme()).toBe('light')

    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(initialTheme()).toBe('dark')

    // #529: 'system' is gone — an existing stored value resolves once so no
    // preference is lost by the migration.
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    localStorage.setItem(THEME_STORAGE_KEY, 'system')
    expect(initialTheme()).toBe('dark')
  })

  it('nextTheme flips dark <-> light (two-state, no system)', () => {
    expect(nextTheme('dark')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
  })

  it('resolveTheme returns light and dark directly', () => {
    expect(resolveTheme('light')).toBe('light')
    expect(resolveTheme('dark')).toBe('dark')
  })

  it('subscribeSystemTheme listens to matchMedia change events', () => {
    let listener: ((e: any) => void) | null = null
    const addEventListener = vi.fn((_event: string, fn: any) => {
      listener = fn
    })
    const removeEventListener = vi.fn()

    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener,
      removeEventListener,
    }))

    const onChange = vi.fn()
    const unsubscribe = subscribeSystemTheme(onChange)

    expect(addEventListener).toHaveBeenCalledWith('change', expect.any(Function))
    expect(listener).not.toBeNull()

    // Trigger dark change
    listener!({ matches: false } as any)
    expect(onChange).toHaveBeenCalledWith('light')

    listener!({ matches: true } as any)
    expect(onChange).toHaveBeenCalledWith('dark')

    unsubscribe()
    expect(removeEventListener).toHaveBeenCalledWith('change', expect.any(Function))
  })

  it('navbar theme control visibility defaults to true and persists changes', () => {
    expect(initialNavbarThemeVisible()).toBe(true)

    persistNavbarThemeVisible(false)
    expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('false')
    expect(initialNavbarThemeVisible()).toBe(false)

    persistNavbarThemeVisible(true)
    expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('true')
    expect(initialNavbarThemeVisible()).toBe(true)
  })

  it('dispatchSetNavbarThemeVisible dispatches event and persists', () => {
    const onNavbarToggle = vi.fn()
    window.addEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)

    dispatchSetNavbarThemeVisible(false)
    expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('false')
    expect(onNavbarToggle).toHaveBeenCalled()

    window.removeEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
  })

  it('dispatchSetTheme dispatches event and persists theme', () => {
    const onSet = vi.fn()
    window.addEventListener(THEME_SET_EVENT, onSet)

    dispatchSetTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(onSet).toHaveBeenCalled()

    window.removeEventListener(THEME_SET_EVENT, onSet)
  })
})

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

  it('initialTheme reads light, dark, or system from localStorage', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    expect(initialTheme()).toBe('light')

    localStorage.setItem(THEME_STORAGE_KEY, 'system')
    expect(initialTheme()).toBe('system')

    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(initialTheme()).toBe('dark')
  })

  it('nextTheme cycles dark -> light -> system -> dark', () => {
    expect(nextTheme('dark')).toBe('light')
    expect(nextTheme('light')).toBe('system')
    expect(nextTheme('system')).toBe('dark')
  })

  it('resolveTheme resolves light and dark directly, and system via matchMedia', () => {
    expect(resolveTheme('light')).toBe('light')
    expect(resolveTheme('dark')).toBe('dark')

    // Mock matchMedia dark = true
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    expect(resolveTheme('system')).toBe('dark')

    // Mock matchMedia dark = false (light)
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    expect(resolveTheme('system')).toBe('light')
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

    dispatchSetTheme('system')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')
    expect(onSet).toHaveBeenCalled()

    window.removeEventListener(THEME_SET_EVENT, onSet)
  })
})

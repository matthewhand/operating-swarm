import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  DEFAULT_NAVBAR_THEME_TOGGLE_MODE,
  DEFAULT_THEME,
  dispatchSetNavbarThemeMode,
  dispatchSetNavbarThemeVisible,
  dispatchSetTheme,
  initialNavbarThemeMode,
  initialTheme,
  isNavbarThemeToggleVisible,
  nextTheme,
  persistNavbarThemeMode,
  resolveTheme,
  subscribeSystemTheme,
  THEME_NAVBAR_MODE_SET_EVENT,
  THEME_NAVBAR_MODE_STORAGE_KEY,
  THEME_NAVBAR_SET_EVENT,
  THEME_NAVBAR_STORAGE_KEY,
  THEME_SET_EVENT,
  THEME_STORAGE_KEY,
} from '../theme'

describe('theme helpers (REQ-110 & #847)', () => {
  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_MODE_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('initialTheme defaults to system when nothing stored', () => {
    expect(initialTheme()).toBe(DEFAULT_THEME)
    expect(initialTheme()).toBe('system')
  })

  it('initialTheme reads light, dark, or system from localStorage', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    expect(initialTheme()).toBe('light')

    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    expect(initialTheme()).toBe('dark')

    localStorage.setItem(THEME_STORAGE_KEY, 'system')
    expect(initialTheme()).toBe('system')
  })

  it('nextTheme flips dark <-> light, and flips relative to system when system is active', () => {
    expect(nextTheme('dark')).toBe('light')
    expect(nextTheme('light')).toBe('dark')

    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true, // dark
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    expect(nextTheme('system')).toBe('light')

    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: false, // light
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    expect(nextTheme('system')).toBe('dark')
  })

  it('resolveTheme resolves system dynamically and returns explicit values directly', () => {
    expect(resolveTheme('light')).toBe('light')
    expect(resolveTheme('dark')).toBe('dark')

    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))
    expect(resolveTheme('system')).toBe('dark')

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

  describe('isNavbarThemeToggleVisible matrix', () => {
    it('returns false for mode never regardless of theme', () => {
      expect(isNavbarThemeToggleVisible('never', 'system')).toBe(false)
      expect(isNavbarThemeToggleVisible('never', 'light')).toBe(false)
      expect(isNavbarThemeToggleVisible('never', 'dark')).toBe(false)
    })

    it('returns true for mode always regardless of theme', () => {
      expect(isNavbarThemeToggleVisible('always', 'system')).toBe(true)
      expect(isNavbarThemeToggleVisible('always', 'light')).toBe(true)
      expect(isNavbarThemeToggleVisible('always', 'dark')).toBe(true)
    })

    it('returns false for mode if_not_system when theme is system, true otherwise', () => {
      expect(isNavbarThemeToggleVisible('if_not_system', 'system')).toBe(false)
      expect(isNavbarThemeToggleVisible('if_not_system', 'light')).toBe(true)
      expect(isNavbarThemeToggleVisible('if_not_system', 'dark')).toBe(true)
    })
  })

  describe('navbar theme toggle mode storage and events', () => {
    it('defaults to if_not_system mode when nothing stored', () => {
      expect(initialNavbarThemeMode()).toBe(DEFAULT_NAVBAR_THEME_TOGGLE_MODE)
      expect(initialNavbarThemeMode()).toBe('if_not_system')
    })

    it('migrates legacy boolean storage keys', () => {
      localStorage.setItem(THEME_NAVBAR_STORAGE_KEY, 'false')
      expect(initialNavbarThemeMode()).toBe('never')

      localStorage.setItem(THEME_NAVBAR_STORAGE_KEY, 'true')
      expect(initialNavbarThemeMode()).toBe('always')
    })

    it('persists navbar theme mode directly', () => {
      persistNavbarThemeMode('never')
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('never')
      expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('false')
      expect(initialNavbarThemeMode()).toBe('never')

      persistNavbarThemeMode('always')
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('always')
      expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('true')
      expect(initialNavbarThemeMode()).toBe('always')

      persistNavbarThemeMode('if_not_system')
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('if_not_system')
      expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('true')
      expect(initialNavbarThemeMode()).toBe('if_not_system')
    })

    it('dispatchSetNavbarThemeMode dispatches event and persists', () => {
      const onModeSet = vi.fn()
      window.addEventListener(THEME_NAVBAR_MODE_SET_EVENT, onModeSet)

      dispatchSetNavbarThemeMode('never')
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('never')
      expect(onModeSet).toHaveBeenCalled()

      window.removeEventListener(THEME_NAVBAR_MODE_SET_EVENT, onModeSet)
    })

    it('dispatchSetNavbarThemeVisible provides backward compatibility', () => {
      const onNavbarToggle = vi.fn()
      window.addEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)

      dispatchSetNavbarThemeVisible(false)
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('never')
      expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('false')
      expect(onNavbarToggle).toHaveBeenCalled()

      dispatchSetNavbarThemeVisible(true)
      expect(localStorage.getItem(THEME_NAVBAR_MODE_STORAGE_KEY)).toBe('always')
      expect(localStorage.getItem(THEME_NAVBAR_STORAGE_KEY)).toBe('true')

      window.removeEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
    })
  })

  it('dispatchSetTheme dispatches event and persists theme', () => {
    const onSet = vi.fn()
    window.addEventListener(THEME_SET_EVENT, onSet)

    dispatchSetTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(onSet).toHaveBeenCalled()

    dispatchSetTheme('system')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('system')

    window.removeEventListener(THEME_SET_EVENT, onSet)
  })
})

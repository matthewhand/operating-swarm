import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ThemeToggle from '../ThemeToggle'
import {
  dispatchSetNavbarThemeMode,
  dispatchSetNavbarThemeVisible,
  dispatchSetTheme,
  THEME_NAVBAR_MODE_STORAGE_KEY,
  THEME_NAVBAR_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from '../../lib/theme'

describe('ThemeToggle component (#847: default system & 3-way navbar toggle mode)', () => {
  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_MODE_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('is hidden by default when theme is system and mode is if_not_system', () => {
    render(<ThemeToggle />)
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()
  })

  it('renders and toggles dark -> light -> dark when theme is set to dark', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: 'Switch to light theme' })
    expect(button).toBeInTheDocument()

    // Click 1: dark -> light
    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    // Click 2: light -> dark
    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('renders when navbar mode is always even if theme is system', () => {
    localStorage.setItem(THEME_NAVBAR_MODE_STORAGE_KEY, 'always')
    vi.stubGlobal('matchMedia', vi.fn().mockReturnValue({
      matches: true, // dark
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }))

    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: 'Switch to light theme' })
    expect(button).toBeInTheDocument()

    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
  })

  it('hides when navbar mode is set to never', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()

    act(() => {
      dispatchSetNavbarThemeMode('never')
    })
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()
  })

  it('dynamically reveals toggle when theme switches from system to explicit mode under default if_not_system', () => {
    render(<ThemeToggle />)
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()

    act(() => {
      dispatchSetTheme('dark')
    })
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()

    act(() => {
      dispatchSetTheme('system')
    })
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()
  })

  it('backward compatibility: responds to legacy dispatchSetNavbarThemeVisible', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()

    act(() => {
      dispatchSetNavbarThemeVisible(false)
    })
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()

    act(() => {
      dispatchSetNavbarThemeVisible(true)
    })
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
  })
})

// #848: a navbar click is a preference change, so it must sync to
// /v1/preferences/ like the Settings control (silent no-op for guests).
describe('#848 — navbar theme clicks persist to user preferences', () => {
  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_MODE_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('PATCHes theme when the navbar toggle is clicked', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    })
    vi.stubGlobal('fetch', fetchMock)

    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))

    await vi.waitFor(() => {
      const patch = fetchMock.mock.calls.find(
        ([url, init]) =>
          String(url).includes('/v1/preferences/') && (init as RequestInit | undefined)?.method === 'PATCH',
      )
      expect(patch).toBeDefined()
      const body = JSON.parse(String((patch as unknown as [string, RequestInit])[1].body))
      expect(body.theme).toBe('light')
    })
  })

  it('does not crash when the sync fails (guest / offline)', async () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    render(<ThemeToggle />)
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    await vi.waitFor(() => {
      expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    })
  })
})

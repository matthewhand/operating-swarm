import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ThemeToggle from '../ThemeToggle'
import {
  dispatchSetNavbarThemeVisible,
  dispatchSetTheme,
  initialTheme,
  THEME_NAVBAR_STORAGE_KEY,
  THEME_STORAGE_KEY,
} from '../../lib/theme'

describe('ThemeToggle component (#529: strict light <-> dark)', () => {
  afterEach(() => {
    localStorage.removeItem(THEME_STORAGE_KEY)
    localStorage.removeItem(THEME_NAVBAR_STORAGE_KEY)
    vi.unstubAllGlobals()
  })

  it('toggles dark -> light -> dark with the label always reflecting the current mode', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: 'Switch to light theme' })
    expect(button).toBeInTheDocument()

    // Click 1: dark -> light
    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Switch to dark theme' })).toBeInTheDocument()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')

    // Click 2: light -> dark — a strict two-state flip, no system stop-over
    fireEvent.click(button)
    expect(screen.getByRole('button', { name: 'Switch to light theme' })).toBeInTheDocument()
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark')
  })

  it('never offers or persists a system value', () => {
    render(<ThemeToggle />)
    const button = screen.getByRole('button', { name: /Switch to (light|dark) theme/ })
    fireEvent.click(button)
    fireEvent.click(button)
    expect(localStorage.getItem(THEME_STORAGE_KEY)).not.toBe('system')
    expect(['light', 'dark']).toContain(localStorage.getItem(THEME_STORAGE_KEY))
    // An external stale 'system' set is refused by the toggle's handler.
    act(() => {
      dispatchSetTheme('system' as never)
    })
    expect(['light', 'dark']).toContain(initialTheme())
  })

  it('hides when navbar theme control is toggled off, and reappears when toggled on', () => {
    render(<ThemeToggle />)
    expect(screen.getByRole('button', { name: /Switch to (light|dark) theme/ })).toBeInTheDocument()

    act(() => {
      dispatchSetNavbarThemeVisible(false)
    })
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()

    act(() => {
      dispatchSetNavbarThemeVisible(true)
    })
    expect(screen.getByRole('button', { name: /Switch to (light|dark) theme/ })).toBeInTheDocument()
  })

  it('respects initial persisted hidden state', () => {
    localStorage.setItem(THEME_NAVBAR_STORAGE_KEY, 'false')
    render(<ThemeToggle />)
    expect(screen.queryByRole('button', { name: /Switch to (light|dark) theme/ })).not.toBeInTheDocument()
  })
})

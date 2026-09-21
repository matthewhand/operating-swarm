import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import {
  dispatchSetTheme,
  initialNavbarThemeMode,
  initialTheme,
  isNavbarThemeToggleVisible,
  nextTheme,
  resolveSystemTheme,
  THEME_NAVBAR_MODE_SET_EVENT,
  THEME_NAVBAR_SET_EVENT,
  THEME_SET_EVENT,
  THEME_TOGGLE_EVENT,
  type NavbarThemeToggleMode,
  type Theme,
} from '../lib/theme'

export default function ThemeToggle({ className = '' }: { className?: string }) {
  const [mode, setMode] = useState<NavbarThemeToggleMode>(initialNavbarThemeMode)
  const [theme, setTheme] = useState<Theme>(initialTheme)

  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail
      if (detail === 'light' || detail === 'dark' || detail === 'system') {
        setTheme(detail)
      }
    }
    const onToggle = () => {
      setTheme((prev) => nextTheme(prev))
    }
    const onNavbarMode = (event: Event) => {
      const detail = (event as CustomEvent<NavbarThemeToggleMode>).detail
      if (detail === 'if_not_system' || detail === 'always' || detail === 'never') {
        setMode(detail)
      }
    }
    const onNavbarToggle = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail
      setMode(detail ? 'always' : 'never')
    }

    window.addEventListener(THEME_SET_EVENT, onSet)
    window.addEventListener(THEME_TOGGLE_EVENT, onToggle)
    window.addEventListener(THEME_NAVBAR_MODE_SET_EVENT, onNavbarMode)
    window.addEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)

    return () => {
      window.removeEventListener(THEME_SET_EVENT, onSet)
      window.removeEventListener(THEME_TOGGLE_EVENT, onToggle)
      window.removeEventListener(THEME_NAVBAR_MODE_SET_EVENT, onNavbarMode)
      window.removeEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
    }
  }, [])

  if (!isNavbarThemeToggleVisible(mode, theme)) return null

  const resolved = theme === 'system' ? resolveSystemTheme() : theme
  const next = resolved === 'dark' ? 'light' : 'dark'
  const ariaLabel =
    resolved === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <button
      type="button"
      className={`btn btn-ghost btn-sm btn-square shrink-0 ${className}`}
      aria-label={ariaLabel}
      title={`Theme: ${theme}. Click to switch to ${next}`}
      data-testid="theme-toggle-btn"
      onClick={() => dispatchSetTheme(next)}
    >
      {resolved === 'dark' ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  )
}

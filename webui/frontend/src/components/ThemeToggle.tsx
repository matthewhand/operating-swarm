import { useEffect, useState } from 'react'
import { Moon, Sun } from 'lucide-react'
import {
  dispatchSetTheme,
  initialNavbarThemeVisible,
  initialTheme,
  nextTheme,
  resolveTheme,
  THEME_NAVBAR_SET_EVENT,
  THEME_SET_EVENT,
  THEME_TOGGLE_EVENT,
  type Theme,
} from '../lib/theme'

export default function ThemeToggle({ className = '' }: { className?: string }) {
  const [visible, setVisible] = useState<boolean>(initialNavbarThemeVisible)
  const [theme, setTheme] = useState<Theme>(initialTheme)
  // Only the setter is read (state value is tracked but never rendered).
  const [, setResolvedTheme] = useState(() => resolveTheme(initialTheme()))

  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail
      if (detail === 'light' || detail === 'dark') {
        setTheme(detail)
        setResolvedTheme(resolveTheme(detail))
      }
    }
    const onToggle = () => {
      setTheme((prev) => {
        const next = nextTheme(prev)
        setResolvedTheme(resolveTheme(next))
        return next
      })
    }
    const onNavbarToggle = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail
      setVisible(Boolean(detail))
    }

    window.addEventListener(THEME_SET_EVENT, onSet)
    window.addEventListener(THEME_TOGGLE_EVENT, onToggle)
    window.addEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)

    return () => {
      window.removeEventListener(THEME_SET_EVENT, onSet)
      window.removeEventListener(THEME_TOGGLE_EVENT, onToggle)
      window.removeEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
    }
  }, [])

  if (!visible) return null

  const next = nextTheme(theme)
  const ariaLabel =
    theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'

  return (
    <button
      type="button"
      className={`btn btn-ghost btn-sm btn-square shrink-0 ${className}`}
      aria-label={ariaLabel}
      title={`Theme: ${theme}. Click to switch to ${next}`}
      data-testid="theme-toggle-btn"
      onClick={() => dispatchSetTheme(next)}
    >
      {theme === 'dark' ? (
        <Sun className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Moon className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  )
}

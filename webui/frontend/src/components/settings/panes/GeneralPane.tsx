/** #856 slice B — GeneralPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useState } from 'react'
import {
  saveUserPrefs,
} from '../../../lib/userPrefs'
import {
  type ContextStrategy,
} from '../../../lib/contextCull'
import {
  initialNavbarThemeMode,
  initialTheme,
  dispatchSetNavbarThemeMode,
  dispatchSetTheme,
  THEME_NAVBAR_MODE_SET_EVENT,
  THEME_NAVBAR_SET_EVENT,
  THEME_SET_EVENT,
  type NavbarThemeToggleMode,
  type Theme,
} from '../../../lib/theme'
import {
  bubbleThemeSupportsStreaming,
  loadBubbleTheme,
} from '../../../lib/bubbleTheme'
import {
  STREAM_REPLIES_LABEL,
  STREAM_REPLIES_TOOLTIP,
  loadStreamReplies,
  saveStreamReplies,
} from '../../../lib/streamReplies'
import {
  loadNotificationsAutoExpire,
  saveNotificationsAutoExpire,
} from '../../../lib/settingsPrefs'
import { DemoSectionProfileControl } from './DemoSectionProfileControl'

export function GeneralPane({
  autoCompressPct,
  onAutoCompressPct,
  contextStrategy,
  onContextStrategy,
  cullTriggerPct,
  onCullTriggerPct,
  cullFractionPct,
  onCullFractionPct,
  demoRows,
}: {
  autoCompressPct: number
  onAutoCompressPct: (next: number) => void
  contextStrategy: ContextStrategy
  onContextStrategy: (next: ContextStrategy) => void
  cullTriggerPct: number
  onCullTriggerPct: (next: number) => void
  cullFractionPct: number
  onCullFractionPct: (next: number) => void
  /** #544: seats the showcase derives its sections from. */
  demoRows?: Array<{ id: string; kind?: string | null }>
}) {
  const [themePref, setThemePref] = useState<Theme>(initialTheme)
  const [navbarMode, setNavbarMode] = useState<NavbarThemeToggleMode>(initialNavbarThemeMode)
  const [streamReplies, setStreamReplies] = useState<boolean>(loadStreamReplies)
  const [notificationsAutoExpire, setNotificationsAutoExpire] = useState<boolean>(loadNotificationsAutoExpire)
  const bubbleTheme = loadBubbleTheme()
  const streamThemeOk = bubbleThemeSupportsStreaming(bubbleTheme)

  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Theme>).detail
      if (detail === 'light' || detail === 'dark' || detail === 'system') {
        setThemePref(detail)
      }
    }
    const onNavbarMode = (event: Event) => {
      const detail = (event as CustomEvent<NavbarThemeToggleMode>).detail
      if (detail === 'if_not_system' || detail === 'always' || detail === 'never') {
        setNavbarMode(detail)
      }
    }
    const onNavbarToggle = (event: Event) => {
      const detail = (event as CustomEvent<boolean>).detail
      setNavbarMode(detail ? 'always' : 'never')
    }
    window.addEventListener(THEME_SET_EVENT, onSet)
    window.addEventListener(THEME_NAVBAR_MODE_SET_EVENT, onNavbarMode)
    window.addEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
    return () => {
      window.removeEventListener(THEME_SET_EVENT, onSet)
      window.removeEventListener(THEME_NAVBAR_MODE_SET_EVENT, onNavbarMode)
      window.removeEventListener(THEME_NAVBAR_SET_EVENT, onNavbarToggle)
    }
  }, [])

  const handleThemeChange = (value: Theme) => {
    setThemePref(value)
    dispatchSetTheme(value)
    void saveUserPrefs({ theme: value })
  }

  const handleNavbarModeChange = (mode: NavbarThemeToggleMode) => {
    setNavbarMode(mode)
    dispatchSetNavbarThemeMode(mode)
    void saveUserPrefs({ theme_navbar_mode: mode })
  }

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-lg font-semibold">General</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Preferences for display and browser behavior.
        </p>
      </div>

      <section aria-labelledby="os-visuals-heading" className="space-y-4">
        <h5
          id="os-visuals-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Visuals
        </h5>

        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-theme-select" className="label py-0">
            <span className="label-text font-medium">Theme</span>
          </label>
          <select
            id="os-theme-select"
            aria-label="Theme"
            className="select select-bordered w-full"
            value={themePref}
            onChange={(e) => handleThemeChange(e.target.value as Theme)}
          >
            <option value="system">Use system (default)</option>
            <option value="light">Light</option>
            <option value="dark">Dark</option>
          </select>
          <p className="text-xs text-base-content/60">
            Choose light, dark, or follow your operating system appearance (prefers-color-scheme).
          </p>
        </div>

        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-navbar-theme-mode-select" className="label py-0">
            <span className="label-text font-medium">Light/dark toggle in top bar</span>
          </label>
          <select
            id="os-navbar-theme-mode-select"
            aria-label="Light/dark toggle in top bar"
            data-testid="os-navbar-theme-mode-select"
            className="select select-bordered w-full"
            value={navbarMode}
            onChange={(e) => handleNavbarModeChange(e.target.value as NavbarThemeToggleMode)}
          >
            <option value="if_not_system">If not system (default)</option>
            <option value="always">Always</option>
            <option value="never">Never</option>
          </select>
          <p className="text-xs text-base-content/60">
            Controls when the quick theme button appears in the top navigation bar.
          </p>
        </div>

        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={streamReplies}
              disabled={!streamThemeOk}
              onChange={(e) => {
                const next = saveStreamReplies(e.target.checked)
                setStreamReplies(next)
              }}
              aria-label={STREAM_REPLIES_LABEL}
              data-testid="stream-replies-toggle"
            />
            <span className="label-text">{STREAM_REPLIES_LABEL}</span>
          </label>
          <p className="text-xs text-base-content/60">
            {streamThemeOk
              ? STREAM_REPLIES_TOOLTIP
              : 'The current bubble theme does not support streaming.'}
          </p>
        </div>
      </section>

      <section aria-labelledby="os-notifications-heading" className="space-y-4">
        <h5
          id="os-notifications-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Notifications
        </h5>
        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={notificationsAutoExpire}
              onChange={(e) => {
                const next = saveNotificationsAutoExpire(e.target.checked)
                setNotificationsAutoExpire(next)
              }}
              aria-label="Auto-expire popup notifications"
              data-testid="notifications-auto-expire-toggle"
            />
            <span className="label-text">Auto-expire popup notifications</span>
          </label>
          <p className="text-xs text-base-content/60">
            Automatically dismiss transient popups after their class default duration:
            Actions (4s), Info (6s), Warnings (8s), Errors (12s). When disabled,
            all popups behave as sticky and stay until manually dismissed.
          </p>
        </div>
      </section>

      <section aria-labelledby="os-showcase-heading" className="space-y-3">
        <h5
          id="os-showcase-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Showcase
        </h5>
        {/* #544 / REQ-922: the demo section profile. Apply derives CLI / API /
            Remote / Fancy sections from the seats present right now and backs
            up the current layout; Remove restores it. Never first-run seeds. */}
        <DemoSectionProfileControl rows={demoRows ?? []} />
      </section>

      <section aria-labelledby="os-context-heading" className="space-y-4">
        <h5
          id="os-context-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Context
        </h5>
        <fieldset className="space-y-2" data-testid="context-strategy">
          <legend className="label-text font-medium">Strategy</legend>
          <label className="label cursor-pointer justify-start gap-3 py-0">
            <input
              type="radio"
              name="os-context-strategy"
              className="radio radio-sm"
              checked={contextStrategy === 'compress'}
              onChange={() => onContextStrategy('compress')}
              aria-label="Compress strategy"
              data-testid="context-strategy-compress"
            />
            <span className="label-text">Compress</span>
          </label>
          <label className="label cursor-pointer justify-start gap-3 py-0">
            <input
              type="radio"
              name="os-context-strategy"
              className="radio radio-sm"
              checked={contextStrategy === 'cull'}
              onChange={() => onContextStrategy('cull')}
              aria-label="Cull strategy"
              data-testid="context-strategy-cull"
            />
            <span className="label-text">Cull</span>
          </label>
          <p className="text-xs text-base-content/60">
            Compress summarises older turns. Cull drops the oldest slice so the
            recent suffix stays stable for input token caching. API agents only
            for cull; hover action becomes Start context from here.
          </p>
        </fieldset>
        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-auto-compress-pct" className="label py-0">
            <span className="label-text font-medium">Auto-compress at</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id="os-auto-compress-pct"
              type="number"
              min={1}
              max={99}
              className="input input-bordered w-24"
              value={autoCompressPct}
              onChange={(event) => onAutoCompressPct(Number(event.target.value))}
              aria-label="Auto-compress at percent"
              data-testid="auto-compress-pct"
            />
            <span className="text-sm text-base-content/70">%</span>
          </div>
          <p className="text-xs text-base-content/60">
            Compact older turns before a send when estimated tokens reach this
            percent of the model&apos;s known context length (1–99, default 80).
            CLI and API use the same value. If the max is unknown, auto-compress
            is skipped; Compact and Compress to here still work.
          </p>
        </div>
        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-cull-trigger-pct" className="label py-0">
            <span className="label-text font-medium">Cull trigger</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id="os-cull-trigger-pct"
              type="number"
              min={1}
              max={99}
              className="input input-bordered w-24"
              value={cullTriggerPct}
              onChange={(event) => onCullTriggerPct(Number(event.target.value))}
              aria-label="Cull trigger percent"
              data-testid="cull-trigger-pct"
            />
            <span className="text-sm text-base-content/70">%</span>
          </div>
          <p className="text-xs text-base-content/60">
            Auto-cull when estimated tokens reach this percent of a known max
            (1–99, default 90). Separate from compress. Unknown max skips auto.
          </p>
        </div>
        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-cull-fraction-pct" className="label py-0">
            <span className="label-text font-medium">Cull fraction</span>
          </label>
          <div className="flex items-center gap-2">
            <input
              id="os-cull-fraction-pct"
              type="number"
              min={1}
              max={99}
              className="input input-bordered w-24"
              value={cullFractionPct}
              onChange={(event) => onCullFractionPct(Number(event.target.value))}
              aria-label="Cull fraction percent"
              data-testid="cull-fraction-pct"
            />
            <span className="text-sm text-base-content/70">%</span>
          </div>
          <p className="text-xs text-base-content/60">
            Oldest slice dropped on auto-cull (1–99, default 50). Recent turns
            stay in the prompt for caching.
          </p>
        </div>
      </section>
    </div>
  )
}

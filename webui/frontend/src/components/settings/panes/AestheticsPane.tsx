/** #856 slice B — AestheticsPane (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useState } from 'react'
import {
  saveUserPrefs,
} from '../../../lib/userPrefs'
import {
  BUBBLE_THEME_LABELS,
  BUBBLE_THEMES,
  loadBubbleTheme,
  saveBubbleTheme,
  type BubbleTheme,
  applyBubbleThemeToAll,
  overriddenBubbleThemeCount,
} from '../../../lib/bubbleTheme'
import {
  ACTION_ROW_LABELS_CHANGED_EVENT,
  loadActionRowLabels,
  saveActionRowLabels,
} from '../../../lib/actionRowLabels'
import {
  NAVBAR_PICKER_PREFS_CHANGED_EVENT,
  loadNavbarPickerPrefs,
  saveHideUnsupportedAgentPicker,
  saveHideUnsupportedSessionPicker,
  type NavbarPickerPrefs,
} from '../../../lib/navbarPickerPrefs'
import {
  FONT_FAMILIES,
  FONT_FAMILY_CHANGED_EVENT,
  FONT_FAMILY_LABELS,
  loadCustomFontFamily,
  loadFontFamily,
  saveCustomFontFamily,
  saveFontFamily,
  type FontFamilyId,
} from '../../../lib/fontFamily'
import {
  saveAvatarMotionPreference,
  useAvatarMotionPreference,
} from '../../../lib/motionPreference'
import { ViewportActionsVisibilityControl } from './ViewportActionsVisibilityControl'
import { ViewportComposerAffordancesControl } from './ComposerAffordancesControl'

export function AestheticsPane() {
  const [bubbleTheme, setBubbleThemePref] = useState<BubbleTheme>(loadBubbleTheme)
  const [labels, setLabels] = useState<boolean>(loadActionRowLabels)
  // #1202: unmount an unsupported navbar Agent / Session selector instead of
  // leaving it greyed — two independent operator toggles, default off.
  const [navbarPrefs, setNavbarPrefs] = useState<NavbarPickerPrefs>(loadNavbarPickerPrefs)
  // #676: Apply-to-all enablement reads the live override map.
  const [overrideCount, setOverrideCount] = useState(() =>
    overriddenBubbleThemeCount(loadBubbleTheme()),
  )
  // #1227: interface font family (root `--os-font-family`).
  const [fontFamily, setFontFamilyPref] = useState<FontFamilyId>(loadFontFamily)
  const [customFont, setCustomFont] = useState<string>(loadCustomFontFamily)
  // #1244: opt avatar motion back in when the host broadcasts reduced motion.
  const avatarMotion = useAvatarMotionPreference()

  useEffect(() => {
    const onFontFamilyChanged = () => {
      setFontFamilyPref(loadFontFamily())
      setCustomFont(loadCustomFontFamily())
    }
    window.addEventListener(FONT_FAMILY_CHANGED_EVENT, onFontFamilyChanged)
    window.addEventListener('storage', onFontFamilyChanged)
    return () => {
      window.removeEventListener(FONT_FAMILY_CHANGED_EVENT, onFontFamilyChanged)
      window.removeEventListener('storage', onFontFamilyChanged)
    }
  }, [])

  useEffect(() => {
    const onLabelsChanged = () => setLabels(loadActionRowLabels())
    window.addEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, onLabelsChanged)
    window.addEventListener('storage', onLabelsChanged)
    return () => {
      window.removeEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, onLabelsChanged)
      window.removeEventListener('storage', onLabelsChanged)
    }
  }, [])

  useEffect(() => {
    const onNavbarPrefsChanged = () => setNavbarPrefs(loadNavbarPickerPrefs())
    window.addEventListener(NAVBAR_PICKER_PREFS_CHANGED_EVENT, onNavbarPrefsChanged)
    window.addEventListener('storage', onNavbarPrefsChanged)
    return () => {
      window.removeEventListener(NAVBAR_PICKER_PREFS_CHANGED_EVENT, onNavbarPrefsChanged)
      window.removeEventListener('storage', onNavbarPrefsChanged)
    }
  }, [])

  const handleBubbleTheme = (next: string) => {
    const saved = saveBubbleTheme(next)
    setBubbleThemePref(saved)
    setOverrideCount(overriddenBubbleThemeCount(saved))
    void saveUserPrefs({ bubble_theme: saved })
  }

  // #1227: apply locally for an instant switch, then sync via the values bag.
  const handleFontFamily = (next: string) => {
    const saved = saveFontFamily(next)
    setFontFamilyPref(saved)
    setCustomFont(loadCustomFontFamily())
    void saveUserPrefs({
      values: { font_family: saved, font_family_custom: loadCustomFontFamily() },
    })
  }

  // #1227: the custom preset edits its own stack; sanitised in fontFamily.ts.
  const handleCustomFont = (next: string) => {
    const saved = saveCustomFontFamily(next)
    setFontFamilyPref(saved)
    setCustomFont(next)
    void saveUserPrefs({
      values: { font_family: saved, font_family_custom: next.trim() },
    })
  }

  // #676: bring every overridden agent onto the selected default.
  const handleApplyToAll = () => {
    applyBubbleThemeToAll(bubbleTheme)
    setOverrideCount(0)
  }

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-lg font-semibold">Aesthetics</h4>
        <p className="mt-1 text-sm text-base-content/70">
          Chat presentation: bubble theme and message action buttons.
        </p>
      </div>

      <section aria-labelledby="os-aesthetics-font-heading" className="space-y-4">
        <h5
          id="os-aesthetics-font-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Typography
        </h5>

        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-font-family-select" className="label py-0">
            <span className="label-text font-medium">Font family</span>
          </label>
          <select
            id="os-font-family-select"
            aria-label="Font family"
            className="select select-bordered w-full"
            value={fontFamily}
            onChange={(e) => handleFontFamily(e.target.value)}
            data-testid="aesthetics-font-family"
          >
            {FONT_FAMILIES.map((id) => (
              <option key={id} value={id}>
                {FONT_FAMILY_LABELS[id]}
              </option>
            ))}
          </select>
          <p className="text-xs text-base-content/60">
            Interface typography. Default follows your host font (Omarchy uses
            JetBrains Mono Nerd Font); Custom takes any CSS font-family stack.
          </p>
        </div>

        {fontFamily === 'custom' && (
          <div className="form-control w-full max-w-md space-y-1">
            <label htmlFor="os-font-family-custom" className="label py-0">
              <span className="label-text font-medium">Custom font stack</span>
            </label>
            <input
              id="os-font-family-custom"
              type="text"
              className="input input-bordered w-full font-mono text-sm"
              aria-label="Custom font stack"
              placeholder="'Fira Code', ui-monospace, monospace"
              value={customFont}
              onChange={(e) => handleCustomFont(e.target.value)}
              data-testid="aesthetics-font-family-custom"
            />
            <p className="text-xs text-base-content/60">
              Comma-separated CSS font-family list. Invalid separators are
              stripped before it is applied.
            </p>
          </div>
        )}
      </section>

      <section aria-labelledby="os-aesthetics-bubble-heading" className="space-y-4">
        <h5
          id="os-aesthetics-bubble-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Bubbles
        </h5>

        <div className="form-control w-full max-w-xs space-y-1">
          <label htmlFor="os-bubble-theme-select" className="label py-0">
            <span className="label-text font-medium">Bubble theme</span>
          </label>
          <select
            id="os-bubble-theme-select"
            aria-label="Bubble theme"
            className="select select-bordered w-full"
            value={bubbleTheme}
            onChange={(e) => handleBubbleTheme(e.target.value)}
            data-testid="aesthetics-bubble-theme"
          >
            {BUBBLE_THEMES.map((id) => (
              <option key={id} value={id}>
                {BUBBLE_THEME_LABELS[id]}
              </option>
            ))}
          </select>
          <p className="text-xs text-base-content/60">
            How chat messages render. Also settable from the chat right-click menu.
          </p>
        </div>

        {/* #676: enabled only when some agent overrides the default with a
            different theme; clicking brings every agent onto this default. */}
        <div className="space-y-1">
          <button
            type="button"
            className="btn btn-sm btn-outline"
            data-testid="aesthetics-apply-all"
            disabled={overrideCount === 0}
            onClick={handleApplyToAll}
          >
            Apply to all{overrideCount > 0 ? ` (${overrideCount} overridden)` : ''}
          </button>
          <p className="text-xs text-base-content/60" data-testid="aesthetics-apply-all-hint">
            {overrideCount === 0
              ? 'Every agent already follows the default.'
              : `${overrideCount} agent${overrideCount === 1 ? '' : 's'} use a different theme — applying brings them onto the default.`}
          </p>
        </div>
      </section>

      <section aria-labelledby="os-aesthetics-labels-heading" className="space-y-4">
        <h5
          id="os-aesthetics-labels-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Message actions
        </h5>

        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={labels}
              onChange={(e) => {
                setLabels(saveActionRowLabels(e.target.checked))
              }}
              aria-label="Action-row button labels"
              data-testid="action-row-labels-toggle"
            />
            <span className="label-text">Action-row button labels</span>
          </label>
          <p className="text-xs text-base-content/60">
            Show text on the message action buttons (Edit, Copy, Read aloud,
            Retry). Off renders icon-only; every button keeps its tooltip and
            accessible name.
          </p>
        </div>
      </section>

      <section aria-labelledby="os-aesthetics-motion-heading" className="space-y-4">
        <h5
          id="os-aesthetics-motion-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Motion
        </h5>
        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={avatarMotion === 'always'}
              onChange={(e) =>
                saveAvatarMotionPreference(e.target.checked ? 'always' : 'system')
              }
              aria-label="Animate avatars"
              data-testid="avatar-motion-toggle"
            />
            <span className="label-text">Animate avatars</span>
          </label>
          <p className="text-xs text-base-content/60">
            Keep avatar animations running even when your system asks for
            reduced motion. Off respects the system setting.
          </p>
        </div>
      </section>

      <section aria-labelledby="os-aesthetics-navbar-heading" className="space-y-4">
        <h5
          id="os-aesthetics-navbar-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Navbar pickers
        </h5>
        <p className="text-xs text-base-content/60">
          An Agent / Session selector the active provider cannot support stays
          visible but greyed by default. Turn a toggle on to unmount the
          unsupported control and reclaim navbar space.
        </p>
        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={navbarPrefs.hideUnsupportedAgentPicker}
              onChange={(e) =>
                setNavbarPrefs(saveHideUnsupportedAgentPicker(e.target.checked))
              }
              aria-label="Hide unsupported Agent selector"
              data-testid="hide-unsupported-agent-picker-toggle"
            />
            <span className="label-text">Hide unsupported Agent selector</span>
          </label>
        </div>
        <div className="form-control">
          <label className="label cursor-pointer justify-start gap-4">
            <input
              type="checkbox"
              className="toggle"
              checked={navbarPrefs.hideUnsupportedSessionPicker}
              onChange={(e) =>
                setNavbarPrefs(saveHideUnsupportedSessionPicker(e.target.checked))
              }
              aria-label="Hide unsupported Session selector"
              data-testid="hide-unsupported-session-picker-toggle"
            />
            <span className="label-text">Hide unsupported Session selector</span>
          </label>
        </div>
      </section>

      <section aria-labelledby="os-aesthetics-viewport-heading" className="space-y-4">
        <h5
          id="os-aesthetics-viewport-heading"
          className="text-base font-semibold border-b border-base-200 pb-1"
        >
          Responsive & Viewport (Mobile / Tablet / Desktop)
        </h5>
        <p className="text-xs text-base-content/60">
          Configure interface visibility per device tier (mobile phones, tablets, and desktop displays).
        </p>

        {/* #833: per-viewport-tier visibility — touch tiers default to
            always-visible, desktop to hover-reveal. */}
        <ViewportActionsVisibilityControl />

        {/* #1215 / #1219: per-tier visibility of the provider/model routing
            picker in the message input. */}
        <ViewportComposerAffordancesControl />
      </section>
    </div>
  )
}

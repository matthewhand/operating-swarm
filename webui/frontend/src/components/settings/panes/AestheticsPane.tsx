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
import { ViewportActionsVisibilityControl } from './ViewportActionsVisibilityControl'

export function AestheticsPane() {
  const [bubbleTheme, setBubbleThemePref] = useState<BubbleTheme>(loadBubbleTheme)
  const [labels, setLabels] = useState<boolean>(loadActionRowLabels)
  // #676: Apply-to-all enablement reads the live override map.
  const [overrideCount, setOverrideCount] = useState(() =>
    overriddenBubbleThemeCount(loadBubbleTheme()),
  )

  useEffect(() => {
    const onLabelsChanged = () => setLabels(loadActionRowLabels())
    window.addEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, onLabelsChanged)
    window.addEventListener('storage', onLabelsChanged)
    return () => {
      window.removeEventListener(ACTION_ROW_LABELS_CHANGED_EVENT, onLabelsChanged)
      window.removeEventListener('storage', onLabelsChanged)
    }
  }, [])

  const handleBubbleTheme = (next: string) => {
    const saved = saveBubbleTheme(next)
    setBubbleThemePref(saved)
    setOverrideCount(overriddenBubbleThemeCount(saved))
    void saveUserPrefs({ bubble_theme: saved })
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

        {/* #833: per-viewport-tier visibility — touch tiers default to
            always-visible, desktop to hover-reveal. */}
        <ViewportActionsVisibilityControl />
      </section>
    </div>
  )
}

/**
 * #1215 / #1219 / #1220 — the settings controls for the composer affordances.
 *
 * ViewportComposerAffordancesControl (#1219 + #1215): a #833-style tier
 * table for the composer's provider/model routing picker. Mobile ships
 * HIDDEN — on a phone the picker eats the composer (#1219); tablet and
 * desktop keep #878's visible default. Every cell is an explicit override
 * (#1215): the shipped default is only what shows before the user chooses.
 *
 * RewriteEnabledControl (#1220): a single toggle for the "Rewrite prompt
 * with AI" action. Default OFF — enabling it is a deliberate opt-in to
 * auxiliary LLM inference per rewrite. Not tiered: the cost concern is
 * viewport-independent.
 *
 * Lives next to the #833 action-row control in Aesthetics → Viewport so
 * all per-tier visibility rules share one documented home.
 */
import { useEffect, useState } from 'react'
import {
  COMPOSER_SHOW_PROVIDER_TIERS_EVENT,
  loadRewriteEnabled,
  loadShowProviderTiers,
  saveRewriteEnabled,
  saveShowProviderTiers,
} from '../../../lib/composerAffordances'
import { type ResponsivePref, type ViewportTier } from '../../../lib/responsivePrefs'

const TIERS: ReadonlyArray<{ id: ViewportTier; icon: string; hint: string }> = [
  { id: 'mobile', icon: '📱', hint: 'Hidden by default (#1219) — the picker eats a phone composer' },
  { id: 'tablet', icon: '📟', hint: 'Visible by default (legacy #878 behavior)' },
  { id: 'desktop', icon: '🖥️', hint: 'Visible by default (legacy #878 behavior)' },
]

function useShowProviderTiers() {
  const [pref, setPref] = useState(() => loadShowProviderTiers())
  useEffect(() => {
    const sync = () => setPref(loadShowProviderTiers())
    window.addEventListener(COMPOSER_SHOW_PROVIDER_TIERS_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(COMPOSER_SHOW_PROVIDER_TIERS_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])
  return [pref, setPref] as const
}

export function ViewportComposerAffordancesControl() {
  const [pref, setPref] = useShowProviderTiers()

  return (
    <div className="space-y-2" data-testid="viewport-composer-control">
      <p className="text-sm font-medium">Composer provider dropdown per device</p>
      <div className="overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th className="w-1/2">Show provider/model picker in message input</th>
              {TIERS.map((tier) => (
                <th key={tier.id} className="text-center">
                  <span aria-hidden="true">{tier.icon}</span>{' '}
                  <span className="capitalize">{tier.id}</span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="text-xs text-base-content/60">
                Provider &amp; model routing picker
              </td>
              {TIERS.map((tier) => (
                <td key={tier.id} className="text-center">
                  <input
                    type="checkbox"
                    className="toggle toggle-sm"
                    checked={pref[tier.id]}
                    title={tier.hint}
                    aria-label={`Show provider dropdown in message input on ${tier.id}`}
                    data-testid={`composer-provider-${tier.id}`}
                    onChange={(e) => {
                      const next: ResponsivePref<boolean> = { ...pref, [tier.id]: e.target.checked }
                      setPref(saveShowProviderTiers(next))
                    }}
                  />
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-xs text-base-content/60">
        Mobile ships hidden (#1219) — flip it on deliberately if you want provider
        routing on a phone. Changes apply immediately, no reload.
      </p>
    </div>
  )
}

export function RewriteEnabledControl() {
  const [enabled, setEnabled] = useState(() => loadRewriteEnabled())
  useEffect(() => {
    const sync = () => setEnabled(loadRewriteEnabled())
    window.addEventListener('swarm:set-composer-rewrite-enabled', sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener('swarm:set-composer-rewrite-enabled', sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  return (
    <div className="space-y-2" data-testid="rewrite-enabled-control">
      <div className="form-control">
        <label className="label cursor-pointer justify-start gap-4">
          <input
            type="checkbox"
            className="toggle toggle-sm"
            checked={enabled}
            aria-label="Enable AI prompt rewrite in the composer"
            data-testid="rewrite-enabled-toggle"
            onChange={(e) => setEnabled(saveRewriteEnabled(e.target.checked))}
          />
          <span className="label-text">Rewrite prompt with AI (+ menu)</span>
        </label>
        <p className="text-xs text-base-content/60">
          Off by default (#1220): each rewrite sends your draft to the configured
          LLM as auxiliary inference. Enabling adds the “Rewrite prompt with AI”
          item to the composer's + menu.
        </p>
      </div>
    </div>
  )
}

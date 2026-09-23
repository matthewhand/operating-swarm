/** #856 slice B — ViewportActionsVisibilityControl (moved verbatim from SettingsSheet.tsx). */
import { useEffect, useState } from 'react'
import {
  ACTIONS_PREFS_CHANGED_EVENT,
  loadActionsAlwaysVisible,
  saveActionsAlwaysVisible,
  type ViewportTier,
} from '../../../lib/responsivePrefs'

export function ViewportActionsVisibilityControl() {
  const [pref, setPref] = useState(() => loadActionsAlwaysVisible())
  useEffect(() => {
    const sync = () => setPref(loadActionsAlwaysVisible())
    window.addEventListener(ACTIONS_PREFS_CHANGED_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(ACTIONS_PREFS_CHANGED_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  const tiers: ReadonlyArray<{ id: ViewportTier; icon: string; hint: string }> = [
    { id: 'mobile', icon: '📱', hint: 'Always visible (no hover on touch)' },
    { id: 'tablet', icon: '📟', hint: 'Always visible (no hover on touch)' },
    { id: 'desktop', icon: '🖥️', hint: 'Hidden until hover (clean view)' },
  ]

  return (
    <div className="space-y-2" data-testid="viewport-actions-control">
      <p className="text-sm font-medium">Action-row visibility per device</p>
      <div className="overflow-x-auto">
        <table className="table table-sm">
          <thead>
            <tr>
              <th className="w-1/2">Always show buttons</th>
              {tiers.map((tier) => (
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
                Message actions (Edit, Reply, Copy, Retry)
              </td>
              {tiers.map((tier) => (
                <td key={tier.id} className="text-center">
                  <input
                    type="checkbox"
                    className="toggle toggle-sm"
                    checked={pref[tier.id]}
                    title={tier.hint}
                    aria-label={`Always show message actions on ${tier.id}`}
                    data-testid={`viewport-actions-${tier.id}`}
                    onChange={(e) => {
                      setPref(saveActionsAlwaysVisible({ ...pref, [tier.id]: e.target.checked }))
                    }}
                  />
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
      <p className="text-xs text-base-content/60">
        Touch devices have no hover, so actions ship always-visible there;
        desktop keeps hover-reveal. Changes apply immediately.
      </p>
    </div>
  )
}

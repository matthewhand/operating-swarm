/**
 * #1700 (3) / #1703 — the first-run chat tip.
 *
 * One component for both tips on purpose (see `lib/vanillaTips.ts`): two
 * renderers for two signals is how the same condition ends up explained twice.
 * The *content* comes entirely from `firstVanillaTip`; this file renders it and
 * nothing else decides anything.
 *
 * Not a modal, and not above the composer: it sits at the top of the transcript
 * (`ChatTranscriptShell`) so sending is never blocked and the conversation
 * stays the focus. `role="status"` (not `alert`) so a screen reader announces
 * it without interrupting.
 *
 * The CTA is a real `<a href>` to a `/chat?settings=…` deep link, which
 * `lib/settingsLinks.ts` intercepts to open the sheet in-app — so it is a
 * navigable link (middle-click, copy address, keyboard) *and* a one-click
 * in-place fix. A `<button onClick>` would have been the dead end #1700
 * complained about.
 */

import { Settings, X } from 'lucide-react'
import { Alert } from './DaisyUI'
import type { VanillaTip } from '../lib/vanillaTips'

export interface VanillaSetupTipProps {
  tip: VanillaTip
  onDismiss: () => void
}

export function VanillaSetupTip({ tip, onDismiss }: VanillaSetupTipProps) {
  return (
    <div className="os-vanilla-tip" data-testid="vanilla-setup-tip" data-tip-id={tip.id}>
      <Alert
        type="info"
        className="os-vanilla-tip__alert"
        role="status"
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="os-vanilla-tip__title font-medium">{tip.title}</p>
            <p className="os-vanilla-tip__body mt-0.5 text-sm text-base-content/80">
              {tip.body}
            </p>
            <a
              href={tip.cta.href}
              className="btn btn-sm mt-2 gap-1.5 os-vanilla-tip__cta"
              data-testid="vanilla-tip-cta"
            >
              <Settings className="h-3.5 w-3.5" aria-hidden="true" />
              {tip.cta.label}
            </a>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square shrink-0"
            aria-label={`Dismiss: ${tip.title}`}
            data-testid="vanilla-tip-dismiss"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </Alert>
    </div>
  )
}

export default VanillaSetupTip

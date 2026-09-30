import { PlugZap, X } from 'lucide-react'
import { Alert } from './DaisyUI'
import { hostCliTipBody, hostCliTipTitle } from '../lib/hostCliTip'
import { openSettingsSheet } from './settings/kernel'

export interface HostCliTipProps {
  /** Detected catalog CLI name, e.g. `opencode` (from `GET /v1/cli-agents/`). */
  cliName: string
  /** X button — hides for this session only. */
  onDismiss: () => void
  /** "Don't show this again" — hides and persists across reloads. */
  onNeverShowAgain: () => void
}

/**
 * #1703 — top-of-chat tip for a host CLI found on PATH but not yet wired up.
 * Not a modal: Chat stays mounted, the composer keeps focus, and sending is
 * never blocked. The CTA deep-links to Settings → CLI agents.
 */
export function HostCliTip({ cliName, onDismiss, onNeverShowAgain }: HostCliTipProps) {
  return (
    <div className="os-host-cli-tip" data-testid="host-cli-tip" data-cli={cliName}>
      <Alert type="info" className="os-host-cli-tip__alert" role="status">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium" data-testid="host-cli-tip-title">
              {hostCliTipTitle(cliName)}
            </p>
            <p className="mt-0.5 text-sm text-base-content/80" data-testid="host-cli-tip-body">
              {hostCliTipBody(cliName)}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <button
                type="button"
                className="btn btn-sm gap-1.5"
                data-testid="host-cli-tip-add"
                onClick={() => openSettingsSheet({ section: 'cli-agents', addCliName: cliName })}
              >
                <PlugZap className="h-3.5 w-3.5" aria-hidden="true" />
                Add provider
              </button>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                data-testid="host-cli-tip-never"
                onClick={onNeverShowAgain}
              >
                Don&rsquo;t show this again
              </button>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square shrink-0"
            aria-label={`Dismiss ${hostCliTipTitle(cliName)}`}
            data-testid="host-cli-tip-dismiss"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </Alert>
    </div>
  )
}

export default HostCliTip

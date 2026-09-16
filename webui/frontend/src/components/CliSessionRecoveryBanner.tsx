import { History, RotateCcw, Trash2 } from 'lucide-react'
import { Alert } from './DaisyUI'
import { CLI_SESSION_RECOVERY_MESSAGE } from '../lib/cliSessionRecovery'

export interface CliSessionRecoveryBannerProps {
  onStartFresh: () => void
  onRetry: () => void
  onClearHistory: () => void
}

/** Inline recovery card when the last turn is a terminal CLI/config failure (#274). */
export function CliSessionRecoveryBanner({
  onStartFresh,
  onRetry,
  onClearHistory,
}: CliSessionRecoveryBannerProps) {
  return (
    <div className="os-cli-session-recovery my-2" data-testid="cli-session-recovery">
      <Alert type="warning" className="os-cli-session-recovery__alert" role="status">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <p className="font-medium">{CLI_SESSION_RECOVERY_MESSAGE}</p>
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              className="btn btn-sm gap-1.5"
              data-testid="cli-session-recovery-fresh"
              onClick={onStartFresh}
            >
              <History className="h-3.5 w-3.5" aria-hidden="true" />
              Start Fresh Session
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost gap-1.5"
              data-testid="cli-session-recovery-retry"
              onClick={onRetry}
            >
              <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
              Retry
            </button>
            <button
              type="button"
              className="btn btn-sm btn-ghost gap-1.5"
              data-testid="cli-session-recovery-clear"
              onClick={onClearHistory}
            >
              <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
              Clear History
            </button>
          </div>
        </div>
      </Alert>
    </div>
  )
}

export default CliSessionRecoveryBanner

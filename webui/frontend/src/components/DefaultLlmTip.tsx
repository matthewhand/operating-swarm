import { Settings, X } from 'lucide-react'
import { Alert } from './DaisyUI'
import { DEFAULT_LLM_TIP_BODY, DEFAULT_LLM_TIP_TITLE } from '../lib/defaultLlmTip'
import { openSettingsSheet } from './SettingsSheet'

export interface DefaultLlmTipProps {
  onDismiss: () => void
}

/** Chat-pane tip for API seats on an unconfigured default LLM (REQ-853 / #207). Not a modal — Chat stays mounted and sending is never blocked. */
export function DefaultLlmTip({ onDismiss }: DefaultLlmTipProps) {
  return (
    <div className="os-default-llm-tip" data-testid="default-llm-tip">
      <Alert type="warning" className="os-default-llm-tip__alert" role="status">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="font-medium">{DEFAULT_LLM_TIP_TITLE}</p>
            <p className="mt-0.5 text-sm text-base-content/80">{DEFAULT_LLM_TIP_BODY}</p>
            <button
              type="button"
              className="btn btn-sm mt-2 gap-1.5"
              data-testid="default-llm-tip-setup"
              onClick={() => openSettingsSheet({ section: 'llm-profiles' })}
            >
              <Settings className="h-3.5 w-3.5" aria-hidden="true" />
              Set up in Settings
            </button>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square shrink-0"
            aria-label="Dismiss default LLM tip"
            data-testid="default-llm-tip-dismiss"
            onClick={onDismiss}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </Alert>
    </div>
  )
}

export default DefaultLlmTip

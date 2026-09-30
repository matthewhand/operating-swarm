import { Bot, Users, X } from 'lucide-react'
import { useState } from 'react'
import { Alert } from './DaisyUI'
import {
  OPENAI_AGENTS_TIP_BODY,
  OPENAI_AGENTS_TIP_TITLE,
  TEAM_BLUEPRINT_TIP_BODY,
  TEAM_BLUEPRINT_TIP_TITLE,
  type BlueprintTipKind,
} from '../lib/blueprintTips'

export interface BlueprintTipProps {
  kind: BlueprintTipKind
  /** `neverShowAgain` is true only when the checkbox was checked. */
  onDismiss: (neverShowAgain: boolean) => void
}

/**
 * Inline chat-pane explainer for openai-agents / team blueprint seats (#1252).
 * Not a modal — Chat stays mounted. `onDismiss` receives the checkbox state;
 * the parent owns persistence.
 */
export function BlueprintTip({ kind, onDismiss }: BlueprintTipProps) {
  const [neverShowAgain, setNeverShowAgain] = useState(false)
  const isTeam = kind === 'team'
  const title = isTeam ? TEAM_BLUEPRINT_TIP_TITLE : OPENAI_AGENTS_TIP_TITLE
  const body = isTeam ? TEAM_BLUEPRINT_TIP_BODY : OPENAI_AGENTS_TIP_BODY
  const Icon = isTeam ? Users : Bot
  const testId = isTeam ? 'team-blueprint-tip' : 'openai-agents-tip'

  return (
    <div className="os-blueprint-tip" data-testid={testId} data-tip-kind={kind}>
      <Alert type="info" className="os-blueprint-tip__alert" role="status">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-2">
            <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            <div className="min-w-0">
              <p className="font-medium">{title}</p>
              <p className="mt-0.5 text-sm text-base-content/80">{body}</p>
              <label className="mt-2 flex cursor-pointer items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  className="checkbox checkbox-xs"
                  checked={neverShowAgain}
                  aria-label="Never show this again"
                  data-testid={`${testId}-never`}
                  onChange={(e) => setNeverShowAgain(e.target.checked)}
                />
                <span>Never show this again</span>
              </label>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-xs btn-square shrink-0"
            aria-label={`Dismiss ${title}`}
            data-testid={`${testId}-dismiss`}
            onClick={() => onDismiss(neverShowAgain)}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
      </Alert>
    </div>
  )
}

export default BlueprintTip

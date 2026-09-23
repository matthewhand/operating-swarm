import { X, Activity, MessageSquare, Wrench, Layers, ArrowDownLeft, ArrowUpRight } from 'lucide-react'
import { Modal } from './DaisyUI/Modal'
import { CONTEXT_METER_TOKENS, formatMeterLabel, formatTokenCount } from '../lib/chatMeter'
import {
  lastEventLabel,
  strategyLabel,
  type ContextLastEvent,
  type ContextStrategy,
} from '../lib/contextCull'

export interface TokenDiagnosticsModalProps {
  isOpen: boolean
  onClose: () => void
  agentName?: string
  conversationId?: string | null
  tokenCount: number
  contextMax?: number | null
  inputTokens?: number | null
  outputTokens?: number | null
  compactsCount?: number
  toolCallsCount?: number
  messageCount?: number
  userMessageCount?: number
  assistantMessageCount?: number
  estimatedCost?: string | null
  contextStrategy?: ContextStrategy
  lastContextEvent?: ContextLastEvent | null
}

export function TokenDiagnosticsModal({
  isOpen,
  onClose,
  agentName,
  conversationId,
  tokenCount,
  contextMax = null,
  inputTokens,
  outputTokens,
  compactsCount = 0,
  toolCallsCount = 0,
  messageCount = 0,
  userMessageCount = 0,
  assistantMessageCount = 0,
  estimatedCost = null,
  contextStrategy = 'compress',
  lastContextEvent = null,
}: TokenDiagnosticsModalProps) {
  const meterMax = contextMax != null && contextMax > 0 ? contextMax : CONTEXT_METER_TOKENS
  const tokenPct = Math.min(100, Math.round((Math.max(0, tokenCount) / meterMax) * 100))
  const usageLabel =
    contextMax != null && contextMax > 0
      ? `${formatMeterLabel(tokenCount, contextMax)} (${tokenPct}%)`
      : `${formatTokenCount(tokenCount)} tok (max unknown)`

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      placement="middle"
      aria-label="Session token diagnostics"
    >
      <div className="space-y-4" data-testid="token-diagnostics-modal">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-base-300 pb-3">
          <div className="flex items-center gap-2">
            <Activity className="h-5 w-5 text-primary" aria-hidden="true" />
            <h2 className="text-base font-semibold">Session Token Diagnostics</h2>
          </div>
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-circle"
            aria-label="Close diagnostics"
            onClick={onClose}
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>

        {/* Session Metadata */}
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/70">
          <div>
            Current Agent:{' '}
            <span className="font-medium text-base-content" data-testid="diag-current-agent">
              {agentName || '—'}
            </span>
          </div>
          <div>
            Session:{' '}
            <span className="font-mono text-base-content" data-testid="diag-session-id">
              {conversationId || '—'}
            </span>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-base-content/70">
          <div>
            Strategy:{' '}
            <span className="font-medium text-base-content" data-testid="diag-context-strategy">
              {strategyLabel(contextStrategy)}
            </span>
          </div>
          <div>
            Last context action:{' '}
            <span className="font-medium text-base-content" data-testid="diag-last-context-event">
              {lastEventLabel(lastContextEvent)}
              {lastContextEvent?.at ? ` · ${lastContextEvent.at}` : ''}
            </span>
          </div>
        </div>

        {/* Context Window Meter */}
        <div className="rounded-lg border border-base-300 bg-base-200/50 p-3 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-medium text-base-content">Context Window Usage</span>
            <span className="tabular-nums font-semibold text-base-content" data-testid="diag-context-usage">
              {usageLabel}
            </span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-base-300">
            <div
              className="h-full rounded-full bg-primary transition-all duration-300"
              style={{ width: `${Math.min(100, Math.max(tokenCount > 0 ? 2 : 0, tokenPct))}%` }}
              role="progressbar"
              aria-valuenow={tokenCount}
              aria-valuemin={0}
              aria-valuemax={meterMax}
              aria-label="Context usage bar"
            />
          </div>
        </div>

        {/* Diagnostics Breakdown Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
          {/* Input Tokens */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <ArrowDownLeft className="h-3.5 w-3.5 text-info shrink-0" aria-hidden="true" />
              <span>Input (Prompt)</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums" data-testid="diag-input-tokens">
                {inputTokens != null ? `${formatTokenCount(inputTokens)}` : '—'}
              </span>
              {inputTokens != null ? <span className="text-xs text-base-content/60 ml-1">tok</span> : null}
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">
              {userMessageCount} user {userMessageCount === 1 ? 'msg' : 'msgs'}
            </div>
          </div>

          {/* Output Tokens */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <ArrowUpRight className="h-3.5 w-3.5 text-success shrink-0" aria-hidden="true" />
              <span>Output (Completion)</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums" data-testid="diag-output-tokens">
                {outputTokens != null ? `${formatTokenCount(outputTokens)}` : '—'}
              </span>
              {outputTokens != null ? <span className="text-xs text-base-content/60 ml-1">tok</span> : null}
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">
              {assistantMessageCount} assistant {assistantMessageCount === 1 ? 'msg' : 'msgs'}
            </div>
          </div>

          {/* Compacts / Summaries */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <Layers className="h-3.5 w-3.5 text-secondary shrink-0" aria-hidden="true" />
              <span>Compacts</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums" data-testid="diag-compacts-count">
                {compactsCount}
              </span>
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">
              {compactsCount === 1 ? '1 summary' : `${compactsCount} summaries`}
            </div>
          </div>

          {/* Tool Calls */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <Wrench className="h-3.5 w-3.5 text-warning shrink-0" aria-hidden="true" />
              <span>Tool Calls</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums" data-testid="diag-tool-calls">
                {toolCallsCount}
              </span>
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">
              {toolCallsCount === 1 ? '1 call' : `${toolCallsCount} calls`}
            </div>
          </div>

          {/* Message Count */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <MessageSquare className="h-3.5 w-3.5 text-accent shrink-0" aria-hidden="true" />
              <span>Messages</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums" data-testid="diag-message-count">
                {messageCount}
              </span>
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">Total turns in session</div>
          </div>

          {/* Estimated Cost */}
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 flex flex-col justify-between">
            <div className="flex items-center gap-1.5 text-xs text-base-content/70">
              <Activity className="h-3.5 w-3.5 text-base-content/50 shrink-0" aria-hidden="true" />
              <span>Cost</span>
            </div>
            <div className="mt-2">
              <span className="text-lg font-bold tabular-nums text-base-content/60" data-testid="diag-estimated-cost">
                {estimatedCost || '—'}
              </span>
            </div>
            <div className="text-[11px] text-base-content/50 mt-0.5">Not tracked</div>
          </div>
        </div>

        {/* Privacy Note */}
        <p className="text-[11px] text-base-content/50 leading-normal">
          Breakdown metrics are honest counts scoped to this conversation session. Prompt text is not shown to prevent accidental exposure of secrets or personal data.
        </p>

        {/* Actions */}
        <div className="flex justify-end pt-2 border-t border-base-300">
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </Modal>
  )
}

import { RotateCcw } from 'lucide-react'

/**
 * EXPERIMENTAL: per-message actions for assistant chat bubbles.
 *
 * Retry re-sends the preceding user message through the normal send path.
 * Copy lives in MessageRowActions (hover-only); this
 * footer combines into the horizontal reactions line (#70). Toggle off with:
 *   localStorage.setItem('swarm_experimental_chat_message_actions', 'off')
 *
 * React / reply / more are not mounted here — hide-until-ready, not stubs.
 */

export function ChatMessageActions({
  text: _text,
  onRetry,
  className,
}: {
  text: string
  onRetry?: () => void
  className?: string
}) {
  if (!onRetry) return null

  return (
    <div className={className ?? 'inline-flex items-center'}>
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1"
        onClick={onRetry}
        aria-label="Resend the previous message"
      >
        <RotateCcw className="h-3 w-3" aria-hidden="true" />
        Retry
      </button>
    </div>
  )
}

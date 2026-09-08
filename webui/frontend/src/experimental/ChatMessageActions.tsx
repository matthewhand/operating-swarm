import { RotateCcw } from 'lucide-react'

/**
 * EXPERIMENTAL: per-message actions for assistant chat bubbles.
 *
 * Retry re-sends the preceding user message through the normal send path.
 * Copy intentionally lives only in MessageRowActions (hover-only); this
 * footer must not add a second always-visible Copy (#70). Toggle off with:
 *   localStorage.setItem('swarm_experimental_chat_message_actions', 'off')
 *
 * React / reply / more are not mounted here — hide-until-ready, not stubs.
 */

export function ChatMessageActions({
  text: _text,
  onRetry,
}: {
  text: string
  onRetry?: () => void
}) {
  return (
    <div className="chat-footer mt-0.5 flex items-center gap-1 opacity-70 transition-opacity hover:opacity-100">
      {onRetry && (
        <button
          type="button"
          className="btn btn-ghost btn-xs gap-1"
          onClick={onRetry}
          aria-label="Resend the previous message"
        >
          <RotateCcw className="h-3 w-3" aria-hidden="true" />
          Retry
        </button>
      )}
    </div>
  )
}

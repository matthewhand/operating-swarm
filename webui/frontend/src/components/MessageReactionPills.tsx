import type { MessageReaction } from '../lib/messageReactions'

/**
 * Aggregated emoji pills under a chat bubble (#1411 / #1241).
 *
 * Idle pills stay dim; the operator's own reaction stays bright.
 */
export default function MessageReactionPills({
  reactions,
  onToggle,
  alwaysVisible = false,
}: {
  reactions: MessageReaction[]
  onToggle?: (emoji: string) => void
  /** Reaction-only turns: the pill is the reply, so it stays visible at rest. */
  alwaysVisible?: boolean
}) {
  if (!reactions.length) return null
  return (
    <div
      data-testid="message-reactions-row"
      data-always-visible={alwaysVisible ? 'true' : undefined}
      className={
        alwaysVisible
          ? 'os-message-reactions os-message-reactions--turn flex flex-wrap items-center gap-1 opacity-100 pointer-events-auto'
          : 'os-message-reactions flex flex-wrap items-center gap-1 mt-1 opacity-100 pointer-events-auto md:opacity-0 md:pointer-events-none group-hover/osrow:md:opacity-100 group-hover/osrow:md:pointer-events-auto group-focus-within/osrow:md:opacity-100 group-focus-within/osrow:md:pointer-events-auto transition-opacity motion-reduce:transition-none'
      }
      aria-label="Message reactions"
    >
      {reactions.map((row) => (
        <button
          key={row.emoji}
          type="button"
          data-testid={`reaction-${row.emoji}`}
          data-user-reacted={row.userReacted ? 'true' : undefined}
          className={`os-reaction-pill badge badge-sm cursor-pointer select-none gap-1 py-2 px-2 text-xs transition-opacity motion-reduce:transition-none ${
            alwaysVisible || row.userReacted
              ? 'badge-primary opacity-100'
              : 'badge-ghost border-base-300 opacity-45 hover:opacity-100 focus-visible:opacity-100'
          }`}
          onClick={() => onToggle?.(row.emoji)}
          aria-label={`Reaction ${row.emoji} count ${row.count}`}
        >
          <span>{row.emoji}</span>
          {row.count > 1 && <span className="text-[10px] font-semibold">{row.count}</span>}
        </button>
      ))}
    </div>
  )
}

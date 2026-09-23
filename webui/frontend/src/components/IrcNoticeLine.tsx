import { formatBubbleTime } from '../lib/bubbleTheme'

export interface IrcNoticeLineProps {
  speaker: string
  text: string
  ts?: string
  rowKey: string
  /** Optional click action (rate-limit lines open the provider settings). */
  onClick?: () => void
}

/**
 * #782 — a not-message row (status notice, session message, rate-limit line)
 * rendered in the IRC theme's gutter grid.
 *
 * Deliberately mirrors the real message-row contract from ChatMessageBubble:
 * the `<speaker>` gutter (via the shared `chat[data-speaker]::before` rule at
 * the fixed gutter width), the draggable divider, the inline time cell
 * (`--:--` when unknown, per #774), then the line body. The transcript keeps
 * one visual language and the gutter column never breaks at notice rows.
 */
export function IrcNoticeLine({ speaker, text, ts, rowKey, onClick }: IrcNoticeLineProps) {
  const timeLabel = formatBubbleTime(ts) || '--:--'
  const timeEl = (
    <time className="os-bubble-time" dateTime={ts} data-testid="bubble-time">
      {timeLabel}
    </time>
  )
  return (
    <div
      className="chat chat-start os-irc-notice"
      data-speaker={speaker}
      data-ts={ts || undefined}
      data-message-theme="irc"
      data-timestamp-placement="inline"
      data-testid="irc-notice-line"
      key={rowKey}
      {...(onClick
        ? {
            role: 'button' as const,
            tabIndex: 0,
            onClick,
            onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault()
                onClick()
              }
            },
          }
        : {})}
    >
      <span
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize IRC name column"
        className="os-irc-gutter-divider"
        data-testid="irc-gutter-divider"
      />
      {timeEl ? (
        <span className="os-bubble-time-inline" data-testid="bubble-time-slot">
          {timeEl}
        </span>
      ) : null}
      <div className="chat-bubble os-irc-notice-bubble">
        <span className="os-irc-notice-text" data-testid="irc-notice-text" title={text}>
          {text}
        </span>
      </div>
    </div>
  )
}

export default IrcNoticeLine

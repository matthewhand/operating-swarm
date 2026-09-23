import { useState } from 'react'
import { renderSafeMarkdown } from '../lib/markdown'
import { QUOTE_CLAMP_LINES, quoteLineCount } from '../lib/replyQuote'

export interface QuotedReplyProps {
  /** The quoted text, `>` markers already stripped. */
  quote: string
}

/**
 * #565: a reply quote rendered as the first ~4 lines with a fade, plus a
 * keyboard-accessible expand toggle. Expansion state is local to this
 * component, which is mounted per message — expanding one reply does not
 * expand every quote in the transcript.
 *
 * The *sent* quote is untouched: this only changes what is drawn.
 */
export function QuotedReply({ quote }: QuotedReplyProps) {
  const [expanded, setExpanded] = useState(false)
  const lines = quoteLineCount(quote)
  const clampable = lines > QUOTE_CLAMP_LINES
  const clamped = clampable && !expanded

  return (
    <blockquote
      className={`os-quote${clamped ? ' os-quote--clamped' : ''}`}
      data-testid="bubble-quote"
      data-clamped={clamped ? 'true' : 'false'}
      data-quote-lines={String(lines)}
    >
      <div
        className="os-quote__body chat-md break-words [&_p]:my-0.5 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0"
        data-testid="bubble-quote-body"
        dangerouslySetInnerHTML={{ __html: renderSafeMarkdown(quote) }}
      />
      {clampable ? (
        <button
          type="button"
          className="os-quote__toggle"
          aria-expanded={expanded}
          data-testid="bubble-quote-toggle"
          onClick={() => setExpanded((current) => !current)}
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      ) : null}
    </blockquote>
  )
}

export default QuotedReply

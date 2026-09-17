/**
 * #565: a reply is *only* markdown — there is no `replyTo`/`quotedMessage`
 * metadata on a message anywhere in the model (verified: zero matches). The
 * outbound text is built as a leading blockquote followed by the new message:
 *
 *   > **Support**: the whole original message, every line prefixed
 *   >
 *   > …
 *
 *   the new message
 *
 * So a leading blockquote *is* the reply quote, and it is the only thing the
 * renderer can key off. This splitter recovers it so the bubble can clamp and
 * expand the quote without touching the bytes that go on the wire.
 */

/** `> ` / `>` / up to three spaces of indent, matching CommonMark blockquote. */
const QUOTE_LINE = /^ {0,3}>\s?/

export interface LeadingQuote {
  /** The quoted text with the `>` markers stripped. */
  quote: string
  /** Everything after the quote; blank separator lines are dropped. */
  body: string
}

/**
 * Split a message that *begins* with a blockquote into quote + remainder.
 *
 * Returns `null` when the message does not start with a blockquote, so an
 * ordinary message that merely contains a quote keeps rendering as markdown.
 */
export function splitLeadingQuote(text: string): LeadingQuote | null {
  if (!text) return null
  const lines = text.replace(/\r\n/g, '\n').split('\n')
  if (!QUOTE_LINE.test(lines[0])) return null

  let end = 0
  while (end < lines.length && QUOTE_LINE.test(lines[end])) end += 1

  const quoted = lines.slice(0, end).map((line) => line.replace(QUOTE_LINE, ''))
  // Trailing quote-blank lines are padding, not content.
  while (quoted.length && quoted[quoted.length - 1].trim() === '') quoted.pop()
  const quote = quoted.join('\n')
  if (!quote.trim()) return null

  const rest = lines.slice(end)
  while (rest.length && rest[0].trim() === '') rest.shift()

  return { quote, body: rest.join('\n') }
}

/** Number of rendered lines a quote will occupy. Used to decide on clamping. */
export function quoteLineCount(quote: string): number {
  return quote.replace(/\r\n/g, '\n').split('\n').length
}

/** How many lines of a reply quote stay visible before "Show more" (#565). */
export const QUOTE_CLAMP_LINES = 4

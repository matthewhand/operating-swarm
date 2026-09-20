/**
 * Message artifact stripping and thinking/reasoning block extraction (#REQ-thinking-reaction).
 *
 * 1. Strips provider-specific header artifacts such as Herdr's
 *    `| | summary of conversation |` (and pipe table headers).
 * 2. Extracts `| Thinking: ...` (Herdr style) and `<think>...</think>` (standard
 *    reasoning models) into a separate thinking payload, leaving the clean
 *    prose for the message bubble while allowing thinking to be displayed
 *    in a collapsible and toggled via the "Thinking" reaction button.
 */

export interface ParsedMessageArtifacts {
  /** Cleaned message body with provider artifacts and thinking block removed. */
  body: string
  /** Extracted thinking/reasoning text, if any. */
  thinking: string | null
  /** True if any artifact was stripped or thinking was extracted. */
  hasArtifacts: boolean
}

const HERDR_SUMMARY_HEADER_RE =
  /^\s*\|\s*\|\s*(?:summary\s+of\s+(?:the\s+)?conversation|conversation\s+summary|summary)\s*\|\s*$/i

const TABLE_SEPARATOR_RE = /^\s*\|[-:\s|]+\|\s*$/

/**
 * Strip provider-specific banners and header artifacts from message text.
 */
export function stripProviderArtifacts(text: string): string {
  if (!text) return ''

  const lines = text.split(/\r?\n/)
  const cleaned: string[] = []
  let inHeader = true

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i]
    if (inHeader) {
      if (HERDR_SUMMARY_HEADER_RE.test(line)) {
        // Skip header line and any immediately following table separator like |---|---|
        if (i + 1 < lines.length && TABLE_SEPARATOR_RE.test(lines[i + 1])) {
          i++
        }
        continue
      }
      if (!line.trim() && cleaned.length === 0) {
        continue
      }
      inHeader = false
    }
    cleaned.push(line)
  }

  return cleaned.join('\n').trim()
}

/**
 * Extract thinking / reasoning blocks (Herdr `| Thinking: ...` or `<think>...</think>`).
 */
export function extractThinkingBlock(rawText: string): ParsedMessageArtifacts {
  if (!rawText || !rawText.trim()) {
    return { body: rawText || '', thinking: null, hasArtifacts: false }
  }

  let text = stripProviderArtifacts(rawText)
  let thinking: string | null = null

  // 1. Check for standard <think>...</think> tags
  const thinkTagMatch = text.match(/<think>([\s\S]*?)<\/think>/i)
  if (thinkTagMatch) {
    thinking = thinkTagMatch[1].trim()
    text = text.replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
  }

  // 2. Check for Herdr pipe-style "| Thinking: ..." or leading "Thinking: ..."
  if (!thinking) {
    const lines = text.split(/\r?\n/)
    const thinkingLines: string[] = []
    const remainingLines: string[] = []
    let capturingThinking = false
    let isPipeThinking = false

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]
      if (!capturingThinking) {
        if (/^\s*\|\s*Thinking:\s*(.*)$/i.test(line)) {
          capturingThinking = true
          isPipeThinking = true
          const match = line.match(/^\s*\|\s*Thinking:\s*(.*)$/i)
          if (match && match[1].trim()) {
            thinkingLines.push(match[1].trim())
          }
          continue
        } else if (/^\s*Thinking:\s*(.*)$/i.test(line)) {
          capturingThinking = true
          isPipeThinking = false
          const match = line.match(/^\s*Thinking:\s*(.*)$/i)
          if (match && match[1].trim()) {
            thinkingLines.push(match[1].trim())
          }
          continue
        }
        remainingLines.push(line)
      } else {
        if (isPipeThinking) {
          if (/^\s*\|\s*(.*)$/.test(line)) {
            const match = line.match(/^\s*\|\s*(.*)$/)
            const content = match ? match[1].trim() : ''
            if (/^[-:\s|]+$/.test(content)) {
              capturingThinking = false
              continue
            }
            thinkingLines.push(content)
          } else if (!line.trim()) {
            capturingThinking = false
          } else {
            capturingThinking = false
            remainingLines.push(line)
          }
        } else {
          if (!line.trim()) {
            capturingThinking = false
          } else {
            thinkingLines.push(line.trim())
          }
        }
      }
    }

    if (thinkingLines.length > 0) {
      thinking = thinkingLines.join('\n').trim()
      text = remainingLines.join('\n').trim()
    }
  }

  return {
    body: text,
    thinking: thinking && thinking.length > 0 ? thinking : null,
    hasArtifacts: text !== rawText || thinking !== null,
  }
}

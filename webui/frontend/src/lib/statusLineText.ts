/**
 * #782 — notification/label rows must be bubble-theme aware.
 *
 * IRC lines are plain text (`<nick> message`); markdown chrome (bold, links,
 * headings, code spans) belongs to bubble themes, not the gutter. This helper
 * strips inline/block markdown down to the words and URLs and flattens the
 * result to one transcript-safe line, truncating long notices with an ellipsis
 * (full text stays on disk and in the title/tooltip).
 */

/** Upper bound for a status gutter line; long detail stays behind a tooltip. */
const MAX_STATUS_LINE_CHARS = 200

function truncateOneLine(text: string): string {
  const oneLine = text.replace(/\s+/g, ' ').trim()
  if (oneLine.length <= MAX_STATUS_LINE_CHARS) return oneLine
  return `${oneLine.slice(0, MAX_STATUS_LINE_CHARS).trimEnd()}…`
}

/** Markdown → plain one-line label, safe for a `<nick> message` gutter line. */
export function statusLineLabel(markdown: string): string {
  const raw = markdown ?? ''
  const out = raw
    // Fenced code blocks: keep the code words, drop the fences.
    .replace(/```[^\n]*\n?/g, '')
    .replace(/```/g, '')
    // Images: the alt text only.
    .replace(/!\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, '$1')
    // Links: `label (url)` — the URL is information, keep it visible.
    .replace(/\[([^\]]*)\]\(([^)\s]+)[^)]*\)/g, '$1 ($2)')
    // Headings, blockquotes, list markers: structural noise on one line.
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\s*>\s?/gm, '')
    .replace(/^\s*[-*+]\s+/gm, '')
    // Inline emphasis and code: keep the words, drop the markers.
    .replace(/\*\*([^*]+)\*\*/g, '$1')
    .replace(/(^|\W)\*([^*\n]+)\*/g, '$1$2')
    .replace(/(^|\W)_([^_\n]+)_/g, '$1$2')
    .replace(/`([^`]*)`/g, '$1')
  return truncateOneLine(out)
}

/**
 * #782 — one-line notice copy for a rate-limit wait, shared by every theme
 * so the IRC gutter line and the legacy status line say the same thing.
 */
export function formatRateLimitNotice(wait: {
  provider: string
  reason: string
  remaining_seconds: number
  wait_until_ms?: number
}): string {
  const remaining =
    wait.wait_until_ms != null
      ? Math.max(0, Math.ceil((wait.wait_until_ms - Date.now()) / 1000))
      : Math.max(0, Math.ceil(wait.remaining_seconds || 0))
  const rule = String(wait.reason || 'rate limit').replace(/_/g, ' ')
  return truncateOneLine(`${wait.provider}: ${rule} — waiting ${remaining}s`)
}

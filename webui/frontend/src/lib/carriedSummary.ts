/**
 * #1694 — the body of a session hop, as chrome the user can inspect.
 *
 * A hop's `context_carried` status line says *that* context was carried. This
 * is the half that says *what*: the redacted injection blob the new backend
 * session was actually seeded with, plus the provenance needed to read it —
 * which seats it crossed, how much, and what was deliberately left out.
 *
 * Two rules this module exists to keep:
 *
 *  1. **Absent is not empty.** An empty hop (`hop_notice_text`'s "No prior
 *     context to carry" branch) carries no payload, and `parseCarriedSummary`
 *     returns `null` for it. The transcript must never show an expandable that
 *     implies context exists when none was carried.
 *  2. **The wire is untrusted.** Every field is type-checked. A `text` that is
 *     not a string is dropped outright rather than stringified into the DOM.
 *
 * This is distinct from a compaction `ConversationSummary` (REQ-37): that is a
 * Django row with a span and a user-controlled in-context tick, this is chrome
 * on the `ui_events` side channel describing one hop. They are not
 * interchangeable and neither is derived from the other.
 */

export interface CarriedSummary {
  /** The redacted blob the new session was seeded with. */
  text: string
  fromCli: string
  toCli: string
  mode: string
  tokens: number
  turnCount: number
  omitted: string[]
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function asCount(value: unknown): number {
  if (typeof value === 'boolean' || !Number.isFinite(value as number)) return 0
  const n = Math.trunc(value as number)
  return n > 0 ? n : 0
}

export function parseCarriedSummary(value: unknown): CarriedSummary | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const row = value as Record<string, unknown>
  // A non-string body is not "empty" — it is malformed. Rendering `String(x)`
  // would put `[object Object]` in the transcript and claim a summary exists.
  if (typeof row.text !== 'string') return null
  const text = row.text.trim()
  if (!text) return null
  const omitted = Array.isArray(row.omitted)
    ? row.omitted.filter((item): item is string => typeof item === 'string' && !!item.trim())
    : []
  return {
    text,
    fromCli: asText(row.from_cli ?? row.fromCli),
    toCli: asText(row.to_cli ?? row.toCli),
    mode: asText(row.mode) || 'summary',
    tokens: asCount(row.tokens),
    turnCount: asCount(row.turn_count ?? row.turnCount),
    omitted,
  }
}

/** "grok → agy", or an honest placeholder when the endpoints are unknown. */
export function carriedSummaryRoute(summary: CarriedSummary): string {
  const from = summary.fromCli
  const to = summary.toCli
  if (from && to) return `${from} → ${to}`
  if (to) return `→ ${to}`
  if (from) return `${from} →`
  return 'session hop'
}

/** "42 tokens" / "3 turns" — only the parts the server actually reported. */
export function carriedSummaryScale(summary: CarriedSummary): string {
  const parts: string[] = []
  if (summary.tokens > 0) parts.push(`${summary.tokens} tokens`)
  if (summary.turnCount > 0) parts.push(`${summary.turnCount} turns`)
  return parts.join(' · ')
}

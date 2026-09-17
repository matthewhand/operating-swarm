/** Nested conversation compact / summaries (REQ-37). */

export interface ConversationSummary {
  id: number
  conversation_id: string
  span: { start: number; end: number }
  parent_summary_id: number | null
  body: string
  created_at: string
  replaced_count?: number
  /** Unticked = summary (and its span) stop feeding model context. */
  include_in_context?: boolean
}

export interface ChatBubble {
  key: string
  role: 'user' | 'assistant' | 'status' | 'system'
  text: string
  streaming: boolean
  /** REQ-104 — expandable archive of the previous swarm thread. */
  kind?: 'prior_history'
  ts?: string
}

export type DisplayItem =
  | { kind: 'message'; message: ChatBubble }
  | { kind: 'summary'; summary: ConversationSummary }

function spanOf(summary: ConversationSummary): { start: number; end: number } {
  const start = Number(summary.span?.start ?? 0)
  const end = Number(summary.span?.end ?? start)
  return { start, end: end < start ? start : end }
}

export function outermostSummaries(summaries: ConversationSummary[]): ConversationSummary[] {
  const nested = new Set(
    summaries
      .map((row) => row.parent_summary_id)
      .filter((id): id is number => id != null),
  )
  return summaries
    .filter((row) => !nested.has(row.id))
    .slice()
    .sort((a, b) => {
      const as = spanOf(a)
      const bs = spanOf(b)
      return as.start - bs.start || bs.end - as.end || a.id - b.id
    })
}

export function summariesById(
  summaries: ConversationSummary[],
): Record<number, ConversationSummary> {
  return Object.fromEntries(summaries.map((row) => [row.id, row]))
}

/** UI walk: covered spans become bordered Summary blocks; leftover turns stay bubbles. */
export function buildDisplayItems(
  messages: ChatBubble[],
  summaries: ConversationSummary[],
): DisplayItem[] {
  if (!summaries.length) {
    return messages.map((message) => ({ kind: 'message' as const, message }))
  }
  const cover: Array<ConversationSummary | undefined> = Array(messages.length)
  for (const row of outermostSummaries(summaries)) {
    const { start, end } = spanOf(row)
    const from = Math.max(0, start)
    const to = Math.min(messages.length - 1, end)
    for (let i = from; i <= to; i += 1) {
      if (!cover[i]) cover[i] = row
    }
  }
  const items: DisplayItem[] = []
  const emitted = new Set<number>()
  let i = 0
  while (i < messages.length) {
    const row = cover[i]
    if (row && !emitted.has(row.id)) {
      items.push({ kind: 'summary', summary: row })
      emitted.add(row.id)
      i = Math.min(messages.length - 1, spanOf(row).end) + 1
      continue
    }
    if (row) {
      i += 1
      continue
    }
    items.push({ kind: 'message', message: messages[i] })
    i += 1
  }
  return items
}

/** Texts the token meter should count (summaries + uncovered raw). */
export function contextTextsForMeter(
  messages: ChatBubble[],
  summaries: ConversationSummary[],
): string[] {
  return buildDisplayItems(messages, summaries)
    .filter((item) => item.kind === 'summary' || (item.message.role !== 'status' && item.message.role !== 'system'))
    .map((item) => (item.kind === 'summary' ? item.summary.body : item.message.text))
}

/** Inclusive raw-transcript offset of a user/assistant bubble (status/system skipped). */
export function rawOffsetForMessage<T extends { key: string; role: string }>(
  messages: T[],
  key: string,
): number {
  let offset = -1
  for (const row of messages) {
    if (row.role === 'user' || row.role === 'assistant') {
      offset += 1
      if (row.key === key) return offset
    }
  }
  return -1
}

export function isConversationSummary(value: unknown): value is ConversationSummary {
  if (!value || typeof value !== 'object') return false
  const row = value as Partial<ConversationSummary>
  if (typeof row.id !== 'number' || typeof row.body !== 'string') return false
  if (!row.span || typeof row.span !== 'object') return false
  const start = Number((row.span as { start?: unknown }).start)
  const end = Number((row.span as { end?: unknown }).end)
  return Number.isFinite(start) && Number.isFinite(end)
}

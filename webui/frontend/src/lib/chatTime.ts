/** Gap timestamps for the chat log. Calendar day is Australia/Sydney, not UTC. */

export const CHAT_TIME_ZONE = 'Australia/Sydney'
export const CHAT_GAP_MS = 15 * 60 * 1000

export function parseCreatedAtMs(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  if (!trimmed) return undefined
  const asNumber = Number(trimmed)
  if (Number.isFinite(asNumber) && asNumber > 1e11) return asNumber
  const parsed = Date.parse(trimmed)
  return Number.isFinite(parsed) ? parsed : undefined
}

function partMap(
  ms: number,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
): Record<string, string> {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, ...options }).formatToParts(
    new Date(ms),
  )
  const map: Record<string, string> = {}
  for (const part of parts) {
    if (part.type !== 'literal') map[part.type] = part.value
  }
  return map
}

export function sydneyDayKey(ms: number, timeZone: string = CHAT_TIME_ZONE): string {
  const parts = partMap(ms, timeZone, { year: 'numeric', month: '2-digit', day: '2-digit' })
  return `${parts.year}-${(parts.month || '').padStart(2, '0')}-${(parts.day || '').padStart(2, '0')}`
}

function addCalendarDays(year: number, month: number, day: number, delta: number) {
  const utc = new Date(Date.UTC(year, month - 1, day + delta))
  return {
    year: utc.getUTCFullYear(),
    month: utc.getUTCMonth() + 1,
    day: utc.getUTCDate(),
  }
}

function formatClock(ms: number, timeZone: string): string {
  const parts = partMap(ms, timeZone, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
  const dayPeriod = (parts.dayPeriod || 'AM').replace(/\./g, '').trim().toUpperCase()
  return `${Number(parts.hour)}:${parts.minute} ${dayPeriod}`
}

/** Today 7:21 AM / Yesterday 6:54 AM / Wed 3 Sep 6:54 AM */
export function formatGapLabel(
  ms: number,
  nowMs: number = Date.now(),
  timeZone: string = CHAT_TIME_ZONE,
): string {
  const clock = formatClock(ms, timeZone)
  const day = sydneyDayKey(ms, timeZone)
  const today = sydneyDayKey(nowMs, timeZone)
  if (day === today) return `Today ${clock}`

  const todayParts = partMap(nowMs, timeZone, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  })
  const yesterday = addCalendarDays(
    Number(todayParts.year),
    Number(todayParts.month),
    Number(todayParts.day),
    -1,
  )
  const yesterdayKey = `${yesterday.year}-${String(yesterday.month).padStart(2, '0')}-${String(yesterday.day).padStart(2, '0')}`
  if (day === yesterdayKey) return `Yesterday ${clock}`

  const stamp = partMap(ms, timeZone, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  return `${stamp.weekday} ${stamp.day} ${stamp.month} ${clock}`
}

export function shouldShowGapStamp(
  previousMs: number | undefined,
  nextMs: number | undefined,
  timeZone: string = CHAT_TIME_ZONE,
): boolean {
  if (previousMs == null || nextMs == null) return false
  if (!Number.isFinite(previousMs) || !Number.isFinite(nextMs)) return false
  if (nextMs - previousMs >= CHAT_GAP_MS) return true
  return sydneyDayKey(previousMs, timeZone) !== sydneyDayKey(nextMs, timeZone)
}

/**
 * REQ-86: Left-rail timestamp for an agent/team/remote row.
 * Relative for recent (<60m), then Today HH:MM AM/PM, Yesterday, or Wed D MMM.
 * Returns null if the thread has no messages.
 */
export function formatRailTimestamp(
  ms: number | undefined | null,
  nowMs: number = Date.now(),
  timeZone: string = CHAT_TIME_ZONE,
): string | null {
  if (ms == null || !Number.isFinite(ms) || ms <= 0) return null
  const diffMs = nowMs - ms
  if (diffMs >= 0 && diffMs < 60 * 1000) {
    return 'Just now'
  }
  if (diffMs >= 60 * 1000 && diffMs < 60 * 60 * 1000) {
    const mins = Math.floor(diffMs / 60000)
    return `${mins} min ago`
  }
  const clock = formatClock(ms, timeZone)
  const day = sydneyDayKey(ms, timeZone)
  const today = sydneyDayKey(nowMs, timeZone)
  if (day === today) return `Today ${clock}`

  const todayParts = partMap(nowMs, timeZone, {
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
  })
  const yesterday = addCalendarDays(
    Number(todayParts.year),
    Number(todayParts.month),
    Number(todayParts.day),
    -1,
  )
  const yesterdayKey = `${yesterday.year}-${String(yesterday.month).padStart(2, '0')}-${String(yesterday.day).padStart(2, '0')}`
  if (day === yesterdayKey) return `Yesterday ${clock}`

  const stamp = partMap(ms, timeZone, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  return `${stamp.weekday} ${stamp.day} ${stamp.month} ${clock}`
}

export const PREVIEW_SNIPPET_MAX_CHARS = 100

/**
 * Normalizes whitespace and truncates preview text with an ellipsis if it exceeds maxChars.
 */
export function truncateSnippet(text: string, maxChars = PREVIEW_SNIPPET_MAX_CHARS): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= maxChars) return clean
  return `${clean.slice(0, maxChars).trimEnd()}…`
}

/**
 * REQ-177: Selects the most recent message from a thread to display in the sidepane rail.
 * Preference order:
 * 1. Latest assistant reply with non-empty text (shows the agent's latest response).
 * 2. Latest user message with non-empty text if no assistant reply exists yet.
 * 3. Returns null if thread is empty or only contains status/empty messages.
 */
export function selectLatestMessage(
  messages: ReadonlyArray<{ role?: string; text?: string; content?: string; key?: string }>,
): { role: string; text: string; key?: string } | null {
  if (!Array.isArray(messages) || messages.length === 0) return null

  // 1. Prefer latest assistant message with non-empty text
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m && m.role === 'assistant') {
      const text = (m.text ?? m.content ?? '').trim()
      if (text.length > 0) {
        return { role: 'assistant', text, key: m.key }
      }
    }
  }

  // 2. Fallback to latest user message if no assistant message exists
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i]
    if (m && m.role === 'user') {
      const text = (m.text ?? m.content ?? '').trim()
      if (text.length > 0) {
        return { role: 'user', text, key: m.key }
      }
    }
  }

  return null
}

/**
 * Resolves the last message snippet and timestamp for a rail row.
 * Prefers live thread activity from local chat sessions (REQ-177).
 */
export function getRowLastMessage(
  id: string,
  sessions?: Array<{ updatedAt?: number; startedAt?: number; snippet?: string }>,
  agentMeta?: Record<string, unknown>,
  fallbackTimestampMs?: number | null,
): { snippet: string | null; timestamp: number | null } {
  const rawTime =
    agentMeta?.last_message_at ?? agentMeta?.lastMessageAt ?? agentMeta?.updated_at
  let parsedTime: number | null = null
  if (typeof rawTime === 'number' && Number.isFinite(rawTime)) {
    parsedTime = rawTime
  } else if (typeof rawTime === 'string') {
    const p = Date.parse(rawTime)
    if (Number.isFinite(p)) parsedTime = p
  }

  const rawSnippet =
    (agentMeta?.last_message ?? agentMeta?.lastMessage) as string | undefined

  // 1. Live thread activity in local chat sessions (REQ-177)
  try {
    if (typeof localStorage !== 'undefined') {
      const rawChats = localStorage.getItem('swarm_agent_chat_sessions')
      if (rawChats) {
        const parsed = JSON.parse(rawChats)
        const session = parsed?.[id]
        if (session && Array.isArray(session.messages) && session.messages.length > 0) {
          const selected = selectLatestMessage(session.messages)
          if (selected) {
            let ts = parsedTime
            if (!ts && typeof selected.key === 'string') {
              const match = selected.key.match(/-(\d{12,})$/)
              if (match) ts = Number(match[1])
            }
            return {
              snippet: rawSnippet ?? truncateSnippet(selected.text),
              timestamp: ts ?? parsedTime ?? fallbackTimestampMs ?? null,
            }
          }
        }
      }
    }
  } catch {
    /* storage unavailable */
  }

  // 2. Scale-out multi-session fallback
  if (sessions && sessions.length > 0) {
    const sorted = [...sessions].sort((a, b) => (b.updatedAt ?? 0) - (a.updatedAt ?? 0))
    const top = sorted[0]
    if (top) {
      return {
        snippet: rawSnippet ?? (top.snippet ? truncateSnippet(top.snippet) : null),
        timestamp: parsedTime ?? top.updatedAt ?? top.startedAt ?? fallbackTimestampMs ?? null,
      }
    }
  }

  // 3. Fallback to explicit metadata or placeholder description
  return {
    snippet: rawSnippet ?? (agentMeta?.snippet as string) ?? (agentMeta?.description as string) ?? null,
    timestamp: parsedTime ?? fallbackTimestampMs ?? null,
  }
}

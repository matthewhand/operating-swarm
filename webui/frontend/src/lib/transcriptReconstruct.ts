/**
 * Reconstruct chat chrome from side-channel UI events (REQ-70 / #789).
 *
 * Model turns stay in `turns`. Status/info/hop chrome lives in `ui_events`.
 * The UI interleaves them by `seq` for display. Filter-on-mixed is a belt
 * only — Success is this reconstruction path.
 */

import { asTranscriptRole, isStatusRole, type ChatTranscriptRole } from './chatStatus'
import { isRateLimitWait, type RateLimitWait } from './providerRateLimits'

export type TranscriptTurn = {
  role?: string
  content?: string
  text?: string
  ts?: string
  timestamp?: string
  created_at?: string
  edited?: boolean
  kind?: string
  seq?: number
  rate_limit?: RateLimitWait
}

export type UiEvent = TranscriptTurn

export type ReconstructedMessage = {
  role: ChatTranscriptRole
  content: string
  ts?: string
  edited?: boolean
  kind?: 'prior_history'
  rate_limit?: RateLimitWait
}

function seqOf(row: TranscriptTurn, fallback: number): number {
  return typeof row.seq === 'number' && Number.isFinite(row.seq) ? row.seq : fallback
}

function contentOf(row: TranscriptTurn): string {
  if (typeof row.content === 'string') return row.content
  if (typeof row.text === 'string') return row.text
  return ''
}

function tsOf(row: TranscriptTurn): string | undefined {
  const raw = row.ts || row.timestamp || row.created_at
  return typeof raw === 'string' && raw.trim() ? raw.trim() : undefined
}

function toMessage(row: TranscriptTurn): ReconstructedMessage | null {
  const content = contentOf(row)
  if (row.kind === 'prior_history') {
    const prior: ReconstructedMessage = { role: 'system', content, kind: 'prior_history' }
    if (row.edited === true) prior.edited = true
    return prior
  }
  const roleRaw = typeof row.role === 'string' ? row.role : ''
  if (roleRaw !== 'user' && roleRaw !== 'assistant' && !isStatusRole(roleRaw) && roleRaw !== 'info') {
    if (!roleRaw) {
      const chrome: ReconstructedMessage = { role: 'status', content }
      const ts = tsOf(row)
      if (ts) chrome.ts = ts
      return chrome
    }
    return null
  }
  const out: ReconstructedMessage = {
    role: asTranscriptRole(roleRaw || 'status'),
    content,
  }
  if (row.edited === true) out.edited = true
  const ts = tsOf(row)
  if (ts) out.ts = ts
  if (isRateLimitWait(row.rate_limit)) out.rate_limit = row.rate_limit
  return out
}

export function isChromeRole(role: string | undefined): boolean {
  return isStatusRole(role)
}

export function isModelTurnRole(role: string | undefined): boolean {
  return role === 'user' || role === 'assistant'
}

export function splitMixedMessages(messages: TranscriptTurn[]): {
  turns: TranscriptTurn[]
  events: UiEvent[]
} {
  const turns: TranscriptTurn[] = []
  const events: UiEvent[] = []
  messages.forEach((row, index) => {
    const stamped = { ...row, seq: seqOf(row, index) }
    if (
      isChromeRole(row.role) ||
      row.kind === 'prior_history' ||
      row.kind === 'hop' ||
      row.kind === 'pr_opened' ||
      row.kind === 'teammate_task'
    ) {
      events.push(stamped)
    } else {
      turns.push(stamped)
    }
  })
  return { turns, events }
}

export function reconstructTranscript(
  turns: TranscriptTurn[] | undefined,
  events: UiEvent[] | undefined,
): ReconstructedMessage[] {
  const items: { seq: number; tie: number; row: TranscriptTurn }[] = []
  ;(turns || []).forEach((row, index) => {
    items.push({ seq: seqOf(row, index), tie: 0, row })
  })
  ;(events || []).forEach((row, index) => {
    items.push({ seq: seqOf(row, index), tie: 1, row })
  })
  items.sort((a, b) => a.seq - b.seq || a.tie - b.tie)
  return items
    .map((item) => toMessage(item.row))
    .filter((row): row is ReconstructedMessage => row != null)
}

export function messagesFromThreadPayload(payload: {
  messages?: unknown
  turns?: unknown
  ui_events?: unknown
}): ReconstructedMessage[] {
  const turns = Array.isArray(payload?.turns) ? (payload.turns as TranscriptTurn[]) : null
  const events = Array.isArray(payload?.ui_events) ? (payload.ui_events as UiEvent[]) : null
  const messages = Array.isArray(payload?.messages) ? (payload.messages as TranscriptTurn[]) : []
  if (turns && events) {
    return reconstructTranscript(turns, events)
  }
  if (events && messages.length) {
    const hasChrome = messages.some((row) => isChromeRole(row.role))
    if (!hasChrome) return reconstructTranscript(messages, events)
  }
  if (events && !messages.length) {
    return reconstructTranscript([], events)
  }
  const split = splitMixedMessages(messages)
  const mixed = messages.some((row) => isChromeRole(row.role))
  return reconstructTranscript(mixed ? split.turns : messages, mixed ? split.events : [])
}

export function turnIndexFromDisplay(
  messages: Array<{ role?: string }>,
  displayIndex: number,
): number {
  let turns = 0
  for (let i = 0; i <= displayIndex && i < messages.length; i += 1) {
    if (isModelTurnRole(messages[i]?.role)) turns += 1
  }
  return turns - 1
}

export function formatChromeTime(ts?: string): string {
  if (!ts || !ts.trim()) return ''
  const date = new Date(ts)
  return Number.isNaN(date.getTime()) ? ts.trim() : date.toISOString()
}

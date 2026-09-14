/**
 * REQ-90 / #447 — queued composer sends while a generation is in flight.
 *
 * Queued rows live in localStorage with the conversation id (not Neon, not
 * the model-turn store) so a refresh still shows them. Drain is oldest-first
 * and skips a row whose editor is focused or dirty.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export const QUEUED_SENDS_KEY = 'swarm_queued_sends'
export const SUGGESTION_CHIP_EVENT = 'swarm:suggestion-chip'

export const QUEUED_PANE_MAX_HEIGHT_CLASS = 'max-h-[33%]'
export const QUEUED_PANE_MAX_HEIGHT_STYLE = '33.333%'

export interface QueuedSendRow {
  id: string
  text: string
  createdAt: number
}

export type QueuedSendMap = Record<string, QueuedSendRow[]>

export function newQueuedSendId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `queued-${crypto.randomUUID()}`
  }
  return `queued-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function isQueuedSendRow(value: unknown): value is QueuedSendRow {
  if (!value || typeof value !== 'object') return false
  const row = value as QueuedSendRow
  return (
    typeof row.id === 'string' &&
    row.id.length > 0 &&
    typeof row.text === 'string' &&
    typeof row.createdAt === 'number' &&
    Number.isFinite(row.createdAt)
  )
}

export function loadQueuedSendsMap(): QueuedSendMap {
  try {
    const raw = localStorage.getItem(QUEUED_SENDS_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: QueuedSendMap = {}
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!key || !Array.isArray(value)) continue
      const rows = value.filter(isQueuedSendRow)
      if (rows.length) out[key] = rows
    }
    return out
  } catch {
    return {}
  }
}

export function saveQueuedSendsMap(map: QueuedSendMap): void {
  try {
    localStorage.setItem(QUEUED_SENDS_KEY, JSON.stringify(map))
  } catch {
    /* persistence is best-effort */
  }
}

export function loadQueuedSends(conversationId: string): QueuedSendRow[] {
  const id = conversationId.trim()
  if (!id) return []
  return loadQueuedSendsMap()[id] ?? []
}

export function clearAllQueuedSends(): void {
  try {
    localStorage.removeItem(QUEUED_SENDS_KEY)
  } catch {
    /* best-effort */
  }
}

export function saveQueuedSends(conversationId: string, rows: QueuedSendRow[]): void {
  const id = conversationId.trim()
  if (!id) return
  const all = loadQueuedSendsMap()
  if (rows.length === 0) delete all[id]
  else all[id] = rows
  saveQueuedSendsMap(all)
}

export function enqueueQueuedSend(
  rows: QueuedSendRow[],
  text: string,
  now = Date.now(),
): QueuedSendRow[] {
  const trimmed = text.trim()
  if (!trimmed) return rows
  return [
    ...rows,
    {
      id: newQueuedSendId(),
      text: trimmed,
      createdAt: now,
    },
  ]
}

export function updateQueuedSend(
  rows: QueuedSendRow[],
  id: string,
  text: string,
): QueuedSendRow[] {
  return rows.map((row) => (row.id === id ? { ...row, text } : row))
}

export function removeQueuedSend(rows: QueuedSendRow[], id: string): QueuedSendRow[] {
  return rows.filter((row) => row.id !== id)
}

export function prependQueuedSend(rows: QueuedSendRow[], row: QueuedSendRow): QueuedSendRow[] {
  if (rows.some((existing) => existing.id === row.id)) return rows
  return [row, ...rows]
}

/** Oldest-first; skip ids whose editor is focused or dirty. */
export function nextDrainableQueuedSend(
  rows: QueuedSendRow[],
  holdIds: ReadonlySet<string> | readonly string[],
): QueuedSendRow | null {
  const held = holdIds instanceof Set ? holdIds : new Set(holdIds)
  for (const row of rows) {
    if (held.has(row.id)) continue
    if (!row.text.trim()) continue
    return row
  }
  return null
}

export function generationIsInFlight(
  messages: Array<{ streaming?: boolean }>,
  awaitingAssistant: boolean,
): boolean {
  return awaitingAssistant || messages.some((row) => row.streaming === true)
}

export function queuedPaneMaxHeightPx(transcriptHeight: number): number {
  if (!Number.isFinite(transcriptHeight) || transcriptHeight <= 0) return 0
  return Math.max(1, Math.round(transcriptHeight / 3))
}

/** #198: previews cap at this many chars; hover (title) reveals the full text. */
export const QUEUED_PREVIEW_MAX_CHARS = 80

/**
 * #198: single-line preview for a queued row — whitespace collapsed, capped
 * at 80 chars with an ellipsis. The pane styles the truncation with a fade;
 * the full text stays available via the row's hover title and the editor.
 */
export function queuedPreviewText(text: string): string {
  const singleLine = text.replace(/\s+/g, ' ').trim()
  if (singleLine.length <= QUEUED_PREVIEW_MAX_CHARS) return singleLine
  return `${singleLine.slice(0, QUEUED_PREVIEW_MAX_CHARS)}…`
}

export function queuedPreviewIsTruncated(text: string): boolean {
  return text.replace(/\s+/g, ' ').trim().length > QUEUED_PREVIEW_MAX_CHARS
}

export function suggestionChipText(event: Event): string {
  const detail = (event as CustomEvent<{ text?: unknown }>).detail
  return typeof detail?.text === 'string' ? detail.text : ''
}

export function useQueuedSends(conversationId: string): {
  rows: QueuedSendRow[]
  enqueue: (text: string) => void
  update: (id: string, text: string) => void
  remove: (id: string) => void
  restore: (row: QueuedSendRow) => void
} {
  const [rows, setRows] = useState<QueuedSendRow[]>(() => loadQueuedSends(conversationId))
  const idRef = useRef(conversationId)

  useEffect(() => {
    if (idRef.current === conversationId) return
    idRef.current = conversationId
    setRows(loadQueuedSends(conversationId))
  }, [conversationId])

  useEffect(() => {
    if (idRef.current !== conversationId) return
    saveQueuedSends(conversationId, rows)
  }, [conversationId, rows])

  const enqueue = useCallback((text: string) => {
    setRows((prev) => enqueueQueuedSend(prev, text))
  }, [])

  const update = useCallback((id: string, text: string) => {
    setRows((prev) => updateQueuedSend(prev, id, text))
  }, [])

  const remove = useCallback((id: string) => {
    setRows((prev) => removeQueuedSend(prev, id))
  }, [])

  const restore = useCallback((row: QueuedSendRow) => {
    setRows((prev) => prependQueuedSend(prev, row))
  }, [])

  return useMemo(
    () => ({ rows, enqueue, update, remove, restore }),
    [rows, enqueue, update, remove, restore],
  )
}

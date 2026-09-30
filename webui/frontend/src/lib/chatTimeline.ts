/**
 * #1274 — timeline markers: day boundaries + session resumes, derived at
 * render time from row `ts` values. Virtual rows only — nothing persisted,
 * no server/schema change, and turn-index math skips them because they are
 * never inserted into the message list (they are interleaved at render).
 */

export const SESSION_RESUME_GAP_MS = 2 * 60 * 60 * 1000

/** A virtual marker row to render between real messages. */
export interface TimelineMarker {
  kind: 'day' | 'resumed'
  /** 'day': friendly date label ('Today', 'Yesterday', 'Mon 23 Sep 2026'). */
  /** 'resumed': `Resumed HH:MM` — same-day re-open after a gap. */
  label: string
  /** ISO timestamp of the boundary row the marker points at. */
  ts: string
}

function startOfDay(d: Date): number {
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime()
}

function sameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() &&
    a.getMonth() === b.getMonth() &&
    a.getDate() === b.getDate()
  )
}

/** 'Today' / 'Yesterday' / locale-aware short form for older days. */
export function dayLabelFor(ts: Date, now: Date = new Date()): string {
  const day = startOfDay(ts)
  const today = startOfDay(now)
  const yesterday = today - 24 * 60 * 60 * 1000
  if (day === today) return 'Today'
  if (day === yesterday) return 'Yesterday'
  return ts.toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

/** `Resumed HH:MM` (24h, deterministic across locales) for a same-day re-open. */
export function resumedLabelFor(ts: Date): string {
  const hhmm = ts.toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  })
  return `Resumed ${hhmm}`
}

/**
 * Markers for the render walk. Rules:
 * - First *message* row (user/assistant) opens with a day marker.
 * - Between consecutive message rows: a different calendar day → day marker;
 *   otherwise a gap ≥ SESSION_RESUME_GAP_MS → resumed-time divider.
 * - Status/notice rows (role 'status' etc.) never trigger or carry markers.
 */
export function timelineMarkersFor(
  rows: Array<{ role: string; ts?: string | null }>,
  now: Date = new Date(),
): Map<number, TimelineMarker> {
  const markers = new Map<number, TimelineMarker>()
  let prevMessage: Date | null = null
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i]
    const isMessage = row.role === 'user' || row.role === 'assistant'
    if (!isMessage || !row.ts) continue
    const ts = new Date(row.ts)
    if (Number.isNaN(ts.getTime())) continue
    if (!prevMessage) {
      markers.set(i, { kind: 'day', label: dayLabelFor(ts, now), ts: row.ts })
    } else if (!sameDay(prevMessage, ts)) {
      markers.set(i, { kind: 'day', label: dayLabelFor(ts, now), ts: row.ts })
    } else if (ts.getTime() - prevMessage.getTime() >= SESSION_RESUME_GAP_MS) {
      markers.set(i, { kind: 'resumed', label: resumedLabelFor(ts), ts: row.ts })
    }
    prevMessage = ts
  }
  return markers
}

/** One display item: the compact/cull walk output or a #1274 virtual marker. */
export interface TimelineDisplayItem {
  kind: 'marker'
  marker: TimelineMarker
  key: string
}

type DisplayItemAny = Record<string, any>

/**
 * Interleave markers into a display list (#1274) without mutating indices:
 * message items consume raw indices in order; a summary item is anchored at
 * its span start (markers land before the covered block). The returned list
 * mixes 'marker' items with the original items — downstream turn-index math
 * reads only the original items, so it is unaffected.
 */
export function interleaveTimelineMarkers(
  displayItems: DisplayItemAny[],
  messages: Array<{ role: string; ts?: string | null }>,
  now: Date = new Date(),
): Array<DisplayItemAny | TimelineDisplayItem> {
  const markers = timelineMarkersFor(messages, now)
  if (markers.size === 0) return displayItems
  const out: Array<DisplayItemAny | TimelineDisplayItem> = []
  let raw = -1
  for (const item of displayItems) {
    if (item.kind === 'summary') {
      const start = Number(item.summary?.span?.start ?? 0)
      const marker = markers.get(start)
      if (marker) out.push({ kind: 'marker', marker, key: `tl-${start}` })
      out.push(item)
      raw = Math.max(raw, Number(item.summary?.span?.end ?? start))
      continue
    }
    raw += 1
    const marker = markers.get(raw)
    if (marker) out.push({ kind: 'marker', marker, key: `tl-${raw}` })
    out.push(item)
  }
  return out
}

/**
 * Opt-in streaming display (#220). Theme gate first; user default off;
 * per-seat override on top.
 */

import {
  bubbleThemeSupportsStreaming,
  loadBubbleTheme,
  type BubbleTheme,
} from './bubbleTheme'

export const STREAM_REPLIES_STORAGE_KEY = 'os.streamReplies'
export const STREAM_REPLIES_SEATS_STORAGE_KEY = 'os.streamReplies.seats'
export const STREAM_REPLIES_CHANGED_EVENT = 'swarm:stream-replies-changed'

export const STREAM_REPLIES_LABEL = 'Stream replies'
export const STREAM_REPLIES_TOOLTIP =
  'Show tokens as they arrive. Off by default — partial markdown is easy to mangle. Only themes that declare streaming support can show a live prefix.'
export const STREAM_REPLIES_SEAT_LABEL = 'Stream replies'
export const STREAM_REPLIES_SEAT_TOOLTIP =
  'Override the user Stream replies preference for this seat. Still blocked when the bubble theme does not support streaming.'

export type SeatStreamReplies = boolean | null

function emitChanged(): void {
  try {
    window.dispatchEvent(new CustomEvent(STREAM_REPLIES_CHANGED_EVENT))
  } catch {
    /* tests / non-browser */
  }
}

function readBool(raw: string | null): boolean | null {
  if (raw === '1' || raw === 'true') return true
  if (raw === '0' || raw === 'false') return false
  return null
}

/** User-level opt-in. Default off. */
export function loadStreamReplies(): boolean {
  try {
    return readBool(localStorage.getItem(STREAM_REPLIES_STORAGE_KEY)) === true
  } catch {
    return false
  }
}

export function saveStreamReplies(value: boolean): boolean {
  const next = Boolean(value)
  try {
    localStorage.setItem(STREAM_REPLIES_STORAGE_KEY, next ? '1' : '0')
  } catch {
    /* persistence is best-effort */
  }
  emitChanged()
  return next
}

function readSeatMap(): Record<string, boolean> {
  try {
    const raw = localStorage.getItem(STREAM_REPLIES_SEATS_STORAGE_KEY)
    if (!raw) return {}
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    const out: Record<string, boolean> = {}
    for (const [id, value] of Object.entries(parsed as Record<string, unknown>)) {
      const seat = id.trim()
      if (!seat) continue
      if (value === true || value === false) out[seat] = value
    }
    return out
  } catch {
    return {}
  }
}

function writeSeatMap(map: Record<string, boolean>): void {
  try {
    if (Object.keys(map).length === 0) {
      localStorage.removeItem(STREAM_REPLIES_SEATS_STORAGE_KEY)
    } else {
      localStorage.setItem(STREAM_REPLIES_SEATS_STORAGE_KEY, JSON.stringify(map))
    }
  } catch {
    /* persistence is best-effort */
  }
  emitChanged()
}

/** `null` means inherit the user toggle. */
export function loadSeatStreamReplies(seatId: string): SeatStreamReplies {
  const id = seatId.trim()
  if (!id) return null
  const map = readSeatMap()
  return Object.prototype.hasOwnProperty.call(map, id) ? map[id] : null
}

export function saveSeatStreamReplies(seatId: string, value: SeatStreamReplies): SeatStreamReplies {
  const id = seatId.trim()
  if (!id) return null
  const map = readSeatMap()
  if (value === null) delete map[id]
  else map[id] = value
  writeSeatMap(map)
  return value
}

export function parseSeatStreamReplies(raw: unknown): SeatStreamReplies {
  if (raw === true || raw === 'on' || raw === 'true' || raw === '1') return true
  if (raw === false || raw === 'off' || raw === 'false' || raw === '0') return false
  return null
}

/**
 * Theme gate AND user/seat toggle. Streaming transport is unchanged;
 * this only decides whether a partial markdown prefix is shown.
 */
export function streamingPartialEnabled(opts?: {
  theme?: BubbleTheme
  seatId?: string
}): boolean {
  const theme = opts?.theme ?? loadBubbleTheme()
  if (!bubbleThemeSupportsStreaming(theme)) return false
  if (opts?.seatId) {
    const seat = loadSeatStreamReplies(opts.seatId)
    if (seat !== null) return seat
  }
  return loadStreamReplies()
}

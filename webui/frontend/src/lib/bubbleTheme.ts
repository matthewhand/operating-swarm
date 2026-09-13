import { parseCreatedAtMs } from './chatTime'

export const BUBBLE_THEMES = ['speech', 'simple', 'irc', 'feed'] as const
export type BubbleTheme = (typeof BUBBLE_THEMES)[number]

// REQ-844 / #166: 'speech' is the default — tails visible + symmetric gutters.
export const DEFAULT_BUBBLE_THEME: BubbleTheme = 'speech'
export const BUBBLE_THEME_STORAGE_KEY = 'os.bubbleTheme'

export const BUBBLE_THEME_LABELS: Record<BubbleTheme, string> = {
  speech: 'Speech',
  simple: 'Simple',
  irc: 'IRC',
  feed: 'Feed',
}

export function parseBubbleTheme(raw: unknown): BubbleTheme {
  if (typeof raw === 'string' && (BUBBLE_THEMES as readonly string[]).includes(raw)) {
    return raw as BubbleTheme
  }
  return DEFAULT_BUBBLE_THEME
}

export function loadBubbleTheme(): BubbleTheme {
  try {
    return parseBubbleTheme(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY))
  } catch {
    return DEFAULT_BUBBLE_THEME
  }
}

export function saveBubbleTheme(value: string): BubbleTheme {
  const next = parseBubbleTheme(value)
  try {
    localStorage.setItem(BUBBLE_THEME_STORAGE_KEY, next)
  } catch {
    /* persistence is best-effort */
  }
  return next
}

/** Compact clock for feed-style rows; empty when `ts` is missing or invalid. */
export function formatBubbleTime(ts: string | undefined): string {
  const ms = parseCreatedAtMs(ts)
  if (ms == null) return ''
  return new Intl.DateTimeFormat(undefined, { hour: 'numeric', minute: '2-digit' }).format(
    new Date(ms),
  )
}

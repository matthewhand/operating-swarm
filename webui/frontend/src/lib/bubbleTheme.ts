import {
  allBubbleThemes,
  getRegisteredBubbleTheme,
  type BubbleTheme,
  type BubbleThemeBase,
} from './bubbleThemes'

export {
  allBubbleThemes,
  BubbleThemeBase,
  FeedTheme,
  formatBubbleTime,
  IrcTheme,
  registerBubbleTheme,
  SimpleTheme,
  SpeechTheme,
  type ActionRowPlacement,
  type ComposerChrome,
  type MessageLayout,
  type TimestampPlacement,
} from './bubbleThemes'
export type { BubbleTheme } from './bubbleThemes'

// REQ-844 / #166: 'speech' is the default — tails visible + symmetric gutters.
export const DEFAULT_BUBBLE_THEME: BubbleTheme = 'speech'
export const BUBBLE_THEME_STORAGE_KEY = 'os.bubbleTheme'
/** #506: fired by saveBubbleTheme so mounted transcripts re-read without a remount. */
export const BUBBLE_THEME_CHANGED_EVENT = 'swarm:bubble-theme-changed'

/** Theme ids in registry insertion order. */
export const BUBBLE_THEMES = allBubbleThemes().map((theme) => theme.id)

export const BUBBLE_THEME_LABELS = Object.fromEntries(
  allBubbleThemes().map((theme) => [theme.id, theme.label]),
) as Record<BubbleTheme, string>

/** #220 — per-theme streaming affordance (theme gate; #217 owns the rest). */
export type StreamingAffordance = 'caret' | 'block' | 'none'

export interface BubbleThemeStreaming {
  id: BubbleTheme
  supportsStreaming: boolean
  renderStreamingAffordance: StreamingAffordance
}

export const BUBBLE_THEME_STREAMING: Record<BubbleTheme, BubbleThemeStreaming> = {
  speech: { id: 'speech', supportsStreaming: true, renderStreamingAffordance: 'caret' },
  simple: { id: 'simple', supportsStreaming: true, renderStreamingAffordance: 'caret' },
  irc: { id: 'irc', supportsStreaming: true, renderStreamingAffordance: 'block' },
  feed: { id: 'feed', supportsStreaming: false, renderStreamingAffordance: 'none' },
}

export function bubbleThemeSupportsStreaming(theme: BubbleTheme): boolean {
  return BUBBLE_THEME_STREAMING[theme].supportsStreaming
}

export function renderStreamingAffordance(theme: BubbleTheme): StreamingAffordance {
  return BUBBLE_THEME_STREAMING[theme].renderStreamingAffordance
}

export function streamingAffordanceClass(theme: BubbleTheme): string {
  const kind = renderStreamingAffordance(theme)
  if (kind === 'none') return ''
  return `os-stream-affordance os-stream-affordance--${kind}`
}

export function parseBubbleTheme(raw: unknown): BubbleTheme {
  if (typeof raw === 'string' && (BUBBLE_THEMES as readonly string[]).includes(raw)) {
    return raw as BubbleTheme
  }
  return DEFAULT_BUBBLE_THEME
}

export function getBubbleTheme(id?: unknown): BubbleThemeBase {
  return getRegisteredBubbleTheme(parseBubbleTheme(id))
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
  try {
    window.dispatchEvent(new CustomEvent(BUBBLE_THEME_CHANGED_EVENT, { detail: next }))
  } catch {
    /* tests / non-browser */
  }
  return next
}

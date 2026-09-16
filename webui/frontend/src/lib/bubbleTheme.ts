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
  type ComposerChrome,
  type MessageLayout,
  type TimestampPlacement,
} from './bubbleThemes'
export type { BubbleTheme } from './bubbleThemes'

// REQ-844 / #166: 'speech' is the default — tails visible + symmetric gutters.
export const DEFAULT_BUBBLE_THEME: BubbleTheme = 'speech'
export const BUBBLE_THEME_STORAGE_KEY = 'os.bubbleTheme'

/** Theme ids in registry insertion order. */
export const BUBBLE_THEMES = allBubbleThemes().map((theme) => theme.id)

export const BUBBLE_THEME_LABELS = Object.fromEntries(
  allBubbleThemes().map((theme) => [theme.id, theme.label]),
) as Record<BubbleTheme, string>

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
  return next
}

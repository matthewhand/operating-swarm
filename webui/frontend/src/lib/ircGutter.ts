/**
 * #675 — IRC theme's resizable gutter: the timestamp+name column width is a
 * persisted preference, dragged via a vertical divider between the gutter
 * and the message column. Classic IRC alignment: every message body starts
 * at the same x regardless of prefix length.
 *
 * Bounds keep the timestamp+name from clipping (min) and the message column
 * from collapsing (max). Double-click resets (the component calls save with
 * the DEFAULT).
 */
import type { BubbleTheme } from './bubbleTheme'

export const IRC_GUTTER_STORAGE_KEY = 'os.ircGutterPx'
/** Fired on `window` after every persisted width change (drag move + reset). */
export const IRC_GUTTER_CHANGED_EVENT = 'os:irc-gutter-changed'
export const IRC_GUTTER_MIN_PX = 96
export const IRC_GUTTER_MAX_PX = 400
export const IRC_GUTTER_DEFAULT_PX = 140

export function loadIrcGutterPx(): number {
  try {
    const raw = localStorage.getItem(IRC_GUTTER_STORAGE_KEY)
    const n = raw === null ? NaN : Number(raw)
    if (Number.isFinite(n) && n >= IRC_GUTTER_MIN_PX && n <= IRC_GUTTER_MAX_PX) {
      return Math.round(n)
    }
  } catch {
    /* storage unavailable */
  }
  return IRC_GUTTER_DEFAULT_PX
}

export function saveIrcGutterPx(px: number): number {
  const clamped = Math.min(IRC_GUTTER_MAX_PX, Math.max(IRC_GUTTER_MIN_PX, Math.round(px)))
  try {
    localStorage.setItem(IRC_GUTTER_STORAGE_KEY, String(clamped))
    window.dispatchEvent(new CustomEvent(IRC_GUTTER_CHANGED_EVENT))
  } catch {
    /* persistence is best-effort */
  }
  return clamped
}

/** Is this theme the resizable-gutter IRC layout? */
export function themeUsesIrcGutter(theme: BubbleTheme | string | undefined): boolean {
  return theme === 'irc'
}

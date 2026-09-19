/**
 * #506 / REQ-908 — action-row button labels preference.
 *
 * Controls whether the message action/reaction row (#70) renders icon+text
 * (default) or icon-only. A user preference, deliberately *not* a theme
 * attribute — #217's `BubbleThemeBase` contract governs theme-driven layout,
 * not user prefs. Shape copied from `lib/streamReplies.ts`; the default is
 * the inverse (labels default ON).
 */

export const ACTION_ROW_LABELS_STORAGE_KEY = 'os.actionRowLabels'
export const ACTION_ROW_LABELS_CHANGED_EVENT = 'swarm:action-row-labels-changed'

function emitChanged(): void {
  try {
    window.dispatchEvent(new CustomEvent(ACTION_ROW_LABELS_CHANGED_EVENT))
  } catch {
    /* tests / non-browser */
  }
}

/** Absent/unreadable key resolves `true` — labels are on by default. */
export function loadActionRowLabels(): boolean {
  try {
    const raw = localStorage.getItem(ACTION_ROW_LABELS_STORAGE_KEY)
    if (raw === '0' || raw === 'false') return false
    return true
  } catch {
    return true
  }
}

export function saveActionRowLabels(value: boolean): boolean {
  const next = Boolean(value)
  try {
    localStorage.setItem(ACTION_ROW_LABELS_STORAGE_KEY, next ? '1' : '0')
  } catch {
    /* persistence is best-effort */
  }
  emitChanged()
  return next
}

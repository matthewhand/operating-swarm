/**
 * #770 — composer routing-pill resize: clamps, persistence, and drag math.
 *
 * The pill's visible width is user-resizable via a double-slit grab handle:
 * - Upper bound is the **full unclipped text width** (px), so expansion
 *   never overshoots into empty space.
 * - Lower bound is ~3 characters of label + chevron (2.5rem).
 * - The chosen width persists across refreshes; `null` means "auto" (the
 *   pre-#770 default sizing).
 */

export const COMPOSER_PILL_MIN_WIDTH = 40 // 2.5rem — ~3 chars + chevron
/** Default (auto) cap matching the CSS max-width. */
export const COMPOSER_PILL_AUTO_MAX = 200 // 12.5rem
export const COMPOSER_PILL_WIDTH_STORAGE_KEY = 'swarm_composer_pill_width'

/**
 * Clamp a dragged pill width. `fullTextWidth` is the measured unclipped
 * label width; the upper bound never exceeds it (no empty expansion) and
 * never falls below the min so the handle stays usable.
 */
export function clampPillWidth(width: number, fullTextWidth: number): number {
  const max = Math.max(COMPOSER_PILL_MIN_WIDTH, Math.ceil(fullTextWidth))
  return Math.min(Math.max(Math.round(width), COMPOSER_PILL_MIN_WIDTH), max)
}

/** Load the persisted pill width; `null` = auto (never resized). */
export function loadPillWidth(): number | null {
  try {
    const raw = localStorage.getItem(COMPOSER_PILL_WIDTH_STORAGE_KEY)
    if (raw !== null) {
      const parsed = Number(raw)
      if (!Number.isNaN(parsed) && parsed >= COMPOSER_PILL_MIN_WIDTH) return parsed
    }
  } catch {}
  return null
}

/** Persist the pill width; `null` clears back to auto. */
export function savePillWidth(width: number | null): void {
  try {
    if (width === null) localStorage.removeItem(COMPOSER_PILL_WIDTH_STORAGE_KEY)
    else localStorage.setItem(COMPOSER_PILL_WIDTH_STORAGE_KEY, String(width))
  } catch {}
}

/**
 * Drag math: a new width from the start width minus pointer displacement deltaX
 * (event.clientX - startX).
 *
 * In the composer layout, the routing pill is anchored on the right side of the
 * composer row. Dragging left (negative deltaX) expands the pill toward the
 * composer input space. Dragging right (positive deltaX) narrows the pill.
 */
export function pillWidthFromDrag(
  startWidth: number,
  deltaX: number,
  fullTextWidth: number,
): number {
  return clampPillWidth(startWidth - deltaX, fullTextWidth)
}


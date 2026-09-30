/**
 * #1231 — the routing pill's label budget.
 *
 * #770's drag-resize is replaced by a fixed cap: 32 characters, ellipsis on
 * overflow, full path on the tooltip. One owner so the pill, its testids,
 * and any future label surface cannot drift apart.
 */

export const COMPOSER_PILL_MAX_CHARS = 32

/**
 * Collapse whitespace, then cap at {@link COMPOSER_PILL_MAX_CHARS} with a
 * trailing ellipsis (counted inside the budget). Empty-safe.
 */
export function truncatePillLabel(raw: string | null | undefined): string {
  const clean = (raw ?? '').replace(/\s+/g, ' ').trim()
  if (clean.length <= COMPOSER_PILL_MAX_CHARS) return clean
  return `${clean.slice(0, COMPOSER_PILL_MAX_CHARS - 1).trimEnd()}…`
}

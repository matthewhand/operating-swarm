/**
 * REQ-116: Left rail resizer constants and persistence helpers.
 *
 * #765 adds a third rail state below avatar-only: fully collapsed (0px,
 * divider-only). Snap physics on drag are: < collapse threshold → 0px,
 * else ≤ avatar threshold → avatar rail, else smooth continuous width.
 */

export const MIN_RAIL_WIDTH = 68
export const MAX_RAIL_WIDTH = 420
export const DEFAULT_RAIL_WIDTH = 256
export const AVATAR_ONLY_THRESHOLD = 96
/** #765: below this dragged width the rail snaps fully shut (0px). */
export const COLLAPSE_SNAP_THRESHOLD = 52
/** #765: the fully collapsed divider-only state — border + pill only. */
export const COLLAPSED_RAIL_WIDTH = 0
export const RAIL_WIDTH_STORAGE_KEY = 'swarm_rail_width'

/**
 * #1083: on laptop viewports (<= 1440px), the rail defaults to compact
 * avatar-only mode (68px) so horizontal chat space is preserved. On wider
 * desktop viewports (> 1440px), it defaults to fully expanded (256px).
 */
export const LAPTOP_MAX_WIDTH = 1440

export function defaultRailWidth(viewportWidth?: number): number {
  if (typeof viewportWidth === 'number' && viewportWidth > 0 && viewportWidth <= LAPTOP_MAX_WIDTH) {
    return MIN_RAIL_WIDTH
  }
  return DEFAULT_RAIL_WIDTH
}

export function clampRailWidth(width: number, viewportWidth?: number): number {
  const max = viewportWidth ? Math.min(MAX_RAIL_WIDTH, Math.floor(viewportWidth * 0.45)) : MAX_RAIL_WIDTH
  return Math.min(Math.max(width, MIN_RAIL_WIDTH), max)
}

export function loadRailWidth(viewportWidth?: number): number {
  try {
    const raw = localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)
    if (raw) {
      const parsed = Number(raw)
      if (!Number.isNaN(parsed)) {
        // #765: 0 is a legal persisted state (fully collapsed); anything
        // below it is garbage and normalizes to collapsed rather than
        // falling back to the default.
        if (parsed <= COLLAPSED_RAIL_WIDTH) return COLLAPSED_RAIL_WIDTH
        return clampRailWidth(parsed, viewportWidth)
      }
    }
  } catch {}
  return defaultRailWidth(viewportWidth)
}

export function saveRailWidth(width: number): void {
  try {
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(width))
  } catch {}
}

export function isAvatarOnlyWidth(width: number): boolean {
  return width <= AVATAR_ONLY_THRESHOLD
}

/** #765: true only for the exact divider-only state. */
export function isFullyCollapsedWidth(width: number): boolean {
  return width <= COLLAPSED_RAIL_WIDTH
}

/**
 * #806: clamp plus an avatar-only snap; #765 adds the edge-collapse snap.
 * Dragging into the avatar-only zone (width <= AVATAR_ONLY_THRESHOLD) snaps
 * straight to MIN_RAIL_WIDTH so there is no floating dead zone between the
 * collapsed avatar rail and labeled rails; dragging below the collapse
 * threshold snaps fully shut so the edge is a firm detent, not a fight.
 */
export function snapRailWidth(width: number, viewportWidth?: number): number {
  if (width <= COLLAPSE_SNAP_THRESHOLD) return COLLAPSED_RAIL_WIDTH
  const clamped = clampRailWidth(width, viewportWidth)
  if (clamped <= AVATAR_ONLY_THRESHOLD) return MIN_RAIL_WIDTH
  return clamped
}

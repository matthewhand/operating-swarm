/**
 * REQ-116: Left rail resizer constants and persistence helpers.
 */

export const MIN_RAIL_WIDTH = 68
export const MAX_RAIL_WIDTH = 420
export const DEFAULT_RAIL_WIDTH = 256
export const AVATAR_ONLY_THRESHOLD = 96
export const RAIL_WIDTH_STORAGE_KEY = 'swarm_rail_width'

export function clampRailWidth(width: number, viewportWidth?: number): number {
  const max = viewportWidth ? Math.min(MAX_RAIL_WIDTH, Math.floor(viewportWidth * 0.45)) : MAX_RAIL_WIDTH
  return Math.min(Math.max(width, MIN_RAIL_WIDTH), max)
}

export function loadRailWidth(): number {
  try {
    const raw = localStorage.getItem(RAIL_WIDTH_STORAGE_KEY)
    if (raw) {
      const parsed = Number(raw)
      if (!Number.isNaN(parsed)) {
        return clampRailWidth(parsed)
      }
    }
  } catch {}
  return DEFAULT_RAIL_WIDTH
}

export function saveRailWidth(width: number): void {
  try {
    localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(width))
  } catch {}
}

export function isAvatarOnlyWidth(width: number): boolean {
  return width <= AVATAR_ONLY_THRESHOLD
}

/**
 * #806: clamp plus an avatar-only snap. Dragging into the avatar-only zone
 * (width <= AVATAR_ONLY_THRESHOLD) snaps straight to MIN_RAIL_WIDTH so there
 * is no floating dead zone between the collapsed avatar rail and labeled
 * rails; dragging back out releases smoothly once past the threshold.
 */
export function snapRailWidth(width: number, viewportWidth?: number): number {
  const clamped = clampRailWidth(width, viewportWidth)
  if (clamped <= AVATAR_ONLY_THRESHOLD) return MIN_RAIL_WIDTH
  return clamped
}

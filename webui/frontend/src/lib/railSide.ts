/**
 * #816 — which side of the screen the agent rail docks to.
 *
 * 'left' is the historical default; 'right' serves one-handed/mobile reach.
 * Plain localStorage (same pattern as `railResize`'s rail width) plus a
 * CustomEvent so App (render order), AgentSidebar (mirror math), and
 * SettingsSheet (opposite dock) react without a new provider.
 */

export type RailSide = 'left' | 'right'

export const RAIL_SIDE_STORAGE_KEY = 'swarm_rail_side'
export const RAIL_SIDE_EVENT = 'swarm:rail-side-change'

export function loadRailSide(): RailSide {
  try {
    return localStorage.getItem(RAIL_SIDE_STORAGE_KEY) === 'right' ? 'right' : 'left'
  } catch {
    return 'left'
  }
}

export function saveRailSide(side: RailSide): void {
  try {
    localStorage.setItem(RAIL_SIDE_STORAGE_KEY, side)
  } catch {}
  if (typeof window !== 'undefined' && typeof window.dispatchEvent === 'function') {
    try {
      window.dispatchEvent(new CustomEvent(RAIL_SIDE_EVENT, { detail: side }))
    } catch {}
  }
}

/**
 * #816: on the right, the row grows *into* the pane, so the drag vector and
 * the arrow keys mirror. `expand` = the user's grow intent (toward content).
 */
export function sideAwareWidthDelta(side: RailSide, expand: boolean): number {
  const sign = side === 'right' ? -1 : 1
  return expand ? sign * 12 : -sign * 12
}

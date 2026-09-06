/**
 * REQ-194 Phase 2 — body/head combo persistence.
 *
 * Per ADR-008 the combo is a **sub-key only while the theme is `robot3d`** —
 * there is no second persist key for the theme itself (that stays
 * `swarm_avatar_theme`). The combo store validates against the catalog and
 * falls back to the default combo on unknown values.
 */

import { defaultCombo, isRobot3dCombo } from './catalog'
import type { Robot3dCombo } from './types'

export const ROBOT3D_COMBO_STORAGE_KEY = 'swarm_robot3d_combo'
export const ROBOT3D_COMBO_SET_EVENT = 'swarm:set-robot3d-combo'

export function loadRobot3dCombo(): Robot3dCombo {
  try {
    const stored = localStorage.getItem(ROBOT3D_COMBO_STORAGE_KEY)
    if (stored) {
      const parsed: unknown = JSON.parse(stored)
      if (isRobot3dCombo(parsed)) {
        return parsed
      }
    }
  } catch {
    /* storage unavailable or malformed */
  }
  return defaultCombo()
}

export function saveRobot3dCombo(combo: Robot3dCombo): Robot3dCombo {
  const next = isRobot3dCombo(combo) ? combo : defaultCombo()
  try {
    localStorage.setItem(ROBOT3D_COMBO_STORAGE_KEY, JSON.stringify(next))
  } catch {
    /* persistence is best-effort */
  }
  try {
    window.dispatchEvent(
      new CustomEvent<Robot3dCombo>(ROBOT3D_COMBO_SET_EVENT, { detail: next }),
    )
  } catch {
    /* window unavailable */
  }
  return next
}
/**
 * REQ-194 Phase 2 — body/head combo picker.
 *
 * ADR-008: the combo is a **sub-key only while the theme is `robot3d`**.
 * It lists the catalog's ≥2 bodies × ≥2 heads that all play the same
 * MiniPose clips. Rendered by AvatarThemePicker only when robot3d is active.
 */

import { useEffect, useState } from 'react'
import { ROBOT3D_BODIES, ROBOT3D_HEADS } from '../lib/robot3d/catalog'
import {
  ROBOT3D_COMBO_SET_EVENT,
  ROBOT3D_COMBO_STORAGE_KEY,
  loadRobot3dCombo,
  saveRobot3dCombo,
} from '../lib/robot3d/comboStore'
import type { Robot3dCombo } from '../lib/robot3d/types'

export default function Robot3dComboPicker() {
  const [combo, setCombo] = useState<Robot3dCombo>(loadRobot3dCombo)

  useEffect(() => {
    const onSet = (event: Event) => {
      const detail = (event as CustomEvent<Robot3dCombo>).detail
      if (detail?.bodyId && detail?.headId) setCombo(detail)
    }
    const onStorage = (event: StorageEvent) => {
      if (event.key === ROBOT3D_COMBO_STORAGE_KEY || event.key === null) {
        setCombo(loadRobot3dCombo())
      }
    }
    window.addEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
    window.addEventListener('storage', onStorage)
    return () => {
      window.removeEventListener(ROBOT3D_COMBO_SET_EVENT, onSet)
      window.removeEventListener('storage', onStorage)
    }
  }, [])

  return (
    <div
      className="flex w-full flex-col gap-1"
      data-robot3d-combo-picker="true"
      data-testid="robot3d-combo-picker"
    >
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs font-medium">
          Body
          <select
            className="select select-bordered select-sm w-full"
            value={combo.bodyId}
            data-robot3d-combo-body="true"
            onChange={(event) => saveRobot3dCombo({ ...combo, bodyId: event.target.value })}
          >
            {ROBOT3D_BODIES.map((body) => (
              <option key={body.id} value={body.id}>
                {body.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium">
          Head
          <select
            className="select select-bordered select-sm w-full"
            value={combo.headId}
            data-robot3d-combo-head="true"
            onChange={(event) => saveRobot3dCombo({ ...combo, headId: event.target.value })}
          >
            {ROBOT3D_HEADS.map((head) => (
              <option key={head.id} value={head.id}>
                {head.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-xs text-base-content/55">
        Every body × head combo plays the same idle / listen / working / error clips — one pose
        family, attach-offset mix-and-match (ADR-008 §2.4). All rigs are original stylised robots.
      </p>
    </div>
  )
}
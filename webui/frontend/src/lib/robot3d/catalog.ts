/**
 * REQ-194 Phase 2 — body/head combo catalog.
 *
 * One pose family: every rig consumes the SAME MiniPose fields. A second
 * body/head is legal only if it consumes those fields (unknown extras
 * ignored; missing required fields fail closed). Bodies publish the head
 * socket (`headAttachment`); heads must match that bind pose. Combo is
 * playable only when both parts declare `idle` + `working` (ADR-008 §2.4).
 *
 * Rigs are **original stylised robots** (MIT) — deliberately NOT the
 * licensed Reachy mesh; see LICENSE/NOTICE.
 */

import type { Robot3dCombo, Robot3dRigManifest } from './types'

function ref(source: string, loop: boolean, fadeMs: number) {
  return { loop, fadeMs, source }
}

export const ROBOT3D_BODIES: Robot3dRigManifest[] = [
  {
    schema: 1,
    id: 'reachy_classic',
    kind: 'body',
    label: 'Classic',
    license: { spdx: 'MIT', notice: 'Original stylised robot, not the licensed Reachy mesh' },
    units: 'meters',
    restHeight: 0.78,
    restHeightTolerance: 0.04,
    headAttachment: {
      offset: { x: 0, y: 0.46, z: 0 },
      quaternion: { x: 0, y: 0, z: 0, w: 1 },
    },
    clips: {
      idle: ref('clips#idle', true, 240),
      listen: ref('clips#listen', true, 200),
      working: ref('clips#working', true, 160),
      dance: ref('clips#dance', false, 180),
      error: ref('clips#error', false, 300),
    },
  },
  {
    schema: 1,
    id: 'column',
    kind: 'body',
    label: 'Column',
    license: { spdx: 'MIT', notice: 'Original stylised robot, not the licensed Reachy mesh' },
    units: 'meters',
    restHeight: 0.82,
    restHeightTolerance: 0.04,
    headAttachment: {
      offset: { x: 0, y: 0.5, z: 0 },
      quaternion: { x: 0, y: 0, z: 0, w: 1 },
    },
    clips: {
      idle: ref('clips#idle', true, 240),
      listen: ref('clips#listen', true, 200),
      working: ref('clips#working', true, 160),
      dance: ref('clips#dance', false, 180),
      error: ref('clips#error', false, 300),
    },
  },
]

export const ROBOT3D_HEADS: Robot3dRigManifest[] = [
  {
    schema: 1,
    id: 'mini_dome',
    kind: 'head',
    label: 'Mini dome',
    license: { spdx: 'MIT', notice: 'Original stylised robot, not the licensed Reachy mesh' },
    units: 'meters',
    restHeight: 0.78,
    restHeightTolerance: 0.04,
    headAttachment: {
      offset: { x: 0, y: 0, z: 0 },
      quaternion: { x: 0, y: 0, z: 0, w: 1 },
    },
    clips: {
      idle: ref('clips#idle', true, 240),
      listen: ref('clips#listen', true, 200),
      working: ref('clips#working', true, 160),
      dance: ref('clips#dance', false, 180),
      error: ref('clips#error', false, 300),
    },
  },
  {
    schema: 1,
    id: 'dish_visor',
    kind: 'head',
    label: 'Dish visor',
    license: { spdx: 'MIT', notice: 'Original stylised robot, not the licensed Reachy mesh' },
    units: 'meters',
    restHeight: 0.78,
    restHeightTolerance: 0.04,
    headAttachment: {
      offset: { x: 0, y: 0.02, z: 0 },
      quaternion: { x: 0, y: 0, z: 0, w: 1 },
    },
    clips: {
      idle: ref('clips#idle', true, 240),
      listen: ref('clips#listen', true, 200),
      working: ref('clips#working', true, 160),
      dance: ref('clips#dance', false, 180),
      error: ref('clips#error', false, 300),
    },
  },
]

/** Phase 1 default — one self-contained rig that is body + head together. */
export const ROBOT3D_FULL: Robot3dRigManifest = {
  schema: 1,
  id: 'reachy_full',
  kind: 'full',
  label: 'Reachy-like',
  license: { spdx: 'MIT', notice: 'Original stylised robot, not the licensed Reachy mesh' },
  units: 'meters',
  restHeight: 0.78,
  restHeightTolerance: 0.04,
  headAttachment: {
    offset: { x: 0, y: 0.46, z: 0 },
    quaternion: { x: 0, y: 0, z: 0, w: 1 },
  },
  clips: {
    idle: ref('clips#idle', true, 240),
    listen: ref('clips#listen', true, 200),
    working: ref('clips#working', true, 160),
    dance: ref('clips#dance', false, 180),
    error: ref('clips#error', false, 300),
  },
}

export function defaultCombo(): Robot3dCombo {
  return { bodyId: ROBOT3D_BODIES[0].id, headId: ROBOT3D_HEADS[0].id }
}

export function isRobot3dCombo(value: unknown): value is Robot3dCombo {
  if (typeof value !== 'object' || value === null) return false
  const combo = value as Record<string, unknown>
  if (typeof combo.bodyId !== 'string' || typeof combo.headId !== 'string') return false
  return (
    ROBOT3D_BODIES.some((b) => b.id === combo.bodyId) &&
    ROBOT3D_HEADS.some((h) => h.id === combo.headId)
  )
}

/** All legal combos — ≥2 bodies × ≥2 heads sharing the same pose family. */
export function listRobot3dCombos(): Robot3dCombo[] {
  const combos: Robot3dCombo[] = []
  for (const body of ROBOT3D_BODIES) {
    for (const head of ROBOT3D_HEADS) {
      combos.push({ bodyId: body.id, headId: head.id })
    }
  }
  return combos
}

export function robot3dBody(id: string): Robot3dRigManifest | undefined {
  return ROBOT3D_BODIES.find((b) => b.id === id)
}

export function robot3dHead(id: string): Robot3dRigManifest | undefined {
  return ROBOT3D_HEADS.find((h) => h.id === id)
}

/**
 * The merged rig for a combo. Playable only when both parts declare
 * `idle` + `working`; unknown extra clip ids fail closed to `undefined`.
 */
export function comboRig(combo: Robot3dCombo): Robot3dRigManifest | undefined {
  const body = robot3dBody(combo.bodyId)
  const head = robot3dHead(combo.headId)
  if (!body || !head) return undefined
  if (!body.clips.idle || !body.clips.working || !head.clips.idle || !head.clips.working) {
    return undefined
  }
  const clips: Robot3dRigManifest['clips'] = {}
  for (const id of ['idle', 'listen', 'working', 'dance', 'error'] as const) {
    const bodyRef = body.clips[id]
    const headRef = head.clips[id]
    if (bodyRef && headRef) {
      clips[id] = bodyRef
    }
  }
  return {
    schema: 1,
    id: `${body.id}+${head.id}`,
    kind: 'full',
    label: `${body.label} + ${head.label}`,
    license: body.license,
    units: 'meters',
    restHeight: body.restHeight,
    restHeightTolerance: Math.max(body.restHeightTolerance, head.restHeightTolerance),
    headAttachment: {
      offset: {
        x: body.headAttachment.offset.x + head.headAttachment.offset.x,
        y: body.headAttachment.offset.y + head.headAttachment.offset.y,
        z: body.headAttachment.offset.z + head.headAttachment.offset.z,
      },
      quaternion: body.headAttachment.quaternion,
    },
    clips,
  }
}

/** A playable rig (full rig or merged combo). */
export function resolveRobot3dRig(combo?: Robot3dCombo): Robot3dRigManifest {
  if (combo) {
    const merged = comboRig(combo)
    if (merged) return merged
  }
  return ROBOT3D_FULL
}
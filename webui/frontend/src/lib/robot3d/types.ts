/**
 * REQ-194 / ADR-008 — MiniPose clip & rig contract (open-swarm owned).
 *
 * Normative shapes mirror docs/adr/008-3d-robot-avatar-theme.md §2.3–§2.5
 * (which itself mirrors the Reachy report docs/reports/reachy-3d-avatar-inspiration.md).
 * Clips are baked MiniPose frame lists — never THREE.AnimationMixer tracks.
 * Mix-and-match is MiniPose + attach offsets, never bone-name swaps.
 */

/** Semantic clip ids named by chrome (ADR-008 §2.1). */
export type Robot3dClipId = 'idle' | 'listen' | 'working' | 'dance' | 'error'

/** One Reachy-Mini-shaped frame. Units: metres + radians + unit quaternion. */
export interface MiniPose {
  body_yaw: number
  head: {
    pos: { x: number; y: number; z: number }
    quat: { x: number; y: number; z: number; w: number }
  }
  antennas: { left: number; right: number }
}

export interface Robot3dClip {
  schema: 1
  id: Robot3dClipId
  loop: boolean
  fadeMs: number
  /** Samples/sec. Idle/working target ≤ 30; pause when hidden. */
  hz: number
  frames: MiniPose[]
}

/** Head socket published by a body rig (Phase 2 attach offset). */
export interface Robot3dAttachment {
  offset: { x: number; y: number; z: number }
  quaternion: { x: number; y: number; z: number; w: number }
}

export interface Robot3dClipRef {
  loop: boolean
  fadeMs: number
  source: string
}

export interface Robot3dRigManifest {
  schema: 1
  id: string
  kind: 'body' | 'head' | 'full'
  label: string
  license: { spdx: string; notice: string }
  units: 'meters'
  restHeight: number
  restHeightTolerance: number
  /** Socket the head mesh attaches to. Body/full MUST export it. */
  headAttachment: Robot3dAttachment
  clips: Partial<Record<Robot3dClipId, Robot3dClipRef>>
}

export interface Robot3dCombo {
  bodyId: string
  headId: string
}

export const ROBOT3D_CLIP_IDS: Robot3dClipId[] = [
  'idle',
  'listen',
  'working',
  'dance',
  'error',
] as const

export const ROBOT3D_REQUIRED_CLIPS: Robot3dClipId[] = ['idle', 'working']
/**
 * REQ-194 — baked MiniPose clips (open-swarm owned, original art).
 *
 * ADR-008 §2.3: clips are baked `MiniPose` frame lists, never AnimationMixer
 * tracks. `idle` + `working` are Phase 1 required; `listen` / `dance` /
 * `error` ship now and are consumed by Phase 3 status wiring.
 *
 * All clips play on every rig in the catalog — a combo is legal only when it
 * declares `idle` + `working`; the extra clips are shared.
 */

import { quatFromTilt } from './poseMath'
import type { MiniPose, Robot3dClip, Robot3dClipId } from './types'

/** Compact frame helper — body_yaw, head pitch/roll/yaw (radians), antenna left/right. */
function frame(
  bodyYaw: number,
  pitch: number,
  roll: number,
  headYaw: number,
  antennaLeft: number,
  antennaRight: number,
  headY = 0.46,
): MiniPose {
  return {
    body_yaw: bodyYaw,
    head: {
      pos: { x: 0, y: headY, z: 0 },
      quat: quatFromTilt(pitch, roll, headYaw),
    },
    antennas: { left: antennaLeft, right: antennaRight },
  }
}

function clip(
  id: Robot3dClipId,
  loop: boolean,
  hz: number,
  fadeMs: number,
  frames: MiniPose[],
): Robot3dClip {
  return { schema: 1, id, loop, fadeMs, hz, frames }
}

/** Slow, calm breathing sway. */
const idle = clip('idle', true, 12, 240, [
  frame(0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
  frame(0.06, 0.02, 0.01, 0.02, 0.04, 0.04),
  frame(0.10, 0.04, 0.02, 0.04, 0.08, 0.08),
  frame(0.06, 0.03, 0.01, 0.02, 0.06, 0.06),
  frame(0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
  frame(-0.06, -0.02, -0.01, -0.02, -0.04, -0.04),
  frame(-0.10, -0.04, -0.02, -0.04, -0.08, -0.08),
  frame(-0.06, -0.03, -0.01, -0.02, -0.06, -0.06),
])

/** Busy, faster motion with a head nod and fluttering antennas. */
const working = clip('working', true, 20, 160, [
  frame(0.00, 0.02, 0.00, 0.00, 0.10, -0.10),
  frame(0.14, 0.10, 0.03, 0.08, 0.22, -0.22),
  frame(0.08, 0.05, 0.02, 0.05, 0.16, -0.16),
  frame(-0.08, 0.06, -0.02, -0.05, -0.16, 0.16),
  frame(-0.14, 0.10, -0.03, -0.08, -0.22, 0.22),
  frame(-0.08, 0.05, -0.02, -0.05, -0.16, 0.16),
  frame(0.10, 0.03, 0.02, 0.06, 0.18, -0.18),
  frame(0.00, 0.02, 0.00, 0.00, 0.10, -0.10),
])

/** Listening: head canted, antennas raised. */
const listen = clip('listen', true, 12, 200, [
  frame(0.00, 0.12, 0.10, 0.00, 0.30, 0.30),
  frame(0.02, 0.14, 0.12, 0.01, 0.34, 0.34),
  frame(0.00, 0.16, 0.14, 0.00, 0.38, 0.38),
  frame(-0.02, 0.14, 0.12, -0.01, 0.34, 0.34),
])

/** Error: head down, antennas drooped, holds last frame (non-loop). */
const error = clip('error', false, 12, 300, [
  frame(0.00, 0.00, 0.00, 0.00, 0.00, 0.00),
  frame(0.00, 0.10, 0.02, 0.00, -0.12, -0.12),
  frame(0.00, 0.24, 0.05, 0.00, -0.30, -0.30),
  frame(0.00, 0.34, 0.08, 0.00, -0.44, -0.44),
])

/** Happy dance — short, playful, never auto-loops on every reply. */
const dance = clip('dance', false, 18, 180, [
  frame(0.00, 0.02, 0.00, 0.00, 0.10, 0.10),
  frame(0.30, 0.06, 0.05, 0.12, 0.30, -0.10),
  frame(-0.10, 0.10, -0.04, -0.10, -0.20, 0.30),
  frame(0.36, 0.04, 0.06, 0.16, 0.34, -0.16),
  frame(-0.26, 0.08, -0.06, -0.14, -0.28, 0.26),
  frame(0.18, 0.06, 0.03, 0.08, 0.22, 0.00),
  frame(0.00, 0.02, 0.00, 0.00, 0.10, 0.10),
])

export const ROBOT3D_CLIPS: Record<Robot3dClipId, Robot3dClip> = {
  idle,
  working,
  listen,
  dance,
  error,
}

export function robot3dClip(id: Robot3dClipId): Robot3dClip {
  return ROBOT3D_CLIPS[id]
}

/** Canonical source strings referenced by every rig manifest. */
export const ROBOT3D_CLIP_SOURCES: Record<Robot3dClipId, string> = {
  idle: 'clips#idle',
  listen: 'clips#listen',
  working: 'clips#working',
  dance: 'clips#dance',
  error: 'clips#error',
}
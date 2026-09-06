/**
 * REQ-194 — pure MiniPose interpolation helpers.
 *
 * Kept free of `three` so the math is unit-testable in jsdom. The WebGL
 * pose-player (posePlayer.ts) consumes these to pose a procedural robot.
 */

import type { MiniPose, Robot3dClip } from './types'

/** Unit quaternion from Tait-Bryan pitch/roll/yaw (radians), XYZ order. */
export function quatFromTilt(
  pitch: number,
  roll = 0,
  yaw = 0,
): { x: number; y: number; z: number; w: number } {
  const cp = Math.cos(pitch / 2)
  const sp = Math.sin(pitch / 2)
  const cr = Math.cos(roll / 2)
  const sr = Math.sin(roll / 2)
  const cy = Math.cos(yaw / 2)
  const sy = Math.sin(yaw / 2)
  return {
    x: sr * cp * cy - cr * sp * sy,
    y: cr * sp * cy + sr * cp * sy,
    z: cr * cp * sy - sr * sp * cy,
    w: cr * cp * cy + sr * sp * sy,
  }
}

/** Shortest-path quaternion slerp. */
export function slerpQuat(
  a: { x: number; y: number; z: number; w: number },
  b: { x: number; y: number; z: number; w: number },
  t: number,
): { x: number; y: number; z: number; w: number } {
  let ax = a.x
  let ay = a.y
  let az = a.z
  let aw = a.w
  let bx = b.x
  let by = b.y
  let bz = b.z
  let bw = b.w
  let dot = ax * bx + ay * by + az * bz + aw * bw
  if (dot < 0) {
    bx = -bx
    by = -by
    bz = -bz
    bw = -bw
    dot = -dot
  }
  if (dot > 0.9995) {
    const k = 1 - t
    return {
      x: ax * k + bx * t,
      y: ay * k + by * t,
      z: az * k + bz * t,
      w: aw * k + bw * t,
    }
  }
  const theta = Math.acos(Math.min(dot, 1))
  const sinTheta = Math.sin(theta)
  const wa = Math.sin((1 - t) * theta) / sinTheta
  const wb = Math.sin(t * theta) / sinTheta
  return {
    x: ax * wa + bx * wb,
    y: ay * wa + by * wb,
    z: az * wa + bz * wb,
    w: aw * wa + bw * wb,
  }
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t
}

export function mixPose(a: MiniPose, b: MiniPose, t: number): MiniPose {
  return {
    body_yaw: lerp(a.body_yaw, b.body_yaw, t),
    head: {
      pos: {
        x: lerp(a.head.pos.x, b.head.pos.x, t),
        y: lerp(a.head.pos.y, b.head.pos.y, t),
        z: lerp(a.head.pos.z, b.head.pos.z, t),
      },
      quat: slerpQuat(a.head.quat, b.head.quat, t),
    },
    antennas: {
      left: lerp(a.antennas.left, b.antennas.left, t),
      right: lerp(a.antennas.right, b.antennas.right, t),
    },
  }
}

/**
 * Sample a clip at time `t` seconds. Loop-aware, with linear frame
 * interpolation at the clip's hz. Returns the interpolated pose.
 */
export function sampleClip(clip: Robot3dClip, t: number): MiniPose {
  const { frames, hz, loop } = clip
  if (frames.length === 0) {
    throw new Error(`clip '${clip.id}' has no frames`)
  }
  if (frames.length === 1) {
    return frames[0]
  }
  const frameTime = 1 / hz
  const total = frames.length * frameTime
  const position = loop ? ((t % total) + total) % total : Math.min(t, total - frameTime)
  const index = Math.floor(position / frameTime)
  const i0 = Math.min(index, frames.length - 1)
  const i1 = loop ? (i0 + 1) % frames.length : Math.min(i0 + 1, frames.length - 1)
  const frac = (position - index * frameTime) / frameTime
  return mixPose(frames[i0], frames[i1], frac)
}
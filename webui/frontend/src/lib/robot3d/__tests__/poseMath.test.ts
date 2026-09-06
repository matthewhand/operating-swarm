import { describe, expect, it } from 'vitest'
import { mixPose, quatFromTilt, sampleClip, slerpQuat } from '../poseMath'
import type { MiniPose, Robot3dClip } from '../types'

const IDENTITY = { x: 0, y: 0, z: 0, w: 1 }

const a: MiniPose = {
  body_yaw: 0,
  head: { pos: { x: 0, y: 0.4, z: 0 }, quat: IDENTITY },
  antennas: { left: 0, right: 0 },
}
const b: MiniPose = {
  body_yaw: 0.4,
  head: { pos: { x: 0, y: 0.5, z: 0.1 }, quat: { x: 0, y: 0, z: 0, w: 1 } },
  antennas: { left: 0.2, right: -0.2 },
}

describe('quatFromTilt', () => {
  it('returns identity for zero angles', () => {
    expect(quatFromTilt(0, 0, 0)).toEqual(IDENTITY)
  })

  it('returns a unit quaternion for nonzero angles', () => {
    const q = quatFromTilt(0.3, 0.2, 0.1)
    const norm = Math.hypot(q.x, q.y, q.z, q.w)
    expect(norm).toBeCloseTo(1, 6)
  })
})

describe('slerpQuat', () => {
  it('is identity at t=0 and target at t=1', () => {
    const target = quatFromTilt(0.5, 0, 0)
    expect(slerpQuat(IDENTITY, target, 0)).toEqual(IDENTITY)
    const end = slerpQuat(IDENTITY, target, 1)
    expect(end.x).toBeCloseTo(target.x, 6)
    expect(end.y).toBeCloseTo(target.y, 6)
  })

  it('keeps unit norm through the blend', () => {
    const q = slerpQuat(IDENTITY, quatFromTilt(0.8, 0.3, 0), 0.37)
    expect(Math.hypot(q.x, q.y, q.z, q.w)).toBeCloseTo(1, 6)
  })
})

describe('mixPose', () => {
  it('interpolates every MiniPose field', () => {
    const m = mixPose(a, b, 0.5)
    expect(m.body_yaw).toBeCloseTo(0.2, 6)
    expect(m.head.pos.y).toBeCloseTo(0.45, 6)
    expect(m.head.pos.z).toBeCloseTo(0.05, 6)
    expect(m.antennas.left).toBeCloseTo(0.1, 6)
    expect(m.antennas.right).toBeCloseTo(-0.1, 6)
  })
})

describe('sampleClip', () => {
  const clip: Robot3dClip = {
    schema: 1,
    id: 'idle',
    loop: true,
    fadeMs: 100,
    hz: 10,
    frames: [a, b],
  }

  it('starts at the first frame', () => {
    const p = sampleClip(clip, 0)
    expect(p.body_yaw).toBeCloseTo(0, 6)
  })

  it('interpolates between frames mid-cycle', () => {
    const p = sampleClip(clip, 0.05)
    expect(p.body_yaw).toBeCloseTo(0.2, 6)
  })

  it('loops back to the start for loop clips', () => {
    const p = sampleClip(clip, 0.2)
    expect(p.body_yaw).toBeCloseTo(0, 6)
  })

  it('holds the last frame for non-loop clips past the end', () => {
    const oneShot: Robot3dClip = { ...clip, loop: false, frames: [a, b] }
    const p = sampleClip(oneShot, 10)
    expect(p.body_yaw).toBeCloseTo(0.4, 6)
  })

  it('throws on empty clips', () => {
    const empty: Robot3dClip = { ...clip, frames: [] }
    expect(() => sampleClip(empty, 0)).toThrow(/no frames/)
  })
})
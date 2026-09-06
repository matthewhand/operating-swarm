import { describe, expect, it } from 'vitest'
import { ROBOT3D_CLIPS, ROBOT3D_CLIP_SOURCES, robot3dClip } from '../clips'
import { ROBOT3D_CLIP_IDS, ROBOT3D_REQUIRED_CLIPS } from '../types'

describe('robot3d clips', () => {
  it('ships every semantic clip id', () => {
    for (const id of ROBOT3D_CLIP_IDS) {
      expect(ROBOT3D_CLIPS[id]).toBeDefined()
    }
  })

  it('declares idle + working (Phase 1 required) with loops and sane hz', () => {
    for (const id of ROBOT3D_REQUIRED_CLIPS) {
      const clip = ROBOT3D_CLIPS[id]
      expect(clip.loop).toBe(true)
      expect(clip.hz).toBeGreaterThan(0)
      expect(clip.hz).toBeLessThanOrEqual(30)
      expect(clip.frames.length).toBeGreaterThan(1)
    }
  })

  it('non-loop clips stay non-loop (dance, error)', () => {
    expect(ROBOT3D_CLIPS.dance.loop).toBe(false)
    expect(ROBOT3D_CLIPS.error.loop).toBe(false)
  })

  it('every frame has a unit-quaternion head and finite fields', () => {
    for (const clip of Object.values(ROBOT3D_CLIPS)) {
      for (const frame of clip.frames) {
        const { x, y, z, w } = frame.head.quat
        expect(Math.hypot(x, y, z, w)).toBeCloseTo(1, 5)
        expect(Number.isFinite(frame.body_yaw)).toBe(true)
        expect(Number.isFinite(frame.antennas.left)).toBe(true)
        expect(Number.isFinite(frame.antennas.right)).toBe(true)
      }
    }
  })

  it('clip sources are canonical and unique', () => {
    for (const id of ROBOT3D_CLIP_IDS) {
      expect(ROBOT3D_CLIP_SOURCES[id]).toBe(`clips#${id}`)
      expect(robot3dClip(id).id).toBe(id)
    }
  })
})
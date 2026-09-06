import { describe, expect, it } from 'vitest'
import {
  ROBOT3D_BODIES,
  ROBOT3D_FULL,
  ROBOT3D_HEADS,
  comboRig,
  defaultCombo,
  isRobot3dCombo,
  listRobot3dCombos,
  resolveRobot3dRig,
} from '../catalog'
import { ROBOT3D_REQUIRED_CLIPS } from '../types'

describe('robot3d rig catalog', () => {
  it('ships >= 2 bodies x >= 2 heads sharing one pose family', () => {
    expect(ROBOT3D_BODIES.length).toBeGreaterThanOrEqual(2)
    expect(ROBOT3D_HEADS.length).toBeGreaterThanOrEqual(2)
    expect(listRobot3dCombos().length).toBeGreaterThanOrEqual(4)
  })

  it('every body publishes the head socket (headAttachment)', () => {
    for (const body of ROBOT3D_BODIES) {
      expect(body.kind).toBe('body')
      expect(body.headAttachment.offset).toBeDefined()
      expect(body.headAttachment.quaternion.w).toBeCloseTo(1, 5)
    }
  })

  it('every rig declares the Phase 1 required clips (idle + working)', () => {
    for (const rig of [...ROBOT3D_BODIES, ...ROBOT3D_HEADS, ROBOT3D_FULL]) {
      for (const id of ROBOT3D_REQUIRED_CLIPS) {
        expect(rig.clips[id]).toBeDefined()
      }
    }
  })

  it('every combo is playable and keeps a single pose family', () => {
    for (const combo of listRobot3dCombos()) {
      const rig = comboRig(combo)
      expect(rig).toBeDefined()
      for (const id of ROBOT3D_REQUIRED_CLIPS) {
        expect(rig?.clips[id]).toBeDefined()
      }
      expect(rig?.headAttachment.offset).toBeDefined()
    }
  })

  it('combo rigs inherit the shared clip sources (no fork per combo)', () => {
    const sources = new Set<string>()
    for (const combo of listRobot3dCombos()) {
      const rig = comboRig(combo)
      for (const id of ROBOT3D_REQUIRED_CLIPS) {
        sources.add(rig?.clips[id]?.source ?? '')
      }
    }
    expect(sources.size).toBe(2) // exactly clips#idle + clips#working, same for all combos
  })

  it('rest heights sit within shared tolerance (same socket family)', () => {
    const bodies = ROBOT3D_BODIES.map((b) => b.restHeight)
    const spread = Math.max(...bodies) - Math.min(...bodies)
    expect(spread).toBeLessThanOrEqual(0.06)
  })

  it('combo validation fails closed on unknown parts', () => {
    expect(isRobot3dCombo({ bodyId: 'nope', headId: 'mini_dome' })).toBe(false)
    expect(isRobot3dCombo(null)).toBe(false)
    expect(isRobot3dCombo('robot3d')).toBe(false)
    expect(comboRig({ bodyId: 'nope', headId: 'mini_dome' })).toBeUndefined()
  })

  it('resolveRobot3dRig falls back to the full Phase 1 rig', () => {
    expect(resolveRobot3dRig(undefined).id).toBe(ROBOT3D_FULL.id)
    expect(resolveRobot3dRig(defaultCombo()).kind).toBe('full')
  })
})
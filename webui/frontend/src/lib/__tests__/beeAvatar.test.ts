import { describe, expect, it } from 'vitest'
import {
  BEE_ACCENTS,
  BEE_ACCESSORIES,
  BEE_VARIANTS,
  beeSpecForAgent,
  isFaceBeeVariant,
  wanderBeeEyePose,
  type BeeVariant,
} from '../beeAvatar'

const ROSTER = Array.from({ length: 96 }, (_, i) => `agent-${i}`).concat([
  'codey',
  'stewie',
  'reachy',
  'jeeves',
  'atlas',
  'nova',
  'oriole',
  'pip',
])

function findId(variant: BeeVariant): string | undefined {
  return ROSTER.find((id) => beeSpecForAgent(id).variant === variant)
}

describe('bee spec from agent id', () => {
  it('is deterministic and varies by id', () => {
    expect(beeSpecForAgent('codey')).toEqual(beeSpecForAgent('codey'))
    expect(beeSpecForAgent('codey')).not.toEqual(beeSpecForAgent('stewie'))
    expect(BEE_VARIANTS).toContain(beeSpecForAgent('codey').variant)
    expect(BEE_ACCENTS).toContain(beeSpecForAgent('codey').accent)
    expect(BEE_ACCESSORIES).toContain(beeSpecForAgent('codey').accessory)
  })

  it('assigns both locked variants across a roster', () => {
    const variants = new Set(ROSTER.map((id) => beeSpecForAgent(id).variant))
    expect(variants.has('side-on')).toBe(true)
    expect(variants.has('face-only')).toBe(true)
  })

  it('covers every pack variant, accent, and accessory', () => {
    expect(BEE_VARIANTS).toHaveLength(6)
    expect(BEE_ACCENTS).toHaveLength(6)
    expect(BEE_ACCESSORIES).toHaveLength(4)
    const variants = new Set(ROSTER.map((id) => beeSpecForAgent(id).variant))
    const accents = new Set(ROSTER.map((id) => beeSpecForAgent(id).accent))
    const accessories = new Set(ROSTER.map((id) => beeSpecForAgent(id).accessory))
    for (const variant of BEE_VARIANTS) {
      expect(variants.has(variant)).toBe(true)
    }
    for (const accent of BEE_ACCENTS) {
      expect(accents.has(accent)).toBe(true)
    }
    for (const accessory of BEE_ACCESSORIES) {
      expect(accessories.has(accessory)).toBe(true)
    }
  })

  it('keeps face-only rest gaze aside and wander inside the sclera', () => {
    const face = findId('face-only')
    expect(face).toBeDefined()
    const spec = beeSpecForAgent(face as string)
    expect(Math.abs(spec.rest.x)).toBeGreaterThan(1)
    expect(spec.gaze === 'left' || spec.gaze === 'right').toBe(true)
    expect(isFaceBeeVariant(spec.variant)).toBe(true)
    const later = wanderBeeEyePose(spec, 4.5)
    expect(later.x).not.toBe(spec.rest.x)
    expect(Math.abs(later.x)).toBeLessThanOrEqual(2.4)
    expect(Math.abs(later.y)).toBeLessThanOrEqual(2.4)
  })
})

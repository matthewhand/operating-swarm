/**
 * #523 — pinned team tiles render a graduated avatar stack: the most
 * recently active member first (largest), roster order when there is no
 * activity. Component-level contract for the AgentSidebar pin grid.
 */
import { describe, expect, it } from 'vitest'
import { orderedFacesByRecency, pinStackSizes, type StackFace } from '../../lib/avatarStack'

const roster: StackFace[] = [
  { id: 'codey', name: 'Codey', startedAt: 1000 },
  { id: 'stewie', name: 'Stewie', startedAt: 9000 },
  { id: 'ada', name: 'Ada', startedAt: 4000 },
]

describe('pin team stack contract (#523)', () => {
  it('front face is the most recently active member', () => {
    const ordered = orderedFacesByRecency(roster)
    expect(ordered[0].id).toBe('stewie')
  })

  it('depth order is recency-descending', () => {
    expect(orderedFacesByRecency(roster).map((f) => f.id)).toEqual(['stewie', 'ada', 'codey'])
  })

  it('sizes descend front-to-back', () => {
    const sizes = pinStackSizes(3)
    expect(sizes[0]).toBeGreaterThan(sizes[1])
    expect(sizes[1]).toBeGreaterThan(sizes[2])
  })

  it('idle teams keep roster order (First default)', () => {
    const idle: StackFace[] = [
      { id: 'a', startedAt: 0 },
      { id: 'b', startedAt: 0 },
    ]
    expect(orderedFacesByRecency(idle).map((f) => f.id)).toEqual(['a', 'b'])
  })
})

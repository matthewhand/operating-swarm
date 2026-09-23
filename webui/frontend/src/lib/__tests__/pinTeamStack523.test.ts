/**
 * #523 — the pinned team tile's avatar stack is recency-driven:
 * the most recently active member renders largest (front), remaining members
 * step down in size per depth, and with no activity the ordering falls back
 * to the chat stacking preference (default First = roster order).
 */
import { describe, expect, it } from 'vitest'
import {
  orderedFacesByRecency,
  pinStackSizes,
  PIN_STACK_BASE_PX,
  PIN_STACK_STEP_PX,
  type StackFace,
} from '../avatarStack'

function face(id: string, startedAt: number): StackFace {
  return { id, name: id, startedAt }
}

describe('#523 orderedFacesByRecency', () => {
  it('orders most-recently-active first', () => {
    const faces = [face('a', 1000), face('b', 3000), face('c', 2000)]
    expect(orderedFacesByRecency(faces).map((f) => f.id)).toEqual(['b', 'c', 'a'])
  })

  it('falls back to roster order (First) when there is no activity', () => {
    const faces = [face('a', 0), face('b', 0), face('c', 0)]
    expect(orderedFacesByRecency(faces, 'first').map((f) => f.id)).toEqual(['a', 'b', 'c'])
  })

  it('respects the Last stacking preference when idle', () => {
    const faces = [face('a', 0), face('b', 0), face('c', 0)]
    expect(orderedFacesByRecency(faces, 'last').map((f) => f.id)).toEqual(['c', 'b', 'a'])
  })

  it('does not mutate the input array', () => {
    const faces = [face('a', 1000), face('b', 3000)]
    orderedFacesByRecency(faces)
    expect(faces.map((f) => f.id)).toEqual(['a', 'b'])
  })
})

describe('#523 pinStackSizes', () => {
  it('descends front-to-back with the most recent member largest', () => {
    const sizes = pinStackSizes(3)
    expect(sizes).toEqual([
      PIN_STACK_BASE_PX,
      PIN_STACK_BASE_PX - PIN_STACK_STEP_PX,
      PIN_STACK_BASE_PX - 2 * PIN_STACK_STEP_PX,
    ])
    expect(Math.min(...sizes)).toBeGreaterThan(0)
  })

  it('returns one size for a single face', () => {
    expect(pinStackSizes(1)).toEqual([PIN_STACK_BASE_PX])
  })
})

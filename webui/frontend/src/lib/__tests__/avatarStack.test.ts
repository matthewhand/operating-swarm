import { describe, expect, it } from 'vitest'
import {
  STACK_FACE_LIMIT,
  TEAM_STACK_ALL_MAX,
  TEAM_STACK_FACE_LIMIT,
  STACK_PULSE_MS,
  isAvatarStack,
  parseStartedAt,
  selectStackedFaces,
  stackAnimationDelayMs,
  teamSidepaneStack,
  type StackFace,
} from '../avatarStack'

function face(id: string, startedAt: number): StackFace {
  return { id, name: id, startedAt }
}

describe('avatarStack', () => {
  it('caps at 3 faces plus a remainder so #398 can reuse the same plan', () => {
    const five = [1, 2, 3, 4, 5].map((n) => face(`m${n}`, n * 100))
    const plan = selectStackedFaces(five)
    expect(STACK_FACE_LIMIT).toBe(3)
    expect(plan.faces).toHaveLength(3)
    expect(plan.remainder).toBe(2)
    expect(plan.faces.map((row) => row.id)).toEqual(['m5', 'm4', 'm3'])
  })

  it('caps team stacks at TEAM_STACK_FACE_LIMIT (2) with remainder for extras', () => {
    const four = [1, 2, 3, 4].map((n) => face(`m${n}`, n * 100))
    expect(TEAM_STACK_FACE_LIMIT).toBe(2)
    const plan = selectStackedFaces(four, TEAM_STACK_FACE_LIMIT)
    expect(plan.faces).toHaveLength(2)
    expect(plan.remainder).toBe(2)
    expect(plan.faces.map((row) => row.id)).toEqual(['m4', 'm3'])
  })

  it('teamSidepaneStack: 1–3 members show all faces; 4+ show 2 + N', () => {
    expect(TEAM_STACK_ALL_MAX).toBe(3)
    expect(TEAM_STACK_FACE_LIMIT).toBe(2)

    const one = teamSidepaneStack([face('m1', 100)])
    expect(one.faces.map((f) => f.id)).toEqual(['m1'])
    expect(one.remainder).toBe(0)

    const two = teamSidepaneStack([1, 2].map((n) => face(`m${n}`, n * 100)))
    expect(two.faces.map((f) => f.id)).toEqual(['m1', 'm2'])
    expect(two.remainder).toBe(0)

    const three = teamSidepaneStack([1, 2, 3].map((n) => face(`m${n}`, n * 100)))
    expect(three.faces.map((f) => f.id)).toEqual(['m1', 'm2', 'm3'])
    expect(three.remainder).toBe(0)

    const four = teamSidepaneStack([1, 2, 3, 4].map((n) => face(`m${n}`, n * 100)))
    expect(four.faces.map((f) => f.id)).toEqual(['m1', 'm2'])
    expect(four.remainder).toBe(2)

    const five = teamSidepaneStack([1, 2, 3, 4, 5].map((n) => face(`m${n}`, n * 100)))
    // Roster order preserved — first 2 members, not most-recent.
    expect(five.faces.map((f) => f.id)).toEqual(['m1', 'm2'])
    expect(five.remainder).toBe(3)
  })

  it('staggers animation delay by startedAt so four faces do not lockstep', () => {
    const startedAt = [1_000, 1_200, 1_400, 1_600]
    const delays = startedAt.map((value) => stackAnimationDelayMs(value, startedAt[0]))
    expect(delays).toEqual([0, 200, 400, 600])
    expect(new Set(delays).size).toBe(4)
    expect(delays.every((ms) => ms < STACK_PULSE_MS)).toBe(true)
  })

  it('treats a single face with no remainder as not a stack', () => {
    expect(isAvatarStack(1, 0)).toBe(false)
    expect(isAvatarStack(2, 0)).toBe(true)
    expect(isAvatarStack(1, 1)).toBe(true)
  })

  it('parses startedAt from a number, ISO string, or fallback index', () => {
    expect(parseStartedAt(1500, 9)).toBe(1500)
    expect(parseStartedAt('2020-01-01T00:00:00.000Z', 9)).toBe(Date.parse('2020-01-01T00:00:00.000Z'))
    expect(parseStartedAt(undefined, 4)).toBe(4)
  })
})

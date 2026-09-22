import { describe, expect, it } from 'vitest'
import {
  STACK_FACE_LIMIT,
  TEAM_STACK_FACE_LIMIT,
  STACK_PULSE_MS,
  isAvatarStack,
  teamChatFaceStack,
  parseStartedAt,
  selectStackedFaces,
  stackAnimationDelayMs,
  teamSidepaneStack,
  markStackWorking,
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

  it('#438: teamChatFaceStack keeps the chat target and counts the rest from the roster', () => {
    const five = [1, 2, 3, 4, 5].map((n) => face(`m${n}`, n * 100))
    // The remainder is the roster minus the one face — never the capped list
    // length, which would report +2 for a 5-member team.
    expect(teamChatFaceStack(five, 'm3').remainder).toBe(4)
    expect(teamChatFaceStack(five, 'm3').face?.id).toBe('m3')
    // #791: with no target, the MOST RECENTLY ACTIVE member leads.
    expect(teamChatFaceStack(five).face?.id).toBe('m5')
  })

  it('#438: teamChatFaceStack never invents a member', () => {
    const faces = [face('m1', 100), face('m2', 200)]
    // A stale chat-target id falls back to the most recent real face (#791)…
    expect(teamChatFaceStack(faces, 'ghost').face?.id).toBe('m2')
    expect(teamChatFaceStack(faces, '  ').face?.id).toBe('m2')
    // …and an empty roster yields no face at all rather than a placeholder.
    expect(teamChatFaceStack([], 'm1').face).toBeNull()
    expect(teamChatFaceStack([], 'm1').remainder).toBe(0)
  })

  it('#438: teamChatFaceStack matches on agentId too, and a one-member team has no remainder', () => {
    const faces = [{ ...face('m1', 100), agentId: 'blueprint-1' }, face('m2', 200)]
    expect(teamChatFaceStack(faces, 'blueprint-1').face?.id).toBe('m1')
    expect(teamChatFaceStack([face('only', 1)], 'only').remainder).toBe(0)
  })

  it('teamSidepaneStack (REQ-891): shows at most 3 faces with no remainder chip; preserves roster order when idle', () => {
    expect(STACK_FACE_LIMIT).toBe(3)

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
    expect(four.faces.map((f) => f.id)).toEqual(['m1', 'm2', 'm3'])
    expect(four.remainder).toBe(0)

    const five = teamSidepaneStack([1, 2, 3, 4, 5].map((n) => face(`m${n}`, n * 100)))
    // Roster order preserved when idle — first 3 members, no remainder (+N) chip
    expect(five.faces.map((f) => f.id)).toEqual(['m1', 'm2', 'm3'])
    expect(five.remainder).toBe(0)
  })

  it('teamSidepaneStack (REQ-891): orders faces most-recently-active first (startedAt desc) when anyWorking is true', () => {
    const five = [
      face('m1', 100),
      face('m2', 200),
      face('m3', 500),
      face('m4', 300),
      face('m5', 400),
    ]
    const working = teamSidepaneStack(five, true)
    // Most recent startedAt desc: m3 (500), m5 (400), m4 (300)
    expect(working.faces.map((f) => f.id)).toEqual(['m3', 'm5', 'm4'])
    expect(working.remainder).toBe(0)

    // Also orders by startedAt desc when individual face has working: true without passing explicit anyWorking
    const withWorkingFace = [
      face('m1', 100),
      { ...face('m2', 200), working: true },
      face('m3', 500),
    ]
    const autoWorking = teamSidepaneStack(withWorkingFace)
    expect(autoWorking.faces.map((f) => f.id)).toEqual(['m3', 'm2', 'm1'])
    expect(autoWorking.remainder).toBe(0)
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

  it('#432 markStackWorking flags faces whose id is running', () => {
    const faces = [face('ada', 1), face('bea', 2)]
    const marked = markStackWorking(faces, (id) => id === 'bea')
    expect(marked.anyWorking).toBe(true)
    expect(marked.faces.map((row) => row.working)).toEqual([false, true])
    expect(markStackWorking(faces, () => false).anyWorking).toBe(false)
  })

  it('parses startedAt from a number, ISO string, or fallback index', () => {
    expect(parseStartedAt(1500, 9)).toBe(1500)
    expect(parseStartedAt('2020-01-01T00:00:00.000Z', 9)).toBe(Date.parse('2020-01-01T00:00:00.000Z'))
    expect(parseStartedAt(undefined, 4)).toBe(4)
  })
})

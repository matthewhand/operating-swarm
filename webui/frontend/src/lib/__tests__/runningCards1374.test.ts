/**
 * #1374 Phase B — Running card models (open href + display list).
 */
import { describe, expect, it } from 'vitest'
import { applyTurnFrame, type TurnSnapshot } from '../agentTurns'
import {
  hrefForRunningAgent,
  labelForRunningAgent,
  openIdForRunningAgent,
  runningCardsForDisplay,
  turnBelongsToSeat,
} from '../runningCards'

const started = (turnId: string, agentId: string) =>
  ({ kind: 'turn_started' as const, turnId, agentId })

describe('openIdForRunningAgent', () => {
  it('strips a team-member lock key down to the member seat', () => {
    expect(openIdForRunningAgent('moa#panelist')).toBe('panelist')
    expect(openIdForRunningAgent('team:office#codey')).toBe('codey')
  })

  it('leaves a plain seat id intact', () => {
    expect(openIdForRunningAgent('codey')).toBe('codey')
    expect(openIdForRunningAgent('blueprint:codey')).toBe('codey')
  })
})

describe('hrefForRunningAgent / labelForRunningAgent', () => {
  it('opens the member seat, not the team lock key', () => {
    expect(hrefForRunningAgent('moa#codey')).toBe('/chat?blueprint=codey')
  })

  it('prefers a published name, then fallback, then the open id', () => {
    expect(labelForRunningAgent('moa#codey', { codey: 'Codey' })).toBe('Codey')
    expect(labelForRunningAgent('ghost', {}, 'Working agent')).toBe('Working agent')
    expect(labelForRunningAgent('ghost', {})).toBe('ghost')
  })
})

describe('runningCardsForDisplay', () => {
  it('is empty when the capability is off — #1371 row stays', () => {
    let snap: TurnSnapshot = {}
    snap = applyTurnFrame(snap, started('t1', 'codey'))
    expect(
      runningCardsForDisplay({
        enabled: false,
        snapshot: snap,
        activeAgentId: 'codey',
        awaitingAssistant: true,
      }),
    ).toEqual([])
  })

  it('emits one card per running turn when the capability is on', () => {
    let snap: TurnSnapshot = {}
    snap = applyTurnFrame(snap, started('t1', 'codey'))
    snap = applyTurnFrame(snap, started('t2', 'stewie'))
    const cards = runningCardsForDisplay({
      enabled: true,
      snapshot: snap,
      activeAgentId: 'codey',
      names: { codey: 'Codey', stewie: 'Stewie' },
    })
    expect(cards).toHaveLength(2)
    expect(cards[0]).toMatchObject({
      agentId: 'codey',
      turnId: 't1',
      name: 'Codey',
      current: true,
      href: '/chat?blueprint=codey',
    })
    expect(cards[1]).toMatchObject({
      agentId: 'stewie',
      turnId: 't2',
      name: 'Stewie',
      current: false,
      href: '/chat?blueprint=stewie',
    })
  })

  it('synthesises a card while awaiting a first token with no bookend', () => {
    const cards = runningCardsForDisplay({
      enabled: true,
      snapshot: {},
      activeAgentId: 'codey',
      awaitingAssistant: true,
      fallbackName: 'Codey',
    })
    expect(cards).toHaveLength(1)
    expect(cards[0]).toMatchObject({
      agentId: 'codey',
      name: 'Codey',
      current: true,
    })
    expect(cards[0].turnId).toBeUndefined()
  })

  it('does not duplicate the active agent when a bookend already exists', () => {
    let snap: TurnSnapshot = {}
    snap = applyTurnFrame(snap, started('t1', 'codey'))
    const cards = runningCardsForDisplay({
      enabled: true,
      snapshot: snap,
      activeAgentId: 'codey',
      awaitingAssistant: true,
    })
    expect(cards).toHaveLength(1)
    expect(cards[0].turnId).toBe('t1')
  })

  it('does not label an unnamed sibling with the seat on screen', () => {
    let snap: TurnSnapshot = {}
    snap = applyTurnFrame(snap, started('t1', 'codey'))
    snap = applyTurnFrame(snap, started('t2', 'ghost'))
    const cards = runningCardsForDisplay({
      enabled: true,
      snapshot: snap,
      activeAgentId: 'codey',
      fallbackName: 'Codey',
    })
    expect(cards.map((card) => card.name)).toEqual(['Codey', 'ghost'])
  })

  it('does not add a phantom team card while a member turn is already running', () => {
    let snap: TurnSnapshot = {}
    snap = applyTurnFrame(snap, started('t1', 'demo-team#codey'))
    const cards = runningCardsForDisplay({
      enabled: true,
      snapshot: snap,
      activeAgentId: 'team:demo-team',
      awaitingAssistant: true,
      fallbackName: 'Demo Rig',
    })
    expect(cards).toHaveLength(1)
    expect(cards[0]).toMatchObject({ agentId: 'demo-team#codey', turnId: 't1', name: 'codey' })
    expect(turnBelongsToSeat('demo-team#codey', 'team:demo-team')).toBe(true)
    expect(turnBelongsToSeat('stewie', 'codey')).toBe(false)
  })
})

/**
 * ADR-017 PR-2 — the SPA-side turn registry pins.
 */
import { describe, expect, it } from 'vitest'
import {
  activeTurnFor,
  applyTurnFrame,
  stopLabelFor,
  type TurnSnapshot,
} from '../agentTurns'

const started = (turnId: string, agentId: string) =>
  ({ kind: 'turn_started', turnId, agentId }) as const
const finished = (turnId: string, agentId: string) =>
  ({ kind: 'turn_finished', turnId, agentId }) as const

describe('applyTurnFrame', () => {
  it('registers a running turn from turn_started', () => {
    const snap = applyTurnFrame({}, started('t1', 'jeeves'))
    expect(snap['t1']).toEqual({ turnId: 't1', agentId: 'jeeves', state: 'running' })
  })

  it('marks the turn finished, keeping identity', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, finished('t1', 'jeeves'))
    expect(snap['t1']).toEqual({ turnId: 't1', agentId: 'jeeves', state: 'finished' })
  })

  it('keeps other agents turns untouched by one finish', () => {
    let snap = applyTurnFrame({}, started('t1', 'a'))
    snap = applyTurnFrame(snap, started('t2', 'b'))
    snap = applyTurnFrame(snap, finished('t1', 'a'))
    expect(snap['t2'].state).toBe('running')
  })

  it('ignores turn_finished for an unknown turn', () => {
    const snap: TurnSnapshot = {}
    expect(applyTurnFrame(snap, finished('ghost', 'x'))).toBe(snap)
  })
})

describe('activeTurnFor', () => {
  it('finds the running turn of the requested agent', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, started('t2', 'moa'))
    expect(activeTurnFor(snap, 'moa')?.turnId).toBe('t2')
  })

  it('returns null once that agent only has finished turns', () => {
    let snap = applyTurnFrame({}, started('t1', 'jeeves'))
    snap = applyTurnFrame(snap, finished('t1', 'jeeves'))
    expect(activeTurnFor(snap, 'jeeves')).toBeNull()
  })

  it('is empty before any bookend arrives (bookends are optional protocol)', () => {
    expect(activeTurnFor({}, 'jeeves')).toBeNull()
  })
})

describe('stopLabelFor', () => {
  it('names the scoped contract when a live turn exists', () => {
    const snap = applyTurnFrame({}, started('t1', 'jeeves'))
    expect(stopLabelFor(activeTurnFor(snap, 'jeeves'))).toContain('other turns keep running')
  })
})

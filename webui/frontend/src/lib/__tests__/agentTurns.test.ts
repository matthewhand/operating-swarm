/**
 * ADR-017 PR-2 — the SPA-side turn registry pins.
 */
import { beforeEach, afterEach, describe, expect, it } from 'vitest'
import {
  activeTurnFor,
  applyTurnFrame,
  getTurnSnapshot,
  isAgentTurnActive,
  recordTurnFrame,
  resetTurnRegistry,
  stopLabelFor,
  subscribeAgentTurns,
  AGENT_TURNS_EVENT,
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

describe('global registry and subscription (#1118)', () => {
  beforeEach(() => {
    resetTurnRegistry()
  })

  afterEach(() => {
    resetTurnRegistry()
  })

  it('records turn_started and turn_finished into the registry and drives isAgentTurnActive', () => {
    expect(isAgentTurnActive('jeeves')).toBe(false)
    recordTurnFrame(started('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(true)
    expect(getTurnSnapshot()['t1']).toEqual({
      turnId: 't1',
      agentId: 'jeeves',
      state: 'running',
    })

    recordTurnFrame(finished('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(false)
    expect(getTurnSnapshot()['t1']?.state).toBe('finished')
  })

  it('supports single-argument applyTurnFrame to update the global registry', () => {
    expect(isAgentTurnActive('codey')).toBe(false)
    applyTurnFrame(started('t2', 'codey'))
    expect(isAgentTurnActive('codey')).toBe(true)
    applyTurnFrame(finished('t2', 'codey'))
    expect(isAgentTurnActive('codey')).toBe(false)
  })

  it('resolves isAgentTurnActive with or without scoped prefix', () => {
    recordTurnFrame(started('t1', 'jeeves'))
    expect(isAgentTurnActive('jeeves')).toBe(true)
    expect(isAgentTurnActive('agent:jeeves')).toBe(true)
    expect(isAgentTurnActive('blueprint:jeeves')).toBe(true)
    expect(isAgentTurnActive('other')).toBe(false)
  })

  it('notifies listeners when a turn starts and finishes', () => {
    const history: TurnSnapshot[] = []
    const unsub = subscribeAgentTurns((snap) => {
      history.push(snap)
    })

    recordTurnFrame(started('t1', 'jeeves'))
    expect(history.length).toBe(1)
    expect(history[0]['t1']?.state).toBe('running')

    recordTurnFrame(finished('t1', 'jeeves'))
    expect(history.length).toBe(2)
    expect(history[1]['t1']?.state).toBe('finished')

    unsub()
    recordTurnFrame(started('t2', 'moa'))
    expect(history.length).toBe(2)
  })

  it('dispatches AGENT_TURNS_EVENT window event on update', () => {
    const events: TurnSnapshot[] = []
    const onEvent = (e: Event) => {
      events.push((e as CustomEvent<TurnSnapshot>).detail)
    }
    window.addEventListener(AGENT_TURNS_EVENT, onEvent)

    recordTurnFrame(started('t1', 'jeeves'))
    expect(events.length).toBe(1)
    expect(events[0]['t1']?.state).toBe('running')

    window.removeEventListener(AGENT_TURNS_EVENT, onEvent)
  })
})

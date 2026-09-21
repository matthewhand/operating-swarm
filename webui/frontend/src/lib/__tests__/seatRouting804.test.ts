/**
 * #804 — cross-kind routing picks must land on a real seat.
 *
 * The seat URL vocabulary is `?blueprint=` (api seats, incl. the api_agent
 * gateway), `?cli=` (host CLI seats), `?remote=` and `?team=`. Nothing reads
 * `?agent=` — yet cross-kind picks used to write exactly that dead param, and
 * the two-stage picker dropped API picks from non-API seats entirely.
 */
import { describe, expect, it } from 'vitest'
import {
  hydrateSeatFromSearchParams,
  seatParamsForPick,
  seatToSearchParams,
} from '../seatRouting'

describe('seatParamsForPick (#804)', () => {
  it('routes a CLI pick to ?cli= (the seat ChatPage actually resolves)', () => {
    expect(seatParamsForPick('cli', 'codex')).toEqual({
      set: { cli: 'codex' },
      delete: ['blueprint', 'remote', 'team', 'session', 'model'],
    })
  })

  it('routes an API pick to ?blueprint=api_agent — never an inert drop', () => {
    expect(seatParamsForPick('api', '')).toEqual({
      set: { blueprint: 'api_agent' },
      delete: ['cli', 'remote', 'team', 'session', 'model'],
    })
    expect(seatParamsForPick('api', 'support')).toEqual({
      set: { blueprint: 'support' },
      delete: ['cli', 'remote', 'team', 'session', 'model'],
    })
  })

  it('routes a remote pick to ?remote=', () => {
    expect(seatParamsForPick('remote', 'trueforge-max')).toEqual({
      set: { remote: 'trueforge-max' },
      delete: ['blueprint', 'cli', 'team', 'session', 'model'],
    })
  })

  it('routes a team pick to ?team=', () => {
    expect(seatParamsForPick('team', 'ba_eng_tester')).toEqual({
      set: { team: 'ba_eng_tester' },
      delete: ['blueprint', 'cli', 'remote', 'session', 'model'],
    })
  })

  it('clears the stale seat params of every other kind', () => {
    // Switching CLI → CLI id keeps ?cli= fresh; a leftover ?session= from the
    // previous seat must go (session bleed, #804 requirement 3).
    const patch = seatParamsForPick('cli', 'grok')
    expect(patch.delete).toContain('session')
    expect(patch.set).toEqual({ cli: 'grok' })
  })

  it('a gateway profile pick lands on api_agent with the profile as model', () => {
    // Stage 2 of "API gateway → Claude Work": the gateway is the seat, the
    // profile rides ?model= which applyApiRoutingChange understands.
    const patch = seatParamsForPick('api', '', { apiModel: 'claude-work' })
    expect(patch.set).toEqual({ blueprint: 'api_agent', model: 'claude-work' })
    expect(patch.delete).toEqual(['cli', 'remote', 'team', 'session'])
  })

  it('a non-api pick clears a leftover ?model= (no bleed)', () => {
    const patch = seatParamsForPick('cli', 'codex')
    expect(patch.delete).toContain('model')
  })
})

// #815 — canonical SeatKind/SeatDescriptor + atomic hydrate/serialize.
describe('#815 canonical seat identity', () => {
  it('hydrates every seat kind from search params', () => {
    expect(hydrateSeatFromSearchParams(new URLSearchParams('blueprint=jeeves'))).toEqual({
      kind: 'api',
      id: 'jeeves',
    })
    expect(hydrateSeatFromSearchParams(new URLSearchParams('cli=grok'))).toEqual({
      kind: 'cli',
      id: 'grok',
    })
    expect(hydrateSeatFromSearchParams(new URLSearchParams('remote=omb'))).toEqual({
      kind: 'remote',
      id: 'omb',
    })
    expect(hydrateSeatFromSearchParams(new URLSearchParams('team=office'))).toEqual({
      kind: 'team',
      id: 'office',
    })
    expect(hydrateSeatFromSearchParams(new URLSearchParams(''))).toBeNull()
  })

  it('legacy ?agent= hydrates as an api seat', () => {
    expect(hydrateSeatFromSearchParams(new URLSearchParams('agent=jeeves'))).toEqual({
      kind: 'api',
      id: 'jeeves',
    })
  })

  it('seatToSearchParams atomically sets one kind and wipes the rest', () => {
    const seen: { set: Record<string, string>; delete: string[] } = { set: {}, delete: [] }
    seatToSearchParams({ kind: 'cli', id: 'grok' }, (set, deleteKeys) => {
      seen.set = set
      seen.delete = deleteKeys
    })
    expect(seen.set).toEqual({ cli: 'grok' })
    expect(seen.delete).toEqual(expect.arrayContaining(['blueprint', 'remote', 'team', 'agent']))
    expect(seen.delete).not.toContain('cli')
  })

  it('api gateway picks keep the model; other kinds drop it', () => {
    const seen: { set: Record<string, string>; delete: string[] } = { set: {}, delete: [] }
    seatToSearchParams({ kind: 'api', id: 'api_agent', model: 'claude-work' }, (set, deleteKeys) => {
      seen.set = set
      seen.delete = deleteKeys
    })
    expect(seen.set).toEqual({ blueprint: 'api_agent', model: 'claude-work' })
    expect(seen.delete).toContain('session')
  })
})

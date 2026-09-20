/**
 * #804 — cross-kind routing picks must land on a real seat.
 *
 * The seat URL vocabulary is `?blueprint=` (api seats, incl. the api_agent
 * gateway), `?cli=` (host CLI seats), `?remote=` and `?team=`. Nothing reads
 * `?agent=` — yet cross-kind picks used to write exactly that dead param, and
 * the two-stage picker dropped API picks from non-API seats entirely.
 */
import { describe, expect, it } from 'vitest'
import { seatParamsForPick } from '../seatRouting'

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

/**
 * #1793 — remote thread identity + thread-load phase.
 *
 * Two contracts this file pins:
 *
 * 1. `remoteThreadId` is the ONLY remote conversation-id derivation. First
 *    mount, render key and hydrate request all call it, so they cannot drift.
 *    Params are trimmed: an untrimmed `?session=` used to mint
 *    `remote-<remote>- ` and address a conversation that does not exist.
 * 2. `threadLoadPhase` never lets "no rows on screen" mean two different
 *    things. A blank transcript while loading and a genuinely empty
 *    conversation are different states, and an error is never an empty thread.
 */
import { describe, expect, it } from 'vitest'
import {
  THREAD_LOADING_LABEL,
  THREAD_STALE_LABEL,
  remoteThreadId,
  threadLoadPhase,
} from '../threadLoadState'

describe('#1793 remoteThreadId', () => {
  it('derives the bare remote id when no session is pinned', () => {
    expect(remoteThreadId('trueforge-2')).toBe('remote-trueforge-2')
    expect(remoteThreadId('trueforge-2', '')).toBe('remote-trueforge-2')
    expect(remoteThreadId('trueforge-2', null)).toBe('remote-trueforge-2')
  })

  it('appends the session so a pinned session keeps its own thread', () => {
    expect(remoteThreadId('trueforge-2', 'sess-9')).toBe('remote-trueforge-2-sess-9')
  })

  it('trims both params so a whitespace-only session cannot re-key the thread', () => {
    // The untrimmed form minted `remote-trueforge-2- ` — a conversation with
    // no rows, which is exactly how a thread reads as "gone".
    expect(remoteThreadId(' trueforge-2 ', '   ')).toBe('remote-trueforge-2')
    expect(remoteThreadId(' trueforge-2 ', ' sess-9 ')).toBe('remote-trueforge-2-sess-9')
  })

  it('is stable: the same inputs always give the same id', () => {
    const first = remoteThreadId('trueforge-2', 'sess-9')
    const second = remoteThreadId('trueforge-2', 'sess-9')
    expect(second).toBe(first)
  })
})

describe('#1793 threadLoadPhase', () => {
  it('loading with no cached copy is loading-empty, never empty', () => {
    expect(
      threadLoadPhase({ threadReady: false, messageCount: 0, hydrateError: null }),
    ).toBe('loading-empty')
  })

  it('loading with rows on screen is loading-stale (the cached copy)', () => {
    expect(
      threadLoadPhase({ threadReady: false, messageCount: 13, hydrateError: null }),
    ).toBe('loading-stale')
  })

  it('a failed load is an error whether or not a copy is on screen', () => {
    expect(threadLoadPhase({ threadReady: true, messageCount: 0, hydrateError: 'boom' })).toBe(
      'error',
    )
    expect(threadLoadPhase({ threadReady: true, messageCount: 4, hydrateError: 'boom' })).toBe(
      'error',
    )
  })

  it('only a settled, successful, genuinely empty thread is empty', () => {
    expect(threadLoadPhase({ threadReady: true, messageCount: 0, hydrateError: null })).toBe(
      'empty',
    )
  })

  it('a settled load with rows is ready', () => {
    expect(
      threadLoadPhase({ threadReady: true, messageCount: 13, hydrateError: null }),
    ).toBe('ready')
  })

  it('an error recorded while still loading does not claim to be an error yet', () => {
    // Loading wins: the operator is told it is loading, and the error is shown
    // when the request settles. Never a half-state.
    expect(
      threadLoadPhase({ threadReady: false, messageCount: 0, hydrateError: 'boom' }),
    ).toBe('loading-empty')
    expect(
      threadLoadPhase({ threadReady: false, messageCount: 2, hydrateError: 'boom' }),
    ).toBe('loading-stale')
  })

  it('carries spoken labels for both loading surfaces', () => {
    expect(THREAD_LOADING_LABEL.length).toBeGreaterThan(0)
    expect(THREAD_STALE_LABEL).toMatch(/previous copy/i)
    expect(THREAD_STALE_LABEL).toMatch(/disabled/i)
  })
})

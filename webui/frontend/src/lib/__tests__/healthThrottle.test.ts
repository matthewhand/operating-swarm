/**
 * #1783 — the shared 429 gate.
 *
 * The rule under test is short and load-bearing: a poll that is told to slow
 * down goes quiet for the server's advertised window instead of retrying into
 * it. The gate is a plain object with an injectable clock precisely so these
 * cases can be stated as numbers rather than as wall-clock waiting.
 */
import { describe, expect, it } from 'vitest'
import { ApiError, ApiThrottleError } from '../api'
import {
  DEFAULT_THROTTLE_WAIT_MS,
  MAX_THROTTLE_WAIT_MS,
  createThrottleGate,
} from '../healthThrottle'

const T0 = 1_700_000_000_000
/** A 429 as `classifyApiError` builds it, with an explicit Retry-After. */
const throttled = (seconds: number) =>
  new ApiThrottleError(429, 'Too many requests — the server is busy.', seconds)

describe('#1783 throttle gate', () => {
  it('starts open', () => {
    const gate = createThrottleGate()
    expect(gate.paused(T0)).toBe(false)
    expect(gate.remainingMs(T0)).toBe(0)
  })

  it('an error that is not a 429 changes nothing', () => {
    const gate = createThrottleGate()
    expect(gate.note(new ApiError(500, 'boom'), T0)).toBe(0)
    expect(gate.note(new Error('network'), T0)).toBe(0)
    expect(gate.paused(T0)).toBe(false)
  })

  it("honours the server's Retry-After", () => {
    const gate = createThrottleGate()
    expect(gate.note(throttled(2), T0)).toBe(2_000)
    expect(gate.paused(T0)).toBe(true)
    expect(gate.paused(T0 + 1_999)).toBe(true)
    expect(gate.paused(T0 + 2_000)).toBe(false)
    expect(gate.remainingMs(T0 + 1_000)).toBe(1_000)
  })

  it('falls back to the 2s the server quotes, doubling per consecutive 429', () => {
    const gate = createThrottleGate()
    expect(gate.note(throttled(0), T0)).toBe(DEFAULT_THROTTLE_WAIT_MS)
    // A second 429 inside that window extends it — a client that waited the
    // advertised time and was throttled again needs more patience.
    expect(gate.note(throttled(0), T0 + 1_000)).toBe(DEFAULT_THROTTLE_WAIT_MS * 2)
    expect(gate.paused(T0 + 2_500)).toBe(true)
    expect(gate.paused(T0 + 5_000)).toBe(false)
    expect(gate.note(throttled(0), T0 + 6_000)).toBe(DEFAULT_THROTTLE_WAIT_MS * 4)
  })

  it('caps the GUESS, so a poll always comes back on its own', () => {
    const gate = createThrottleGate()
    let finalWait = 0
    for (let i = 0; i < 12; i += 1) finalWait = gate.note(throttled(0), T0)
    expect(finalWait).toBe(MAX_THROTTLE_WAIT_MS)
  })

  it('honours an advertised wait longer than the guess cap', () => {
    // The server's number is the server's number: capping it would be the
    // client overruling the quota that just rejected it.
    const gate = createThrottleGate()
    expect(gate.note(throttled(3_600), T0)).toBe(3_600_000)
    expect(gate.paused(T0 + 3_599_000)).toBe(true)
    expect(gate.paused(T0 + 3_600_000)).toBe(false)
  })

  it('a success clears the streak and the pause', () => {
    const gate = createThrottleGate()
    gate.note(throttled(0), T0)
    gate.note(throttled(0), T0 + 1_000)
    gate.noteSuccess()

    expect(gate.paused(T0 + 1_100)).toBe(false)
    // Back to the 2s floor rather than the doubled wait the streak had reached.
    expect(gate.note(throttled(0), T0 + 1_100)).toBe(DEFAULT_THROTTLE_WAIT_MS)
  })
})

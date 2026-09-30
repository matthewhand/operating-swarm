/**
 * #1658 follow-up — a broken seat is labelled broken, everywhere, and only
 * when it really is.
 *
 * Contract pinned here:
 *  - `agentLabel` decorates with `⚠ broken` when the seat has an explicit
 *    `broken` verdict (rail rows, navbar, pickers, composer, search — all flow
 *    through this one funnel)
 *  - healthy and not-yet-probed seats keep their exact name
 *  - a failed status poll does NOT mark a seat broken (a flaky poll must never
 *    rename a working agent)
 *  - a real turn failure marks it broken; a later turn success or a good probe
 *    clears it, so a recovered seat gets its real name back automatically
 *
 * The transport is swapped through the store's own test seam rather than a
 * module mock, so this stays a unit test of the store + label contract.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  BROKEN_SUFFIX,
  __setSeatHealthProber,
  noteTurnFailure,
  noteTurnSuccess,
  refreshSeatHealth,
  resetSeatHealth,
  seatDisplayName,
  seatHealth,
  seatIsBroken,
  subscribeSeatHealth,
  trackSeatHealth,
} from '../seatHealth'
import { agentLabel } from '../supportAgent'

const probeMock = vi.fn()
/** Let the store's promise chain settle. */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

function row(seat_id: string, kind: string, state: string, reason = '') {
  return {
    seat_id,
    kind,
    state,
    reason,
    latency_ms: 1,
    checked_at: Date.now(),
    broken: state === 'broken',
  }
}

describe('#1658 seat health — labels', () => {
  beforeEach(() => {
    resetSeatHealth()
    probeMock.mockReset()
    __setSeatHealthProber((seats) => probeMock(seats))
  })
  afterEach(() => {
    resetSeatHealth()
    __setSeatHealthProber(null)
    vi.useRealTimers()
  })

  it('leaves a healthy seat name exactly as it was', async () => {
    probeMock.mockResolvedValue([row('codey', 'cli', 'ok')])
    trackSeatHealth([{ kind: 'cli', seatId: 'codey' }])
    await flush()
    expect(agentLabel({ id: 'codey', name: 'Codey' })).toBe('Codey')
    expect(seatIsBroken({ kind: 'cli', seatId: 'codey' })).toBe(false)
  })

  it('marks a broken seat in the one funnel every name flows through', async () => {
    probeMock.mockResolvedValue([row('grok', 'cli', 'broken', 'usage balance exhausted')])
    trackSeatHealth([{ kind: 'cli', seatId: 'grok' }])
    await flush()
    // `grok` is a CLI blueprint id, so the label resolves on the cli key.
    expect(agentLabel({ id: 'grok', name: 'Grok' })).toBe(`Grok ${BROKEN_SUFFIX}`)
    expect(seatIsBroken({ kind: 'cli', seatId: 'grok' })).toBe(true)
  })

  it('does not touch a seat that has never been probed', () => {
    expect(agentLabel({ id: 'never-probed', name: 'Fresh' })).toBe('Fresh')
    expect(seatHealth({ kind: 'api', seatId: 'never-probed' }).state).toBe('unknown')
  })

  it('a failed status poll is not evidence a seat is broken', async () => {
    probeMock.mockRejectedValue(new Error('network down'))
    trackSeatHealth([{ kind: 'remote', seatId: 'hermes' }])
    await flush()
    // Still unknown: a flaky poll must never rename a working agent.
    expect(seatHealth({ kind: 'remote', seatId: 'hermes' }).state).toBe('unknown')
  })

  it('a real turn failure marks it broken, and a later turn success clears it', () => {
    const ref = { kind: 'cli', seatId: 'n8n' }
    noteTurnFailure(ref, 'connect ECONNREFUSED')
    expect(seatIsBroken(ref)).toBe(true)
    expect(seatHealth(ref).reason).toBe('connect ECONNREFUSED')

    noteTurnSuccess(ref)
    expect(seatIsBroken(ref)).toBe(false)
  })

  it('a recovered probe un-breaks the seat too', async () => {
    const ref = { kind: 'remote' as const, seatId: 'trueforge' }
    noteTurnFailure(ref, 'upstream 500')
    expect(seatIsBroken(ref)).toBe(true)

    probeMock.mockResolvedValue([row('trueforge', 'remote', 'ok')])
    trackSeatHealth([ref])
    await flush()
    expect(seatIsBroken(ref)).toBe(false)
  })

  it('notifies subscribers so rows re-render without a provider', async () => {
    const seen: number[] = []
    const off = subscribeSeatHealth(() => seen.push(1))
    probeMock.mockResolvedValue([row('codex', 'cli', 'broken', 'exited 1')])
    trackSeatHealth([{ kind: 'cli', seatId: 'codex' }])
    await flush()
    expect(seen.length).toBeGreaterThan(0)
    off()
  })

  it('polls tracked seats on an interval and can refresh on demand', async () => {
    vi.useFakeTimers()
    probeMock.mockResolvedValue([row('agy', 'cli', 'ok')])
    trackSeatHealth([{ kind: 'cli', seatId: 'agy' }])
    expect(probeMock).toHaveBeenCalledTimes(1)

    // A tick that lands while a probe is still in flight is skipped, so let the
    // first promise chain settle before advancing.
    await vi.advanceTimersByTimeAsync(0)
    await vi.advanceTimersByTimeAsync(60_000)
    expect(probeMock).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(0)
    refreshSeatHealth()
    expect(probeMock).toHaveBeenCalledTimes(3)
  })

  it('does not stack probes for a seat already in flight', async () => {
    let release: (rows: unknown[]) => void = () => {}
    probeMock.mockImplementation(() => new Promise((resolve) => { release = resolve }))
    trackSeatHealth([{ kind: 'cli', seatId: 'agy' }])
    vi.useFakeTimers()
    await vi.advanceTimersByTimeAsync(60_000)
    expect(probeMock).toHaveBeenCalledTimes(1)
    release([row('agy', 'cli', 'ok')])
    await vi.advanceTimersByTimeAsync(0)
  })

  it('seatDisplayName is inert without a ref', () => {
    expect(seatDisplayName('Name', null)).toBe('Name')
    expect(seatDisplayName('  ', { kind: 'api', seatId: 'x' })).toBe('')
  })
})

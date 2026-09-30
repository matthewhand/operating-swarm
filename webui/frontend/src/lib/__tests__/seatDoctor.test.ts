/**
 * The seat doctor store's contract.
 *
 * Three properties are pinned here, because each one has already gone wrong
 * somewhere in this codebase and the failure is always the same shape: the UI
 * says something reassuring that nobody checked.
 *
 * 1. `unverified` is a third state, not a softer `broken`, and a
 *    `not_configured` bucket reads as *incomplete*, not as a fault. Only a
 *    genuine fault bucket on a `broken` verdict is allowed the `fault` tone.
 * 2. A failed run is an `error` with a message. It is never a report with zero
 *    rows, and a body that is not a report is rejected rather than rendered.
 * 3. Nothing schedules itself: a run is a human press, and the module contains
 *    no interval. Env references are reduced to variable *names*; a value is
 *    dropped, not printed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { SeatDoctorQuery, SeatDoctorReport, SeatDoctorRow } from '../api/seatDoctor'
import { seatDoctorPath } from '../api/seatDoctor'
import {
  NOT_A_FAULT_BUCKETS,
  SEAT_DOCTOR_CHANGED_EVENT,
  __setSeatDoctorFetcher,
  envVarName,
  envVarNames,
  resetSeatDoctor,
  runSeatDoctor,
  seatDoctorState,
  seatDoctorTone,
  seatDoctorVerdict,
  sortSeatDoctorRows,
  subscribeSeatDoctor,
  summariseSeatDoctor,
} from '../seatDoctor'

function row(over: Partial<SeatDoctorRow> = {}): SeatDoctorRow {
  return {
    kind: 'api',
    seat_id: 'gpt-5.6-terra',
    label: 'Terra',
    origin: 'https://api.example.test/v1',
    verdict: 'broken',
    bucket: 'quota',
    detail: '402 Payment Required',
    remediation: 'top up the credit/balance',
    proves: 'nothing',
    turn_proved: false,
    latency_ms: 120,
    delegates_to: [],
    evidence: {},
    ...over,
  }
}

function report(results: SeatDoctorRow[]): SeatDoctorReport {
  return {
    object: 'seat_doctor_report',
    deep: false,
    read_only: true,
    totals: {
      seats: results.length,
      broken: results.filter((r) => r.verdict === 'broken').length,
      unverified: results.filter((r) => r.verdict === 'unverified').length,
      ok: results.filter((r) => r.verdict === 'ok').length,
    },
    buckets: {},
    results,
  }
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0))

describe('seatDoctor store — verdict honesty', () => {
  beforeEach(() => resetSeatDoctor())
  afterEach(() => {
    resetSeatDoctor()
    __setSeatDoctorFetcher(null)
    vi.useRealTimers()
  })

  it('keeps the three verdicts distinct, and an unknown one is not folded into ok', () => {
    expect(seatDoctorTone(row({ verdict: 'ok', bucket: '' }))).toBe('ok')
    expect(seatDoctorTone(row({ verdict: 'unverified', bucket: '' }))).toBe('unverified')
    expect(seatDoctorTone(row({ verdict: 'broken', bucket: 'quota' }))).toBe('fault')
    // The server may grow a verdict. It is surfaced as unknown, never guessed.
    expect(seatDoctorTone(row({ verdict: 'sideways' }))).toBe('unknown')
    expect(seatDoctorVerdict(row({ verdict: 'sideways' }))).toBe('unknown')
  })

  /**
   * The headline case from the audit: a seat nobody finished setting up. The
   * backend calls it broken (correct — it cannot work), but painting it like a
   * fault sends the operator chasing a failure that does not exist.
   */
  it('not_configured reads as incomplete, never as a fault', () => {
    expect(NOT_A_FAULT_BUCKETS.has('not_configured')).toBe(true)
    const notConfigured = row({ verdict: 'broken', bucket: 'not_configured' })
    expect(seatDoctorTone(notConfigured)).toBe('incomplete')
    expect(seatDoctorTone(notConfigured)).not.toBe('fault')
    // …while a real fault on the same verdict still is one.
    expect(seatDoctorTone(row({ verdict: 'broken', bucket: 'auth' }))).toBe('fault')
  })

  /**
   * `timeout_risk` is paired with an `unverified` verdict in the backend (a turn
   * that worked but blew the seat's own budget). A bucket must not be able to
   * escalate an unverified row into a fault.
   */
  it('a bucket never escalates an unverified row into a fault', () => {
    expect(seatDoctorTone(row({ verdict: 'unverified', bucket: 'timeout_risk' }))).toBe(
      'unverified',
    )
  })

  it('counts broken, unverified and ok separately, and keeps unverified out of ok', () => {
    const summary = summariseSeatDoctor([
      row({ verdict: 'broken', bucket: 'quota' }),
      row({ verdict: 'broken', bucket: 'not_configured' }),
      row({ verdict: 'unverified', bucket: '' }),
      row({ verdict: 'ok', bucket: '' }),
      row({ verdict: 'mystery', bucket: '' }),
    ])
    expect(summary).toMatchObject({
      seats: 5,
      broken: 2,
      // One of the two broken is a setup gap, not a fault.
      incomplete: 1,
      unverified: 1,
      ok: 1,
      unknown: 1,
    })
    expect(summary.ok).toBe(1)
  })

  it('ignores the server totals and counts the rows it will actually render', () => {
    const lying = report([row({ verdict: 'broken', bucket: 'quota' })])
    lying.totals = { seats: 0, broken: 0, unverified: 0, ok: 0 }
    expect(summariseSeatDoctor(lying.results).broken).toBe(1)
  })

  it('sorts faults first, then setup gaps, then unverified, then working', () => {
    const sorted = sortSeatDoctorRows([
      row({ seat_id: 'd', label: 'D', verdict: 'ok', bucket: '' }),
      row({ seat_id: 'u', label: 'U', verdict: 'unverified', bucket: '' }),
      row({ seat_id: 'i', label: 'I', verdict: 'broken', bucket: 'not_configured' }),
      row({ seat_id: 'f', label: 'F', verdict: 'broken', bucket: 'quota' }),
    ])
    expect(sorted.map((r) => r.label)).toEqual(['F', 'I', 'U', 'D'])
  })
})

describe('seatDoctor store — a failed run never reads as good news', () => {
  beforeEach(() => resetSeatDoctor())
  afterEach(() => {
    resetSeatDoctor()
    __setSeatDoctorFetcher(null)
    // The no-interval test installs fake timers; leaving them behind would hang
    // every later test that awaits a real timeout.
    vi.useRealTimers()
  })

  it('records a transport failure as an error with a message, not an empty report', async () => {
    __setSeatDoctorFetcher(() => Promise.reject(new ApiError(503, 'daemon down')))
    const result = await runSeatDoctor()
    const state = seatDoctorState()
    expect(result).toBeNull()
    expect(state.status).toBe('error')
    expect(state.report).toBeNull()
    expect(state.error).toContain('daemon down')
    expect(state.error).toContain('503')
  })

  it('rejects a body that is not a report instead of rendering zero rows', async () => {
    __setSeatDoctorFetcher(() => Promise.resolve({ error: 'nope' } as never))
    await runSeatDoctor()
    const state = seatDoctorState()
    expect(state.status).toBe('error')
    expect(state.report).toBeNull()
    expect(state.error).toMatch(/did not return a seat doctor report/i)
  })

  it('keeps the last good report so a later failure can be shown above it', async () => {
    __setSeatDoctorFetcher(() => Promise.resolve(report([row({ label: 'Terra' })])))
    await runSeatDoctor()
    expect(seatDoctorState().status).toBe('done')

    __setSeatDoctorFetcher(() => Promise.reject(new ApiError(500, 'boom')))
    await runSeatDoctor()
    const state = seatDoctorState()
    expect(state.status).toBe('error')
    expect(state.error).toContain('boom')
    // Kept, not nulled — the pane labels it as the *previous* run.
    expect(state.report?.results).toHaveLength(1)
    expect(state.lastSuccessAt).toBeGreaterThan(0)
  })

  it('emits on change and notifies subscribers so a sibling pane can react', async () => {
    let fired = 0
    const listener = () => {
      fired += 1
    }
    window.addEventListener(SEAT_DOCTOR_CHANGED_EVENT, listener)
    const off = subscribeSeatDoctor(listener)
    __setSeatDoctorFetcher(() => Promise.resolve(report([])))
    await runSeatDoctor()
    expect(fired).toBeGreaterThan(0)
    off()
    window.removeEventListener(SEAT_DOCTOR_CHANGED_EVENT, listener)
  })

  it('a second press joins the run in flight rather than starting a second audit', async () => {
    let resolve: (value: SeatDoctorReport) => void = () => {}
    const fetcher = vi.fn(
      () => new Promise<SeatDoctorReport>((res) => {
        resolve = res
      }),
    )
    __setSeatDoctorFetcher(fetcher)
    const first = runSeatDoctor()
    const second = runSeatDoctor()
    resolve(report([row()]))
    await Promise.all([first, second])
    expect(fetcher).toHaveBeenCalledTimes(1)
  })

  it('sends the operator’s kind filter and deep flag to the endpoint', async () => {
    const fetcher = vi.fn(() => Promise.resolve(report([])))
    __setSeatDoctorFetcher(fetcher)
    const query: SeatDoctorQuery = { kinds: ['remote', 'cli'], deep: true }
    await runSeatDoctor(query)
    expect(fetcher).toHaveBeenCalledWith(query)
    expect(seatDoctorPath(query)).toBe('/v1/seats/doctor?kind=remote&kind=cli&deep=1')
    expect(seatDoctorPath()).toBe('/v1/seats/doctor')
  })

  /**
   * The rule the whole page rests on. If a timer ever appears here, a 40-second
   * audit starts being fired on its own and the surface stops being honest.
   */
  it('never schedules itself — no interval re-runs the audit', async () => {
    vi.useFakeTimers()
    const fetcher = vi.fn(() => Promise.resolve(report([row()])))
    __setSeatDoctorFetcher(fetcher)
    await runSeatDoctor()
    expect(fetcher).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(60 * 60 * 1000)
    expect(fetcher).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('seatDoctor store — env references are names, never values', () => {
  it('accepts a name, a ${NAME} template, and a NAME=… assignment (name only)', () => {
    expect(envVarName('OPENAI_API_KEY')).toBe('OPENAI_API_KEY')
    expect(envVarName('  ${HERDR_TOKEN}  ')).toBe('HERDR_TOKEN')
    expect(envVarName('ANTHROPIC_API_KEY=sk-ant-secret')).toBe('ANTHROPIC_API_KEY')
  })

  it('drops anything that is not a plain variable name', () => {
    expect(envVarName('sk-ant-api03-REALVALUE')).toBe('')
    expect(envVarName('Bearer abc123')).toBe('')
    expect(envVarName('${NOT A NAME}')).toBe('')
    expect(envVarName(42)).toBe('')
    expect(envVarName(null)).toBe('')
  })

  it('reads names off the evidence allowlist only, and de-duplicates', () => {
    expect(
      envVarNames(
        row({
          evidence: {
            api_key_env: 'OPENAI_API_KEY',
            missing_env: 'OPENAI_API_KEY',
            cookie_env: '${HERDR_TOKEN}',
            // Not on the allowlist, so a secret parked elsewhere is not surfaced.
            body: 'sk-ant-api03-SHOULD-NOT-APPEAR',
          },
        }),
      ),
    ).toEqual(['OPENAI_API_KEY', 'HERDR_TOKEN'])
  })

  it('tolerates junk evidence instead of throwing', () => {
    expect(envVarNames(row({ evidence: null as never }))).toEqual([])
    expect(envVarNames(row({ evidence: ['OPENAI_API_KEY'] as never }))).toEqual([])
    expect(envVarNames(row({ evidence: 'sk-secret' as never }))).toEqual([])
  })

  it('reset returns the store to idle with no report and no error', async () => {
    __setSeatDoctorFetcher(() => Promise.resolve(report([row()])))
    await runSeatDoctor()
    await flush()
    resetSeatDoctor()
    const state = seatDoctorState()
    expect(state).toEqual({
      status: 'idle',
      report: null,
      error: '',
      query: {},
      startedAt: 0,
      lastSuccessAt: 0,
    })
  })
})

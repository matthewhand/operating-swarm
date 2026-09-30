/**
 * #1658 follow-up — the seat-health poll must be ONE request per tick, and a
 * rail rebuild must not be a traffic event.
 *
 * The runaway this pins: `probeOne` handed the batch endpoint a single-element
 * `seats` array, so one tick over a 20-seat rail was 20 POSTs to
 * `/v1/seats/health`; and `trackSeatHealth` re-probed on *every* call, from a
 * `useEffect` with no cleanup that any `remotes` / `agents` identity change
 * re-ran. 190k requests in 24h.
 *
 * Every assertion here counts transport invocations, because the number of
 * invocations *is* the number of HTTP requests. The last test in the file
 * counts real `fetch` POSTs with the real transport (no prober seam at all) so
 * the headline number is measured, not inferred.
 *
 * Tests marked NON-REGRESSION GUARD pass on the buggy code as well: they pin
 * behaviour the fix must not break (a failed poll stays non-evidence, a stop
 * still stops the interval). They are here so the fix cannot quietly trade one
 * defect for another.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiThrottleError } from '../api'
import {
  __setSeatHealthProber,
  noteTurnFailure,
  refreshSeatHealth,
  resetSeatHealth,
  seatBrokenReason,
  seatHealth,
  seatIsBroken,
  stopTrackingSeatHealth,
  trackSeatHealth,
  type SeatRef,
} from '../seatHealth'
import type { SeatHealthRow } from '../api/seatHealth'

const probeMock = vi.fn()

function okRows(batch: SeatRef[]): SeatHealthRow[] {
  return batch.map((s) => ({
    seat_id: s.seatId,
    kind: s.kind,
    state: 'ok' as const,
    reason: '',
    latency_ms: 1,
    checked_at: 1_700_000_000_000,
    broken: false,
  }))
}

function rowsWith(batch: SeatRef[], state: string, reason: string): SeatHealthRow[] {
  return batch.map((s) => ({
    seat_id: s.seatId,
    kind: s.kind,
    state: state as SeatHealthRow['state'],
    reason,
    latency_ms: 1,
    checked_at: 1_700_000_000_000,
    broken: state === 'broken',
  }))
}

/** `n` distinct seats of one kind — the realistic rail size. */
function seats(n: number, kind: SeatRef['kind'] = 'api'): SeatRef[] {
  return Array.from({ length: n }, (_, i) => ({
    kind,
    seatId: `seat-${String(i).padStart(2, '0')}`,
  }))
}

/** Settle the store's promise chain under fake timers. */
const settle = () => vi.advanceTimersByTimeAsync(0)

const TICK = 60_000

beforeEach(() => {
  resetSeatHealth()
  probeMock.mockReset()
  __setSeatHealthProber((batch) => probeMock(batch))
})

afterEach(() => {
  resetSeatHealth()
  __setSeatHealthProber(null)
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('seat health poll — one request per tick, whatever the rail size', () => {
  it('asks for the whole rail in ONE call, not one per seat', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(1)
    expect(probeMock.mock.calls[0][0]).toHaveLength(20)
  })

  it('a poll tick is one call for the whole rail, not one per seat', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[1][0]).toHaveLength(20)
  })

  it('a tick that lands while a batch is in flight does not queue another', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    const before = probeMock.mock.calls.length

    // A slow backend: the next five ticks all land mid-batch. The first tick
    // owes one request; the four behind it must be dropped, not queued.
    probeMock.mockImplementation(() => new Promise<SeatHealthRow[]>(() => {}))
    await vi.advanceTimersByTimeAsync(TICK * 5)

    expect(probeMock.mock.calls.length - before).toBe(1)
  })

  it('a rail longer than one request still gets verdicts for its tail', async () => {
    // `MAX_BATCH` in `swarm/core/seat_health.py` truncates the array server-side
    // and never says so, so a 70-seat rail has to be split rather than dropped.
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))
    const many = seats(70)

    trackSeatHealth(many)
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[0][0]).toHaveLength(60)
    expect(probeMock.mock.calls[1][0]).toHaveLength(10)
    for (const s of many) expect(seatHealth(s).state).toBe('ok')
  })

  it('probes every distinct CLI binary, not just the ones this request can fork', async () => {
    // `CLI_PROBES_PER_BATCH` caps distinct forks per request and defers the
    // rest, so a fixed order would starve every CLI past the cap for ever.
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))
    const clis: SeatRef[] = Array.from({ length: 10 }, (_, i) => ({
      kind: 'cli',
      seatId: `cli-${i}`,
      cli: `bin-${i}`,
    }))

    trackSeatHealth(clis)
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    // One request per tick...
    expect(probeMock.mock.calls).toHaveLength(3)
    for (const call of probeMock.mock.calls) expect(call[0]).toHaveLength(10)
    // ...and the fork window walks the whole set.
    const forked = new Set<string>()
    for (const call of probeMock.mock.calls.slice(0, 2)) {
      for (const s of call[0].slice(0, 6)) forked.add(`${s.kind}:${s.seatId}`)
    }
    expect(forked.size).toBe(10)
  })
})

describe('seat health poll — a rail rebuild is not a traffic event', () => {
  it('re-tracking the same seats in a new array sends nothing', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    // A `remotes` poll hands the effect a brand-new array every time.
    trackSeatHealth(seats(20).map((s) => ({ ...s })))
    trackSeatHealth([...seats(20)].reverse())
    trackSeatHealth(seats(20))
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(1)
  })

  it('one added seat is one call, and it carries every seat', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    trackSeatHealth(seats(21))
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[1][0]).toHaveLength(21)
  })

  it('an emptied rail stops the interval instead of leaving one running', async () => {
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(window, 'clearInterval')
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    trackSeatHealth([])
    await vi.advanceTimersByTimeAsync(TICK * 3)

    expect(clearSpy).toHaveBeenCalled()
    expect(probeMock).toHaveBeenCalledTimes(1)
  })

  it('a mount / unmount / mount cycle probes once per mount', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    stopTrackingSeatHealth()
    trackSeatHealth(seats(20))
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
  })

  it('NON-REGRESSION GUARD: a remount leaves exactly one live interval', async () => {
    vi.useFakeTimers()
    const setSpy = vi.spyOn(window, 'setInterval')
    const clearSpy = vi.spyOn(window, 'clearInterval')
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    stopTrackingSeatHealth()
    trackSeatHealth(seats(20))
    await settle()
    // One interval per mount, one clear per stop — never a second interval
    // piling up behind the first.
    stopTrackingSeatHealth()

    expect(setSpy).toHaveBeenCalledTimes(2)
    expect(clearSpy).toHaveBeenCalledTimes(2)
  })

  it('NON-REGRESSION GUARD: stopTrackingSeatHealth stops the interval', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    const atStop = probeMock.mock.calls.length
    stopTrackingSeatHealth()
    await vi.advanceTimersByTimeAsync(TICK * 3)

    expect(probeMock).toHaveBeenCalledTimes(atStop)
  })
})

describe('seat health poll — a 429 silences the poll instead of feeding the throttle', () => {
  it('ticks inside the Retry-After window are dropped, and the poll resumes after it', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    // The server says 429 and asks for 90s. A 60s tick then lands INSIDE that
    // window, which is exactly the dig-while-429 that kept the window shut.
    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(2)

    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(2)

    // The window frees and the poll resumes on its own, with no operator action.
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(3)
    expect(probeMock.mock.calls[2][0]).toHaveLength(20)
  })

  it('a throttled batch leaves every last verdict standing', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))
    const rail = seats(20)

    trackSeatHealth(rail)
    await settle()
    expect(seatHealth(rail[3]).state).toBe('ok')

    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    // A busy server is not a dead agent. Nothing gets renamed to `broken`.
    for (const s of rail) expect(seatHealth(s).state).toBe('ok')
  })

  it('a manual refresh does not dig into a closed window either', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 0))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    const after = probeMock.mock.calls.length

    // The 2s the server's own message quotes is the floor (the doubling per
    // consecutive 429 is the gate's policy, pinned in healthThrottle.test).
    refreshSeatHealth()
    await vi.advanceTimersByTimeAsync(1_500)
    await settle()
    expect(probeMock.mock.calls.length).toBe(after)

    // Ask again once the window is clear: the refresh path is not disabled, it
    // is only held while the server is saying no.
    await vi.advanceTimersByTimeAsync(1_000)
    refreshSeatHealth()
    await settle()
    expect(probeMock.mock.calls.length).toBe(after + 1)
  })

  it('a new seat arriving mid-throttle waits rather than spending a request', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))

    trackSeatHealth(seats(20))
    await settle()
    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    const after = probeMock.mock.calls.length

    // A genuinely new seat would normally get an immediate verdict. While the
    // gate is shut it does not — the queue behind a throttle is the defect.
    trackSeatHealth(seats(21))
    await settle()
    expect(probeMock.mock.calls.length).toBe(after)

    await vi.advanceTimersByTimeAsync(TICK * 2)
    await settle()
    expect(probeMock.mock.calls[after][0]).toHaveLength(21)
  })
})

describe('seat health poll — a bad seat cannot take the batch down', () => {
  it('NON-REGRESSION GUARD: a failed batch leaves every last verdict standing', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => okRows(batch))
    const rail = seats(20)

    trackSeatHealth(rail)
    await settle()
    expect(seatHealth(rail[3]).state).toBe('ok')

    probeMock.mockRejectedValue(new Error('429 Too Many Requests'))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    // A failed status poll is not proof a seat is broken.
    for (const s of rail) expect(seatHealth(s).state).toBe('ok')
  })

  it('one missing row does not cost the other seats their verdicts', async () => {
    vi.useFakeTimers()
    // The backend answers for 18 of 20 seats and says nothing about the rest.
    probeMock.mockImplementation(async (batch: SeatRef[]) =>
      okRows(batch).filter((row) => row.seat_id !== 'seat-18' && row.seat_id !== 'seat-19'),
    )
    const rail = seats(20)

    trackSeatHealth(rail)
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(1)
    for (const s of rail.slice(0, 18)) expect(seatHealth(s).state).toBe('ok')
    expect(seatHealth(rail[18]).state).toBe('unknown')
    expect(seatHealth(rail[19]).state).toBe('unknown')
  })

  it('one unparseable row does not stop the rows after it', async () => {
    vi.useFakeTimers()
    probeMock.mockImplementation(async (batch: SeatRef[]) => {
      const good = okRows(batch)
      // A row the store cannot key, sitting in the middle of the batch.
      return [good[0], { kind: 'cli' } as unknown as SeatHealthRow, ...good.slice(1)]
    })
    const rail = seats(20)

    trackSeatHealth(rail)
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(1)
    for (const s of rail) expect(seatHealth(s).state).toBe('ok')
  })

  it("a backend 'deferred' answer does not overwrite a real turn failure", async () => {
    vi.useFakeTimers()
    const ref: SeatRef = { kind: 'cli', seatId: 'seat-00', cli: 'grok' }
    noteTurnFailure(ref, 'connect ECONNREFUSED')
    // `probe_seats` reports a capped-out CLI as `unknown`/"deferred" rather
    // than skipping it. That is the absence of an answer, not a verdict, and a
    // failed turn is stronger evidence than any probe.
    probeMock.mockImplementation(async (batch: SeatRef[]) =>
      rowsWith(batch, 'unknown', 'deferred: this tick already probed 6 CLI binaries'),
    )

    trackSeatHealth([ref])
    await settle()

    expect(seatIsBroken(ref)).toBe(true)
    expect(seatBrokenReason(ref)).toBe('connect ECONNREFUSED')
  })
})

describe('seat health poll — measured on the real transport', () => {
  it('posts ONE request per tick, with every seat in its body', async () => {
    // No prober seam: this is `apiPost` through `fetch`, so the count below is
    // the number the backend's throttle log would show.
    __setSeatHealthProber(null)
    const fetchMock = vi.fn(async (_input: RequestInfo, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body || '{}'))
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'seat_health_batch',
          checked: (body.seats as unknown[]).length,
          broken: 0,
          results: (body.seats as { kind: string; seat_id: string }[]).map((s) => ({
            seat_id: s.seat_id,
            kind: s.kind,
            state: 'ok',
            reason: '',
            latency_ms: 1,
            checked_at: 1_700_000_000_000,
            broken: false,
          })),
        }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    trackSeatHealth([
      ...seats(8, 'api'),
      ...seats(6, 'cli').map((s) => ({ ...s, cli: `${s.seatId}-bin` })),
      ...seats(6, 'remote'),
    ])
    await new Promise((resolve) => setTimeout(resolve, 0))

    const posts = () =>
      fetchMock.mock.calls.filter(
        ([input, init]) => String(input) === '/v1/seats/health' && init?.method === 'POST',
      )
    expect(posts()).toHaveLength(1)
    expect(JSON.parse(String(posts()[0][1]?.body)).seats).toHaveLength(20)

    // And the same rail rebuilt with identical contents adds nothing.
    trackSeatHealth([
      ...seats(8, 'api'),
      ...seats(6, 'cli').map((s) => ({ ...s, cli: `${s.seatId}-bin` })),
      ...seats(6, 'remote'),
    ])
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(posts()).toHaveLength(1)

    vi.unstubAllGlobals()
  })
})

/**
 * #1783 — remote health is ONE write per tick, and a 429 silences the poll.
 *
 * The runaway this pins: a 60s tick over N remotes was N `POST
 * /v1/remotes/<id>/health/` writes against a DRF write throttle of one per
 * minute — ~290k requests in 24h, and a `Too many requests — the server is
 * busy. Please try again in 2s.` toast every time the poll dug back in. There
 * is no batch form of that route, so the poll now asks `POST /v1/seats/health`
 * — already batch-shaped, already probing `kind: "remote"` through the same
 * `remotes.check_health` — with every tracked id in ONE body.
 *
 * Two properties are asserted, and they are the two halves of the requirement:
 *  - TRAFFIC: a tick is one write whatever the remote count, and a rebuild
 *    that changed no ids is still zero writes (#1196's invariant, kept).
 *  - PATIENCE: a 429 shuts the poll until the server's `Retry-After` is up. No
 *    dig-while-429 — retrying into a closed window is what kept the window shut.
 *
 * Every assertion counts transport invocations, because the number of
 * invocations *is* the number of HTTP requests. The last test in the file
 * counts real `fetch` POSTs with the real transport (no seam at all), so the
 * headline number is measured rather than inferred.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiThrottleError } from '../api'
import type { SeatHealthRow } from '../api/seatHealth'
import {
  __resetRemoteHealthForTests,
  __setRemoteHealthProber,
  refreshRemoteHealth,
  remoteHealthStatus,
  startRemoteHealthPolling,
  stopRemoteHealthPolling,
} from '../remoteHealth'

const probeMock = vi.fn()

function okRows(ids: string[]): SeatHealthRow[] {
  return ids.map((id) => ({
    seat_id: id,
    kind: 'remote',
    state: 'ok' as const,
    reason: '',
    latency_ms: 1,
    checked_at: 1_700_000_000_000,
    broken: false,
  }))
}

const TICK = 60_000
/** `n` distinct remote ids — the shape a real rail hands over. */
function ids(n: number): string[] {
  return Array.from({ length: n }, (_, i) => `remote-${String(i).padStart(2, '0')}`)
}

/** Settle the store's promise chain under fake timers. */
const settle = () => vi.advanceTimersByTimeAsync(0)

beforeEach(() => {
  probeMock.mockReset()
  probeMock.mockImplementation(async (batch: string[]) => okRows(batch))
  __setRemoteHealthProber((batch) => probeMock(batch))
  __resetRemoteHealthForTests()
})

afterEach(() => {
  __resetRemoteHealthForTests()
  __setRemoteHealthProber(null)
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('#1783 remote health — one write per tick, whatever the remote count', () => {
  it('a 20-remote rail asks for the whole list in ONE call, not one per remote', async () => {
    vi.useFakeTimers()

    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()

    // THE HEADLINE. Pre-fix this was 20 POSTs, one per remote, per tick.
    expect(probeMock).toHaveBeenCalledTimes(1)
    expect(probeMock.mock.calls[0][0]).toHaveLength(20)
  })

  it('a poll tick is one call for the whole list, not one per remote', async () => {
    vi.useFakeTimers()

    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    // Three moments that each want a verdict for 20 remotes: three writes.
    // Per-remote would be 60.
    expect(probeMock).toHaveBeenCalledTimes(3)
    for (const call of probeMock.mock.calls) expect(call[0]).toHaveLength(20)
  })

  it('a tick that lands while a batch is in flight does not queue another', async () => {
    vi.useFakeTimers()
    // A slow backend: the batch stays in flight for the whole window.
    probeMock.mockImplementation(() => new Promise<SeatHealthRow[]>(() => {}))

    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(TICK * 5)

    // Each of those five ticks owes nothing: the request is still outstanding,
    // and queueing is the busy loop being fixed.
    expect(probeMock).toHaveBeenCalledTimes(1)
  })

  it('a list longer than one batch still gets verdicts for its tail', async () => {
    // `MAX_BATCH` in `swarm/core/seat_health.py` truncates the `seats` array
    // without saying so, so a 70-remote install is split rather than dropped.
    vi.useFakeTimers()
    const many = ids(70)

    startRemoteHealthPolling(many, 'sidebar')
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[0][0]).toHaveLength(60)
    expect(probeMock.mock.calls[1][0]).toHaveLength(10)
    for (const id of many) expect(remoteHealthStatus(id)).toBe('ok')
  })
})

describe('#1196 invariant — a rebuild is still not a traffic event', () => {
  it('publishing the same remotes again in a new array sends nothing', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    // A `remotes` poll hands the effect a brand-new array every time, with the
    // same contents. Before the fix each of these was another 20 requests.
    startRemoteHealthPolling(ids(20), 'sidebar')
    startRemoteHealthPolling([...ids(20)].reverse(), 'sidebar')
    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(1)
  })

  it('one added remote is exactly one further call, carrying every remote', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()

    startRemoteHealthPolling(ids(21), 'sidebar')
    await settle()

    // A new id still gets an immediate verdict, and it costs one write — the
    // same one, carrying everything, rather than a second request per id.
    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[1][0]).toHaveLength(21)
  })

  it('a removed remote stops being polled', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    startRemoteHealthPolling(ids(3), 'sidebar')
    await settle()
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    expect(probeMock).toHaveBeenCalledTimes(2)
    expect(probeMock.mock.calls[1][0]).toEqual(['remote-00', 'remote-01', 'remote-02'])
  })

  it('the chat pane costs one call for the whole list, and a resend costs none', async () => {
    vi.useFakeTimers()
    // The rail already tracks all four and holds a verdict for each.
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()
    const afterRail = probeMock.mock.calls.length

    // A new subscription is one write — for every tracked id, not just the one
    // the chat pane cares about, because the batch is the unit of traffic.
    startRemoteHealthPolling(['remote-01'], 'chat')
    await settle()
    expect(probeMock.mock.calls.length - afterRail).toBe(1)

    // Re-running the effect with the SAME selection costs nothing, which is the
    // `remotes`-identity-churn case.
    startRemoteHealthPolling(['remote-01'], 'chat')
    startRemoteHealthPolling(['remote-01'], 'chat')
    await settle()
    expect(probeMock.mock.calls.length - afterRail).toBe(1)

    // An actual switch is one more call, still a single request.
    startRemoteHealthPolling(['remote-02'], 'chat')
    await settle()
    expect(probeMock.mock.calls.length - afterRail).toBe(2)
  })

  it('NON-REGRESSION GUARD: an unmounted rail leaves no interval running', async () => {
    vi.useFakeTimers()
    const clearSpy = vi.spyOn(window, 'clearInterval')
    startRemoteHealthPolling(ids(3), 'sidebar')
    await settle()
    const atMount = probeMock.mock.calls.length

    stopRemoteHealthPolling('sidebar')
    expect(clearSpy).toHaveBeenCalled()
    await vi.advanceTimersByTimeAsync(TICK * 3)

    expect(probeMock.mock.calls.length).toBe(atMount)
  })

  it('NON-REGRESSION GUARD: a mount / unmount / mount cycle probes once per mount', async () => {
    vi.useFakeTimers()
    const setSpy = vi.spyOn(window, 'setInterval')
    startRemoteHealthPolling(ids(3), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    stopRemoteHealthPolling('sidebar')
    startRemoteHealthPolling(ids(3), 'sidebar')
    await settle()

    // A remount is a new subscription, not a rail rebuild: it re-probes once.
    expect(probeMock).toHaveBeenCalledTimes(2)
    // And it leaves exactly one live interval, never a second behind the first.
    expect(setSpy).toHaveBeenCalledTimes(2)
  })

  it('NON-REGRESSION GUARD: the default-owner API still polls and stops', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(2))
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(2)

    stopRemoteHealthPolling()
    await vi.advanceTimersByTimeAsync(TICK * 3)
    expect(probeMock).toHaveBeenCalledTimes(2)
  })
})

describe('#1783 — a 429 silences the poll instead of feeding the throttle', () => {
  it('ticks inside the Retry-After window are dropped, and the poll resumes after it', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(20), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(1)

    // The server says 429 and asks for 90s. A 60s tick then lands INSIDE that
    // window, which is exactly the dig-while-429 that kept the window shut.
    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(2)

    // The next tick is still inside the window: dropped, not queued.
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(2)

    // The window frees and the poll resumes on its own, with no operator action.
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(3)
    expect(probeMock.mock.calls[2][0]).toHaveLength(20)
  })

  it('the manual refresh does not dig into a closed window either', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()

    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    const after = probeMock.mock.calls.length

    // `refreshRemoteHealth` is the explicit path, and it is still bound by the
    // gate: an operator hammering refresh should not spend the throttle budget.
    refreshRemoteHealth(['remote-00'])
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(after)
  })

  it('a 429 with no Retry-After still silences the next attempt for 2s', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()

    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 0))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    const after = probeMock.mock.calls.length

    // The 2s the server's own message quotes is the floor (the doubling per
    // consecutive 429 is the gate's own policy, pinned in healthThrottle.test).
    refreshRemoteHealth(['remote-00'])
    await vi.advanceTimersByTimeAsync(1_500)
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(after)

    // Ask again once the window is clear: the refresh path is not disabled, it
    // is only held while the server is saying no.
    await vi.advanceTimersByTimeAsync(1_000)
    refreshRemoteHealth(['remote-00'])
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(after + 1)
  })

  it('a throttled batch does not paint the fleet offline', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()
    for (const id of ids(4)) expect(remoteHealthStatus(id)).toBe('ok')

    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    // The banner's honesty rule under throttling: a busy server is not a dead
    // remote. Every last verdict stands.
    for (const id of ids(4)) expect(remoteHealthStatus(id)).toBe('ok')
  })

  it('a plain failure is not a verdict either', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()
    for (const id of ids(4)) expect(remoteHealthStatus(id)).toBe('ok')

    probeMock.mockRejectedValueOnce(new Error('network down'))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()

    for (const id of ids(4)) expect(remoteHealthStatus(id)).toBe('ok')
  })

  it('a remote added while throttled is picked up by the first free tick, not before', async () => {
    vi.useFakeTimers()
    startRemoteHealthPolling(ids(4), 'sidebar')
    await settle()

    probeMock.mockRejectedValueOnce(new ApiThrottleError(429, 'busy', 90))
    await vi.advanceTimersByTimeAsync(TICK)
    await settle()
    const after = probeMock.mock.calls.length

    // A new remote would normally get an immediate verdict. Behind a throttle it
    // waits: the queue is the defect.
    startRemoteHealthPolling(ids(5), 'sidebar')
    await settle()
    expect(probeMock).toHaveBeenCalledTimes(after)

    await vi.advanceTimersByTimeAsync(TICK * 2)
    await settle()
    expect(probeMock.mock.calls[after][0]).toHaveLength(5)
  })
})

describe('#1783 remote health — measured on the real transport', () => {
  it('posts ONE request per tick to /v1/seats/health, with every remote in it', async () => {
    // No prober seam: this is `apiPost` through `fetch`, so the count below is
    // what the backend's throttle log would show. And it proves the negative
    // that matters — the poll no longer touches `/v1/remotes/<id>/health/`.
    __setRemoteHealthProber(null)
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
    const rail = ids(12)

    startRemoteHealthPolling(rail, 'sidebar')
    await new Promise((resolve) => setTimeout(resolve, 0))

    const posts = (path: string) =>
      fetchMock.mock.calls.filter(
        ([input, init]) => String(input) === path && init?.method === 'POST',
      )
    expect(posts('/v1/seats/health')).toHaveLength(1)
    expect(posts('/v1/remotes/remote-00/health/')).toHaveLength(0)
    const body = JSON.parse(String(posts('/v1/seats/health')[0][1]?.body))
    expect(body.seats).toHaveLength(12)
    expect(new Set(body.seats.map((s: { seat_id: string }) => s.seat_id))).toEqual(
      new Set(rail),
    )
    for (const seat of body.seats) expect(seat.kind).toBe('remote')

    // And the same rail rebuilt with identical contents adds nothing.
    startRemoteHealthPolling(ids(12), 'sidebar')
    await new Promise((resolve) => setTimeout(resolve, 0))
    expect(posts('/v1/seats/health')).toHaveLength(1)
  })
})

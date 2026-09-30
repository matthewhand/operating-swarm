/**
 * Cold-mount GET burst must be paced, not thundered.
 *
 * A cold SPA mount fires ~19 read-only /v1/* GETs in one tick. Over HTTP/2 the
 * browser multiplexes them, so the server sees the whole volley at once and the
 * DRF anon throttle returns 429 (retry-after ~17s). The transport gate caps
 * concurrent GETs and coalesces identical in-flight paths; writes are untouched.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiGet, MAX_CONCURRENT_GETS, __resetGetSchedulerForTests } from '../api'

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('cold-mount GET pacing', () => {
  beforeEach(() => {
    __resetGetSchedulerForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    __resetGetSchedulerForTests()
  })

  it('never exceeds MAX_CONCURRENT_GETS in-flight GETs on a cold mount burst', async () => {
    let active = 0
    let peak = 0
    const fetchMock = vi.fn().mockImplementation(async () => {
      active += 1
      peak = Math.max(peak, active)
      await new Promise((resolve) => setTimeout(resolve, 5))
      active -= 1
      return jsonResponse({ ok: true })
    })
    vi.stubGlobal('fetch', fetchMock)

    const paths = Array.from({ length: 19 }, (_, i) => `/v1/burst-${i}/`)
    const results = await Promise.all(paths.map((path) => apiGet<{ ok: boolean }>(path)))

    expect(results).toHaveLength(19)
    expect(fetchMock).toHaveBeenCalledTimes(19)
    expect(peak).toBeLessThanOrEqual(MAX_CONCURRENT_GETS)
  })

  it('coalesces concurrent identical in-flight GETs into one network call', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ n: 1 }))
    vi.stubGlobal('fetch', fetchMock)

    const [a, b, c] = await Promise.all([
      apiGet<{ n: number }>('/v1/same/'),
      apiGet<{ n: number }>('/v1/same/'),
      apiGet<{ n: number }>('/v1/same/'),
    ])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(a).toEqual({ n: 1 })
    expect(b).toEqual({ n: 1 })
    expect(c).toEqual({ n: 1 })
  })

  it('re-fetches the same path once the previous call settled (no stale TTL cache)', async () => {
    const fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ n: 1 }))
    vi.stubGlobal('fetch', fetchMock)

    await apiGet('/v1/sequential/')
    await apiGet('/v1/sequential/')

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

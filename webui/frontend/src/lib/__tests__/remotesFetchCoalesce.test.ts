/**
 * #581 — selecting a remote seat must be a handful of requests, not a volley.
 *
 * ChatPage mounted two queries that both GET /v1/remotes/ ('configured-remotes'
 * via fetchConfiguredRemotes and 'remotes-list' via fetchRemotes). The
 * contract here: concurrent /v1/remotes/ reads share one network GET —
 * in-flight dedupe plus a short TTL — and fetchConfiguredRemotes reuses the
 * shared fetch instead of issuing its own.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { fetchRemotes } from '../api'
import { fetchConfiguredRemotes } from '../remotesCatalog'
import { resetRemotesFetchCacheForTests } from '../api'

const REMOTES_PAYLOAD = {
  object: 'list',
  data: [
    {
      id: 'omb',
      kind: 'remote',
      title: 'OpenMausBot',
      configured: true,
      agents: [{ id: 'omb:default', name: 'default' }],
    },
  ],
}

describe('#581 /v1/remotes/ reads are coalesced', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    resetRemotesFetchCacheForTests()
    fetchMock = vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/remotes')) {
        return {
          ok: true,
          status: 200,
          json: async () => REMOTES_PAYLOAD,
        } as Response
      }
      // /remotes_catalog.json is absent in the test environment.
      return { ok: false, status: 404, json: async () => ({}) } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetRemotesFetchCacheForTests()
  })

  it('coalesces concurrent fetchRemotes() calls into one network GET', async () => {
    const [a, b, c] = await Promise.all([fetchRemotes(), fetchRemotes(), fetchRemotes()])
    expect(a.object).toBe('list')
    expect(b.object).toBe('list')
    expect(c.object).toBe('list')
    const remotesGets = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/v1/remotes'),
    )
    expect(remotesGets).toHaveLength(1)
  })

  it('reuses the cached list within the TTL window', async () => {
    await fetchRemotes()
    await fetchRemotes()
    const remotesGets = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/v1/remotes'),
    )
    expect(remotesGets).toHaveLength(1)
  })

  it('fetchConfiguredRemotes shares the same GET as fetchRemotes', async () => {
    const [entries, list] = await Promise.all([fetchConfiguredRemotes(), fetchRemotes()])
    expect(entries.length).toBeGreaterThan(0)
    expect(list.object).toBe('list')
    const remotesGets = fetchMock.mock.calls.filter(([input]) =>
      String(input).includes('/v1/remotes'),
    )
    expect(remotesGets).toHaveLength(1)
  })
})

describe('#680 throttled remotes fetch is never cached as empty', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    resetRemotesFetchCacheForTests()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetRemotesFetchCacheForTests()
  })

  function throttleFetch(statuses: number[]) {
    let call = 0
    fetchMock = vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (!url.includes('/v1/remotes')) {
        return { ok: false, status: 404, json: async () => ({}) } as unknown as Response
      }
      const status = statuses[Math.min(call, statuses.length - 1)]
      call += 1
      if (status === 200) {
        return { ok: true, status: 200, json: async () => REMOTES_PAYLOAD } as Response
      }
      return {
        ok: false,
        status,
        headers: { get: (name: string) => (name.toLowerCase() === 'retry-after' ? '1' : null) },
        json: async () => ({ detail: 'Request was throttled. Expected available in 1 second.' }),
      } as unknown as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  }

  it('retries after a 429 and returns the real list — the section self-heals', async () => {
    throttleFetch([429, 200])
    const rows = await fetchConfiguredRemotes()
    expect(rows).toHaveLength(1)
    expect(rows[0].id).toBe('omb')
    expect(fetchMock.mock.calls.filter(([i]) => String(i).includes('/v1/remotes'))).toHaveLength(2)
  })

  it('re-throws the throttle error after the retry budget — never an empty list', async () => {
    throttleFetch([429, 429, 429])
    await expect(fetchConfiguredRemotes()).rejects.toMatchObject({ name: 'ApiThrottleError' })
  })

  it('still returns [] for a plain server error (non-throttle failure)', async () => {
    throttleFetch([500])
    const rows = await fetchConfiguredRemotes()
    expect(rows).toEqual([])
  })
})

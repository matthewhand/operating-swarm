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

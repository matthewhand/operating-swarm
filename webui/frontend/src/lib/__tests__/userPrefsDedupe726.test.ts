/**
 * #726 — /v1/preferences/ is fetched by at least four independent surfaces on
 * page load (ChatPage hydrate, SettingsSheet, RoleAgentTip, DefaultLlmTip).
 * Each call used to be a full GET, so one page load fired 4-8 identical
 * requests and the DRF anon throttle answered 429 to the rest of the app.
 *
 * The fix is one promise in userPrefs: concurrent callers share an in-flight
 * GET, and a resolved bag is reused for a short window. PATCHes invalidate the
 * cache so the next read sees fresh data.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  __resetUserPrefsCacheForTests,
  fetchUserPrefs,
  saveUserPrefs,
} from '../userPrefs'

function jsonResponse(body: unknown, ok = true, status = ok ? 200 : 400) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const SERVER_BAG = {
  object: 'user_preferences',
  favourites: [],
  hidden_agents: [],
  values: {},
}

describe('#726 fetchUserPrefs dedupe', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetUserPrefsCacheForTests()
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('shares one in-flight GET across concurrent callers', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(SERVER_BAG))
    vi.stubGlobal('fetch', fetchMock)

    const [a, b, c, d] = await Promise.all([
      fetchUserPrefs(),
      fetchUserPrefs(),
      fetchUserPrefs(),
      fetchUserPrefs(),
    ])

    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(a).toEqual(b)
    expect(c).toEqual(d)
  })

  it('reuses a resolved bag for a short window instead of re-GETting', async () => {
    const fetchMock = vi.fn(async () => jsonResponse(SERVER_BAG))
    vi.stubGlobal('fetch', fetchMock)

    await fetchUserPrefs()
    await fetchUserPrefs()

    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Past the cache window a fresh GET is allowed again.
    vi.advanceTimersByTime(61_000)
    await fetchUserPrefs()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('invalidates the cache after a PATCH so the next read is fresh', async () => {
    const fetchMock =    vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse(SERVER_BAG))
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal(
      'document',
      Object.assign(document, { cookie: 'csrftoken=test-token' }),
    )

    await fetchUserPrefs()
    await saveUserPrefs({ favourites: [] })
    await fetchUserPrefs()

    const gets = fetchMock.mock.calls.filter(([, init]) => ((init?.method || 'GET') as string).toUpperCase() === 'GET')
    expect(gets.length).toBe(2)
  })
})

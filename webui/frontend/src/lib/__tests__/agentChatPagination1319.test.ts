/**
 * #1319 — frontend hydration paging contract for `fetchAgentThread`.
 *
 * - the newest page is requested by default (bounded `limit`);
 * - `has_more` / `cursor` are surfaced to the caller;
 * - `before` fetches an older page; `flush` keeps the full-thread load.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  THREAD_PAGE_SIZE,
  fetchAgentThread,
  fetchEarlierAgentThreadPage,
} from '../agentChat'

function stubThread(body: Record<string, unknown>) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => body,
  } as Response)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function firstUrl(fetchMock: ReturnType<typeof vi.fn>): string {
  return String(fetchMock.mock.calls[0][0])
}

describe('fetchAgentThread paging (#1319)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('requests the newest page by default and surfaces has_more/cursor', async () => {
    const fetchMock = stubThread({
      agent_id: 'codey',
      conversation_id: 'c1',
      messages: [{ role: 'user', content: 'newest' }],
      has_more: true,
      cursor: '7',
    })
    const thread = await fetchAgentThread('codey', 'c1')
    const url = firstUrl(fetchMock)
    expect(url).toContain(`limit=${THREAD_PAGE_SIZE}`)
    expect(url).not.toContain('before=')
    expect(thread.has_more).toBe(true)
    expect(thread.cursor).toBe('7')
    expect(thread.messages).toEqual([{ role: 'user', content: 'newest' }])
  })

  it('passes an explicit limit and before cursor', async () => {
    const fetchMock = stubThread({
      agent_id: 'codey',
      conversation_id: 'c1',
      messages: [],
    })
    await fetchAgentThread('codey', 'c1', { limit: 10, before: 42 })
    const url = firstUrl(fetchMock)
    expect(url).toContain('limit=10')
    expect(url).toContain('before=42')
  })

  it('flush reloads the full thread (no default limit)', async () => {
    const fetchMock = stubThread({
      agent_id: 'codey',
      conversation_id: 'c1',
      messages: [],
    })
    await fetchAgentThread('codey', 'c1', { flush: true })
    const url = firstUrl(fetchMock)
    expect(url).toContain('flush=1')
    expect(url).not.toContain('limit=')
  })

  it('fetchEarlierAgentThreadPage sends the before cursor', async () => {
    const fetchMock = stubThread({
      agent_id: 'codey',
      conversation_id: 'c1',
      messages: [],
    })
    await fetchEarlierAgentThreadPage('codey', 'c1', '12')
    expect(firstUrl(fetchMock)).toContain('before=12')
  })

  it('defaults has_more false and cursor empty when the server omits them', async () => {
    stubThread({
      agent_id: 'codey',
      conversation_id: 'c1',
      messages: [],
    })
    const thread = await fetchAgentThread('codey', 'c1')
    expect(thread.has_more).toBe(false)
    expect(thread.cursor).toBe('')
  })
})

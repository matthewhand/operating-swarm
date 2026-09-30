/**
 * #1358 — TrueForge navbar catalog.
 *
 * The agent + session pickers source TrueForge rows from the dedicated
 * `/v1/remotes/<id>/trueforge/` endpoint only. A foreign provider or the
 * default inference profile is never consulted, and a down endpoint degrades
 * to an honest empty catalog instead of another provider's rows.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchRemoteThreadSessions,
  fetchTrueForgeCatalog,
  fetchTrueForgeNavbarCatalog,
  isTrueForgeKind,
  trueForgeAgentsFromCatalog,
  trueForgeMemberSessions,
} from '../remoteSessions'

const CATALOG_BODY = {
  object: 'trueforge.catalog',
  remote: 'trueforge',
  kind: 'trueforge',
  ok: true,
  detail: 'TrueForge listed 2 agent(s)',
  http_status: 200,
  rows_are: 'agents',
  resume_key: 'session_id',
  agents: [
    { id: 'agent-1', label: 'orchestrator', name: 'orchestrator' },
    { id: 'agent-2', label: 'coder', name: 'coder' },
  ],
  sessions: [
    {
      id: 'sess-9',
      title: 'refactor the parser',
      snippet: 'orchestrator',
      agent: 'orchestrator',
      created_at: '2026-09-21T10:00:00Z',
      updated_at: '2026-09-22T08:30:00Z',
    },
    { id: 'sess-4', title: 'sess-4', agent: 'coder' },
  ],
}

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('#1358 isTrueForgeKind', () => {
  it('matches the trueforge kind only', () => {
    expect(isTrueForgeKind('trueforge')).toBe(true)
    expect(isTrueForgeKind('TrueForge')).toBe(true)
    expect(isTrueForgeKind('true_forge')).toBe(false)
    expect(isTrueForgeKind('hermes')).toBe(false)
    expect(isTrueForgeKind('')).toBe(false)
  })
})

describe('#1358 fetchTrueForgeCatalog', () => {
  it('reads agents + sessions from the TrueForge endpoint', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo) => jsonResponse(CATALOG_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const catalog = await fetchTrueForgeCatalog('trueforge')

    expect(String(fetchMock.mock.calls[0][0])).toBe('/v1/remotes/trueforge/trueforge/')
    expect(catalog.ok).toBe(true)
    expect(catalog.kind).toBe('trueforge')
    expect(catalog.agents.map((a) => a.id)).toEqual(['agent-1', 'agent-2'])
    expect(catalog.sessions.map((s) => s.id)).toEqual(['sess-9', 'sess-4'])
    expect(catalog.sessions[0].title).toBe('refactor the parser')
    expect(catalog.sessions[0].updated_at).toBe('2026-09-22T08:30:00Z')
  })

  it('degrades to an empty catalog when the endpoint is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse({ error: 'unavailable' }, 503)))
    const catalog = await fetchTrueForgeCatalog('trueforge')
    expect(catalog.ok).toBe(false)
    expect(catalog.agents).toEqual([])
    expect(catalog.sessions).toEqual([])
    expect(catalog.detail).toMatch(/503/)
  })

  it('degrades to an empty catalog when the network fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('conn refused') }))
    const catalog = await fetchTrueForgeCatalog('trueforge')
    expect(catalog.ok).toBe(false)
    expect(catalog.agents).toEqual([])
    expect(catalog.sessions).toEqual([])
    expect(catalog.detail).toMatch(/unreachable/i)
  })

  it('never fabricates rows for an empty id', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const catalog = await fetchTrueForgeCatalog('')
    expect(fetchMock).not.toHaveBeenCalled()
    expect(catalog.agents).toEqual([])
    expect(catalog.sessions).toEqual([])
  })
})

describe('#1358 fetchTrueForgeNavbarCatalog', () => {
  it('returns an operate-shaped result carrying only TrueForge rows', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(CATALOG_BODY)))
    const result = await fetchTrueForgeNavbarCatalog('trueforge')
    expect(result.ok).toBe(true)
    const data = result.data as { agents: unknown[]; sessions: unknown[]; rows_are: string }
    expect(data.rows_are).toBe('agents')
    expect(data.agents).toHaveLength(2)
    expect(data.sessions).toHaveLength(2)
  })
})

describe('#1358 fetchRemoteThreadSessions (TrueForge)', () => {
  it('uses the TrueForge endpoint, never the generic operate path', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo) => jsonResponse(CATALOG_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const sessions = await fetchRemoteThreadSessions({
      id: 'trueforge',
      kind: 'trueforge',
      title: 'TrueForge',
    })

    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toEqual(['/v1/remotes/trueforge/trueforge/'])
    expect(urls.some((url) => url.includes('/operate/'))).toBe(false)
    expect(sessions.map((s) => s.memberId)).toEqual(['sess-9', 'sess-4'])
    expect(sessions[0].href).toBe('/chat?remote=trueforge&session=sess-9')
  })
})

describe('#1358 trueForge helper mappers', () => {
  it('maps agents and sessions from the catalog', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(CATALOG_BODY)))
    const catalog = await fetchTrueForgeCatalog('trueforge')
    expect(trueForgeAgentsFromCatalog(catalog)).toEqual([
      { id: 'agent-1', label: 'orchestrator' },
      { id: 'agent-2', label: 'coder' },
    ])
    const sessions = trueForgeMemberSessions(
      { id: 'trueforge', title: 'TrueForge', kind: 'trueforge' },
      catalog,
    )
    expect(sessions[0].startedAt).toBe(Date.parse('2026-09-22T08:30:00Z'))
    expect(sessions[1].startedAt).toBe(0)
  })

  it('returns empty lists for a null catalog', () => {
    expect(trueForgeAgentsFromCatalog(null)).toEqual([])
    expect(
      trueForgeMemberSessions({ id: 'trueforge', title: 'TrueForge', kind: 'trueforge' }, null),
    ).toEqual([])
  })
})

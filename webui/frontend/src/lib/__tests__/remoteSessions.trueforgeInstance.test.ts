/**
 * #1358 follow-up — named TrueForge instances reuse their sessions too.
 *
 * The picker/send paths branch on `isTrueForgeKind`. Matching only the literal
 * `trueforge` id meant a named instance (`trueforge_prod`, `tf_local`) fell to
 * the generic remote path and never used the TrueForge catalog / session
 * picker, so the seat minted a new TrueForge session every turn.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  fetchRemoteThreadSessions,
  isTrueForgeKind,
  remoteListsSessions,
} from '../remoteSessions'

function jsonResponse(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const CATALOG_BODY = {
  object: 'trueforge.catalog',
  remote: 'trueforge_prod',
  kind: 'trueforge',
  ok: true,
  detail: 'TrueForge listed 1 session',
  rows_are: 'agents',
  resume_key: 'session_id',
  agents: [{ id: 'agent-1', label: 'orchestrator', name: 'orchestrator' }],
  sessions: [{ id: 'sess-prod', title: 'prod thread', agent: 'orchestrator' }],
}

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('#1358 isTrueForgeKind named instances', () => {
  it('matches canonical and named TrueForge ids', () => {
    expect(isTrueForgeKind('trueforge')).toBe(true)
    expect(isTrueForgeKind('TrueForge')).toBe(true)
    expect(isTrueForgeKind('trueforge_prod')).toBe(true)
    expect(isTrueForgeKind('trueforge-secondary')).toBe(true)
    expect(isTrueForgeKind('tf_local')).toBe(true)
    expect(isTrueForgeKind('tf-eu')).toBe(true)
  })

  it('rejects foreign and near-miss ids', () => {
    expect(isTrueForgeKind('true_forge')).toBe(false)
    expect(isTrueForgeKind('hermes')).toBe(false)
    expect(isTrueForgeKind('turboforge')).toBe(false)
    expect(isTrueForgeKind('')).toBe(false)
  })
})

describe('#1358 remoteListsSessions named TrueForge instances', () => {
  it('treats named TrueForge instances as session-capable', () => {
    expect(remoteListsSessions({ id: 'trueforge_prod', kind: 'trueforge' })).toBe(true)
    expect(remoteListsSessions({ id: 'tf_local', kind: 'trueforge' })).toBe(true)
    expect(remoteListsSessions({ id: 'box', kind: 'trueforge' })).toBe(true)
  })

  it('still refuses a non-session remote', () => {
    expect(remoteListsSessions({ id: 'omb', kind: 'omb' })).toBe(false)
  })
})

describe('#1358 fetchRemoteThreadSessions named instance', () => {
  it('uses the TrueForge catalog endpoint, never the generic operate path', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo) => jsonResponse(CATALOG_BODY))
    vi.stubGlobal('fetch', fetchMock)

    const sessions = await fetchRemoteThreadSessions({
      id: 'trueforge_prod',
      kind: 'trueforge',
      title: 'TrueForge prod',
    })

    const urls = fetchMock.mock.calls.map((call) => String(call[0]))
    expect(urls).toEqual(['/v1/remotes/trueforge_prod/trueforge/'])
    expect(urls.some((url) => url.includes('/operate/'))).toBe(false)
    expect(sessions.map((s) => s.memberId)).toEqual(['sess-prod'])
  })
})

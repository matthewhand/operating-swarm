import { afterEach, describe, expect, it, vi } from 'vitest'
import { AGENT_EDITS_KEY, saveAgentEdit } from '../agentEdits'
import * as api from '../api'
import {
  fetchCliSessions,
  filterCliSessions,
  formatActivityAge,
  latestCliActivityMs,
  looksLikeSessionId,
  sanitizeCliSessionId,
  selectCliSession,
  type CliProviderSession,
} from '../cliSessions'

function row(id: string, title: string, snippet = ''): CliProviderSession {
  return {
    id,
    title,
    snippet,
    updated_at: '2026-09-05T12:00:00Z',
    source: 'swarm',
  }
}

describe('sanitizeCliSessionId', () => {
  it('accepts storeable ids and rejects secrets / junk', () => {
    expect(sanitizeCliSessionId('sid-ok_1')).toBe('sid-ok_1')
    expect(sanitizeCliSessionId('ses_abc')).toBe('ses_abc')
    expect(sanitizeCliSessionId('sk-live-secret-key')).toBeNull()
    expect(sanitizeCliSessionId('has space')).toBeNull()
    expect(sanitizeCliSessionId('a/b')).toBeNull()
    expect(sanitizeCliSessionId('')).toBeNull()
  })
})

describe('looksLikeSessionId', () => {
  it('mirrors sanitize for paste-id', () => {
    expect(looksLikeSessionId('uuid-like-session')).toBe(true)
    expect(looksLikeSessionId('sk-abc')).toBe(false)
  })
})

describe('formatActivityAge', () => {
  const now = Date.parse('2026-09-05T18:00:00')

  it('uses relative stamps for recent activity', () => {
    expect(formatActivityAge(now - 30_000, now)).toBe('just now')
    expect(formatActivityAge(now - 2 * 60_000, now)).toBe('2m ago')
    expect(formatActivityAge(now - 3 * 60 * 60_000, now)).toBe('3h ago')
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    yesterday.setHours(15, 0, 0, 0)
    expect(formatActivityAge(yesterday.getTime(), now)).toBe('Yesterday')
  })

  it('returns empty for missing or invalid stamps', () => {
    expect(formatActivityAge('', now)).toBe('')
    expect(formatActivityAge('not-a-date', now)).toBe('')
  })
})

describe('filterCliSessions', () => {
  const sessions = [
    row('sid-1', 'First', 'hello'),
    row('sid-2', 'Second', 'again'),
  ]

  it('filters by title, snippet, or id', () => {
    expect(filterCliSessions(sessions, 'second').map((s) => s.id)).toEqual(['sid-2'])
    expect(filterCliSessions(sessions, 'hello').map((s) => s.id)).toEqual(['sid-1'])
    expect(filterCliSessions(sessions, 'sid-2').map((s) => s.id)).toEqual(['sid-2'])
    expect(filterCliSessions(sessions, '')).toHaveLength(2)
  })
})

describe('CLI session Folder cwd (REQ-167)', () => {
  afterEach(() => {
    localStorage.removeItem(AGENT_EDITS_KEY)
    vi.restoreAllMocks()
  })

  it('list and select send Folder when the agent record has one', async () => {
    saveAgentEdit('cli_agent', { folder: '/home/dev/tool' })
    const getSpy = vi.spyOn(api, 'apiGet').mockResolvedValue({
      object: 'cli_session_list',
      agent_id: 'cli_agent',
      cli: 'grok',
      can_list: false,
      sessions: [],
      recent: [],
      empty_reason: null,
      activity_sot: 'swarm',
    } as any)
    const postSpy = vi.spyOn(api, 'apiPost').mockResolvedValue({
      object: 'cli_session_select',
      agent_id: 'cli_agent',
      cli: 'grok',
      conversation_id: 'cli-1',
      cli_session_id: null,
      messages: [],
      status: 'Started a new grok session.',
      collapsed_prior: false,
      import: 'none',
    } as any)

    await fetchCliSessions('cli_agent', 'grok')
    expect(getSpy).toHaveBeenCalledWith(expect.stringContaining('folder=%2Fhome%2Fdev%2Ftool'))

    await selectCliSession({ agentId: 'cli_agent', cli: 'grok', startNew: true })
    expect(postSpy).toHaveBeenCalledWith(
      '/v1/cli-sessions/select/',
      expect.objectContaining({ folder: '/home/dev/tool', start_new: true }),
    )
  })

  it('list and select omit Folder when unset', async () => {
    const getSpy = vi.spyOn(api, 'apiGet').mockResolvedValue({
      object: 'cli_session_list',
      agent_id: 'cli_agent',
      cli: 'grok',
      can_list: false,
      sessions: [],
      recent: [],
      empty_reason: null,
      activity_sot: 'swarm',
    } as any)
    const postSpy = vi.spyOn(api, 'apiPost').mockResolvedValue({
      object: 'cli_session_select',
      agent_id: 'cli_agent',
      cli: 'grok',
      conversation_id: 'cli-1',
      cli_session_id: null,
      messages: [],
      status: 'Started a new grok session.',
      collapsed_prior: false,
      import: 'none',
    } as any)

    await fetchCliSessions('cli_agent', 'grok')
    expect(getSpy.mock.calls[0][0]).not.toContain('folder=')

    await selectCliSession({ agentId: 'cli_agent', cli: 'grok', startNew: true })
    expect(postSpy.mock.calls[0][1]).not.toHaveProperty('folder')
  })
})

describe('latestCliActivityMs (#67)', () => {
  it('returns the newest updated_at across sessions and recent', () => {
    expect(
      latestCliActivityMs({
        sessions: [{ updated_at: '2026-09-05T12:00:00Z' }, { updated_at: '2026-09-06T12:00:00Z' }],
        recent: [{ updated_at: '2026-09-04T12:00:00Z' }],
      }),
    ).toBe(Date.parse('2026-09-06T12:00:00Z'))
  })

  it('returns null when nothing usable exists', () => {
    expect(latestCliActivityMs(null)).toBeNull()
    expect(latestCliActivityMs({ sessions: [], recent: [] })).toBeNull()
    expect(latestCliActivityMs({ sessions: [{ updated_at: 'bogus' }] })).toBeNull()
  })
})


describe('cliSessions #139 folder on select', () => {
  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.removeItem(AGENT_EDITS_KEY)
  })

  it('explicit folder option wins over agent edit (#139 hydrate)', async () => {
    saveAgentEdit('cli_agent', { folder: '/home/dev/tool' })
    const postSpy = vi.spyOn(api, 'apiPost').mockResolvedValue({
      object: 'cli_session_select',
      agent_id: 'cli_agent',
      cli: 'qwen',
      conversation_id: 'c1',
      cli_session_id: 'sess-1',
      messages: [],
      status: 'ok',
      collapsed_prior: false,
      import: 'full',
    } as any)
    await selectCliSession({
      agentId: 'cli_agent',
      cli: 'qwen',
      sessionId: 'sess-1',
      folder: '/home/dev/from-row',
    })
    expect(postSpy).toHaveBeenCalledWith(
      '/v1/cli-sessions/select/',
      expect.objectContaining({ folder: '/home/dev/from-row', session_id: 'sess-1' }),
    )
  })
})


import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  filterRemoteSessionRows,
  mostRecentRemoteSession,
  memberSessionsFromRemoteOperate,
  remoteAgentsFromOperate,
  remoteChatTurnParams,
  remoteListsSessions,
  sessionsFromOperateResult,
} from '../remoteSessions'

describe('remoteSessions (issue #88 AnythingLLM)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('maps operate list agents for the navbar dropdown', () => {
    expect(
      remoteAgentsFromOperate({
        agents: [
          { id: 'desk', name: 'Desk' },
          { id: 'spec', title: 'Specialist' },
        ],
      }),
    ).toEqual([
      { id: 'desk', label: 'Desk' },
      { id: 'spec', label: 'Specialist' },
    ])
  })

  it('treats Octop seats as session-list remotes, including named instances', () => {
    expect(remoteListsSessions({ id: 'octop', kind: 'octop' })).toBe(true)
    expect(remoteListsSessions({ id: 'octop-lab', kind: 'octop-lab' })).toBe(true)
    expect(remoteListsSessions({ id: 'tencent-octop', kind: 'tencent-octop' })).toBe(true)
  })

  it('treats AnythingLLM as a session-list remote', () => {
    expect(remoteListsSessions({ id: 'anythingllm', kind: 'anythingllm' })).toBe(true)
    expect(
      remoteListsSessions({ id: 'box', kind: 'anythingllm', capabilities: { sessions: true } }),
    ).toBe(true)
    expect(remoteListsSessions({ id: 'omb', kind: 'omb' })).toBe(false)
  })

  it('puts the resume key on chat send params', () => {
    expect(remoteChatTurnParams('anythingllm')).toEqual({
      remote: 'anythingllm',
      name: 'anythingllm',
      op: 'send',
    })
    expect(remoteChatTurnParams('anythingllm', 'teamstinky:thread-1')).toEqual({
      remote: 'anythingllm',
      name: 'anythingllm',
      op: 'send',
      session_id: 'teamstinky:thread-1',
      target: 'teamstinky:thread-1',
    })
  })

  it('reads operate list sessions and is searchable', () => {
    const result = {
      remote: 'anythingllm',
      op: 'list',
      ok: true,
      detail: 'listed',
      data: {
        sessions: [
          { id: 'docs', title: 'Docs', snippet: 'workspace', channel: 'Docs' },
          {
            id: 'docs:abc',
            title: 'latest hacker news?',
            snippet: '',
            channel: 'Docs',
          },
          { id: 'onboarding:t1', title: 'onboarding docs', snippet: 'welcome' },
        ],
      },
    }
    const rows = sessionsFromOperateResult(result)
    expect(rows.map((row) => row.id)).toEqual(['docs', 'docs:abc', 'onboarding:t1'])
    expect(filterRemoteSessionRows(rows, 'hacker').map((row) => row.id)).toEqual(['docs:abc'])
    expect(filterRemoteSessionRows(rows, 'docs').map((row) => row.id)).toEqual([
      'docs',
      'docs:abc',
      'onboarding:t1',
    ])

    const sessions = memberSessionsFromRemoteOperate(
      { id: 'anythingllm', kind: 'anythingllm', title: 'AnythingLLM' },
      result,
    )
    expect(sessions).toHaveLength(3)
    expect(sessions[1].href).toBe(
      '/chat?remote=anythingllm&session=docs%3Aabc',
    )
    expect(sessions[1].memberId).toBe('docs:abc')
  })
})

describe('remoteSessions (issue #90 Open WebUI)', () => {
  it('treats Open WebUI as a session-list remote', () => {
    expect(remoteListsSessions({ id: 'openwebui', kind: 'openwebui' })).toBe(true)
    expect(remoteListsSessions({ id: 'owui', kind: 'open-webui' })).toBe(true)
  })

  it('passes session_id on chat turn params for resume', () => {
    expect(remoteChatTurnParams('openwebui', '550e8400-e29b-41d4-a716-446655440000')).toEqual({
      remote: 'openwebui',
      name: 'openwebui',
      op: 'send',
      session_id: '550e8400-e29b-41d4-a716-446655440000',
      target: '550e8400-e29b-41d4-a716-446655440000',
    })
    expect(remoteChatTurnParams('openwebui')).toEqual({
      remote: 'openwebui',
      name: 'openwebui',
      op: 'send',
    })
  })

  it('normalizes operate list sessions and filters when many', () => {
    const rows = sessionsFromOperateResult({
      remote: 'openwebui',
      op: 'list',
      ok: true,
      detail: 'listed',
      data: {
        sessions: [
          { id: 'aaa', title: 'latest hacker news?', snippet: 'hn' },
          { id: 'bbb', title: 'onboarding docs', snippet: 'welcome' },
        ],
      },
    })
    expect(rows.map((row) => row.id)).toEqual(['aaa', 'bbb'])
    expect(filterRemoteSessionRows(rows, 'hacker').map((row) => row.id)).toEqual(['aaa'])
    expect(filterRemoteSessionRows(rows, 'zzz')).toEqual([])
  })
})

describe('#796 — Herdr members populate the session switcher', () => {
  it('maps data.members (herdr agent list) onto session rows named by target', () => {
    const result = {
      ok: true,
      data: {
        members: [
          { kind: 'herdr', name: 'w3:p5', display: 'grok (hermes)', source: 'agent' },
          { kind: 'herdr', name: 'agy', display: '', source: 'agent' },
        ],
      },
    } as unknown as Parameters<typeof sessionsFromOperateResult>[0]
    const rows = sessionsFromOperateResult(result)
    expect(rows.map((r) => r.id)).toEqual(['w3:p5', 'agy'])
    // #787: the friendly display name becomes the title, pane id stays the id.
    expect(rows[0].title).toBe('grok (hermes)')
    expect(rows[1].title).toBe('agy')
  })

  it('still prefers explicit sessions/data arrays when present', () => {
    const result = {
      ok: true,
      data: {
        sessions: [{ id: 'ws-docs:t1', title: 'thread one' }],
        members: [{ kind: 'herdr', name: 'w3:p5', display: 'grok' }],
      },
    } as unknown as Parameters<typeof sessionsFromOperateResult>[0]
    const rows = sessionsFromOperateResult(result)
    expect(rows.map((r) => r.id)).toEqual(['ws-docs:t1'])
  })
})

describe('#852 — most recent session auto-select', () => {
  const row = (id: string, startedAt: number, status: 'running' | 'finished' = 'finished') => ({
    id,
    groupId: 'anythingllm',
    groupKind: 'remote' as const,
    memberId: id,
    title: id,
    snippet: '',
    status,
    startedAt,
    href: `/chat?remote=anythingllm&session=${id}`,
  })

  it('picks the newest session', () => {
    expect(
      mostRecentRemoteSession([row('old', 100), row('new', 200)]),
    ).toMatchObject({ memberId: 'new' })
  })

  it('prefers a running session over a newer finished one', () => {
    expect(
      mostRecentRemoteSession([row('done', 500), row('live', 100, 'running')]),
    ).toMatchObject({ memberId: 'live', status: 'running' })
  })

  it('returns null for empty lists instead of throwing', () => {
    expect(mostRecentRemoteSession([])).toBeNull()
  })
})

// #hermes — sessions ride a nested envelope and stamp epoch-seconds activity.
describe('hermes sessions', () => {
  const payload = {
    remote: 'hermes',
    op: 'list',
    ok: true,
    detail: 'listed Hermes models/sessions/jobs (missing slices stay null)',
    data: {
      models: { object: 'list', data: [{ id: 'hermes-agent' }] },
      sessions: {
        object: 'list',
        data: [
          {
            id: 'run_a',
            title: 'Reply with exactly OK #5',
            preview: 'Reply with exactly: OK',
            started_at: 1790461952.0102215,
            last_active: 1790461955.230066,
            message_count: 2,
          },
          {
            id: 'run_b',
            title: 'Run host task list 500 files summarize #2',
            preview: '[f60012a8] Run a long host task: list 500 files...',
            started_at: 1790450864.0696745,
            last_active: 1790452871.3685114,
            message_count: 13,
          },
        ],
      },
      jobs: { jobs: [] },
    },
  } as never

  it('reads session rows nested under data.sessions.data', () => {
    const rows = sessionsFromOperateResult(payload)
    expect(rows.map((r) => r.id)).toEqual(['run_a', 'run_b'])
    expect(rows[0].title).toBe('Reply with exactly OK #5')
    expect(rows[0].snippet).toBe('Reply with exactly: OK')
  })

  it('maps the nested data.models list onto navbar agent options', () => {
    expect(remoteAgentsFromOperate((payload as { data: unknown }).data)).toEqual([
      { id: 'hermes-agent', label: 'hermes-agent' },
    ])
  })

  it('lands each row on ?remote=hermes&session=<id>', () => {
    const sessions = memberSessionsFromRemoteOperate(
      { id: 'hermes', kind: 'hermes', title: 'Hermes' },
      payload,
    )
    expect(sessions).toHaveLength(2)
    expect(sessions[0].memberId).toBe('run_a')
    expect(sessions[0].href).toBe('/chat?remote=hermes&session=run_a')
  })

  it('turns epoch-seconds last_active into a real (non-1970) startedAt', () => {
    const sessions = memberSessionsFromRemoteOperate(
      { id: 'hermes', kind: 'hermes', title: 'Hermes' },
      payload,
    )
    // `last_active` is epoch seconds (~1.79e9), not ms — a naive pass-through
    // would render 1970. The parser normalises it to ms.
    expect(sessions[0].startedAt).toBe(Date.parse('2026-09-26T22:32:35.230Z'))
    expect(sessions[0].startedAt).toBeGreaterThan(Date.parse('2026-01-01T00:00:00Z'))
  })
})

// #810 — TrueForge: the History picker lists real sessions, never agent rows.
describe('#810 trueforge sessions', () => {
  const tfResult = {
    remote: 'trueforge',
    op: 'list',
    ok: true,      data: {
        rows_are: 'agents',
        resume_key: 'session_id',
        data: [{ id: 'agent-1', name: 'orchestrator' }],
        sessions: [
          {
            id: 'sess-9',
            agent: 'orchestrator',
            title: 'refactor the parser',
            created_at: '2026-09-21T10:00:00Z',
            updated_at: '2026-09-22T08:30:00Z',
          },
          { id: 'sess-4', agent: 'coder' },
        ],
      },
  } as never

  it('maps data.sessions to pickable threads with titles', () => {
    const rows = memberSessionsFromRemoteOperate(
      { id: 'trueforge', title: 'TrueForge', kind: 'trueforge' },
      tfResult,
    )
    expect(rows.map((r) => r.memberId)).toEqual(['sess-9', 'sess-4'])
    expect(rows[0].title).toBe('refactor the parser')
    expect(rows[1].title).toContain('sess-4')
    expect(rows[0].href).toContain('session=sess-9')
  })

  // #1099/#1100: real activity stamps replace the fake `startedAt: index`
  // (row 0 was literally epoch-0). Rows without timestamps stay at 0, which
  // the shared formatters render as *no stamp* — never a 0 or 1970 date.
  it('parses updated_at into a real startedAt and leaves unknown rows at epoch-0', () => {
    const rows = memberSessionsFromRemoteOperate(
      { id: 'trueforge', title: 'TrueForge', kind: 'trueforge' },
      tfResult,
    )
    expect(rows[0].startedAt).toBe(Date.parse('2026-09-22T08:30:00Z'))
    expect(rows[1].startedAt).toBe(0)
  })

  it('falls back to created_at when updated_at is absent', () => {
    const rows = memberSessionsFromRemoteOperate(
      { id: 'trueforge', title: 'TrueForge', kind: 'trueforge' },
      {
        remote: 'trueforge',
        op: 'list',
        ok: true,
        data: {
          rows_are: 'agents',
          sessions: [{ id: 's1', created_at: '2026-09-20T09:00:00Z' }],
        },
      } as never,
    )
    expect(rows[0].startedAt).toBe(Date.parse('2026-09-20T09:00:00Z'))
  })

  it('never presents agent rows as sessions when data.sessions is absent', () => {
    const rows = memberSessionsFromRemoteOperate(
      { id: 'trueforge', title: 'TrueForge', kind: 'trueforge' },
      {
        remote: 'trueforge',
        op: 'list',
        ok: true,
        data: { rows_are: 'agents', data: [{ id: 'agent-1', name: 'orchestrator' }] },
      } as never,
    )
    expect(rows).toEqual([])
  })

  it('composer agent rows still map from the same payload (both lists coexist)', () => {
    const agents = remoteAgentsFromOperate((tfResult as { data: unknown }).data)
    expect(agents.map((a) => a.id)).toEqual(['agent-1'])
  })
})

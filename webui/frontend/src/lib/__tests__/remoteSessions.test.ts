import { describe, expect, it, vi, beforeEach } from 'vitest'
import {
  filterRemoteSessionRows,
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

describe('remoteSessions (issue #89 Letta)', () => {
  it('treats Letta as a session-list remote', () => {
    expect(remoteListsSessions({ id: 'letta', kind: 'letta' })).toBe(true)
    expect(
      remoteListsSessions({ id: 'box', kind: 'letta', capabilities: { sessions: true } }),
    ).toBe(true)
  })

  it('puts the Letta resume key on chat send params', () => {
    expect(remoteChatTurnParams('letta')).toEqual({
      remote: 'letta',
      name: 'letta',
      op: 'send',
    })
    expect(remoteChatTurnParams('letta', 'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')).toEqual({
      remote: 'letta',
      name: 'letta',
      op: 'send',
      session_id: 'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      target: 'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
    })
  })

  it('reads Letta operate list sessions and is searchable', () => {
    const result = {
      remote: 'letta',
      op: 'list',
      ok: true,
      detail: 'listed',
      data: {
        sessions: [
          {
            id: 'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
            title: 'Memory clerk',
            snippet: 'long-term memory agent',
            channel: 'memgpt_agent',
          },
          {
            id: 'agent-bbbbbbbb-cccc-4ddd-8eee-ffffffffffff',
            title: 'Onboarding flow',
            snippet: 'workflow for new hires',
            channel: 'workflow_agent',
          },
        ],
      },
    }
    const rows = sessionsFromOperateResult(result)
    expect(rows.map((row) => row.id)).toEqual([
      'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
      'agent-bbbbbbbb-cccc-4ddd-8eee-ffffffffffff',
    ])
    expect(filterRemoteSessionRows(rows, 'onboarding').map((row) => row.id)).toEqual([
      'agent-bbbbbbbb-cccc-4ddd-8eee-ffffffffffff',
    ])
    expect(filterRemoteSessionRows(rows, 'memory').map((row) => row.id)).toEqual([
      'agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
    ])

    const sessions = memberSessionsFromRemoteOperate(
      { id: 'letta', kind: 'letta', title: 'Letta' },
      result,
    )
    expect(sessions).toHaveLength(2)
    expect(sessions[0].href).toBe(
      '/chat?remote=letta&session=agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee',
    )
    expect(sessions[0].memberId).toBe('agent-aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee')
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

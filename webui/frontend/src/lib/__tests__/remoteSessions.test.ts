import { describe, expect, it, vi, beforeEach } from 'vitest'
import * as api from '../api'
import {
  filterRemoteSessionRows,
  memberSessionsFromRemoteOperate,
  remoteChatTurnParams,
  remoteListsSessions,
  sessionsFromOperateResult,
} from '../remoteSessions'

describe('remoteSessions (issue #88 AnythingLLM)', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
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

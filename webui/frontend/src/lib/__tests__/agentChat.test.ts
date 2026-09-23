import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  AGENT_CONVERSATION_EVENT,
  DEFAULT_AGENT_ID,
  activeTaskSessionCount,
  agentChatHref,
  agentIdFromBlueprint,
  compactAgentThread,
  startContextFromHere,
  conversationIdForAgent,
  conversationIdForTask,
  fetchAgentThread,
  listTaskSessions,
  peekConversationIdForAgent,
  setConversationIdForAgent,
} from '../agentChat'

describe('agentIdFromBlueprint', () => {
  it('maps empty / whitespace to _default', () => {
    expect(agentIdFromBlueprint('')).toBe(DEFAULT_AGENT_ID)
    expect(agentIdFromBlueprint('  ')).toBe(DEFAULT_AGENT_ID)
    expect(agentIdFromBlueprint(null)).toBe(DEFAULT_AGENT_ID)
    expect(agentIdFromBlueprint('jeeves')).toBe('jeeves')
  })
})

describe('conversationIdForAgent', () => {
  afterEach(() => {
    window.localStorage.clear()
  })

  it('returns the same id for the same agent across calls', () => {
    const first = conversationIdForAgent('codey')
    const second = conversationIdForAgent('codey')
    expect(first).toBe(second)
    expect(conversationIdForAgent('other')).not.toBe(first)
  })

  it('peeks a stored id without minting', () => {
    expect(peekConversationIdForAgent('codey')).toBeNull()
    const minted = conversationIdForAgent('codey')
    expect(peekConversationIdForAgent('codey')).toBe(minted)
  })

  it('persists a selected session id and rehydrates it after remount', () => {
    setConversationIdForAgent('codey', 'sess-notes')
    expect(peekConversationIdForAgent('codey')).toBe('sess-notes')
    expect(conversationIdForAgent('codey')).toBe('sess-notes')
    expect(agentChatHref('codey')).toBe('/chat?blueprint=codey&session=sess-notes')
    expect(agentChatHref('stewie')).toBe('/chat?blueprint=stewie')
    expect(agentChatHref('team:demo')).toBe('/chat?team=demo')
    expect(agentChatHref('remote:omb')).toBe('/chat?remote=omb')
    setConversationIdForAgent('team:demo', 'sess-team')
    expect(agentChatHref('team:demo')).toBe('/chat?team=demo&session=sess-team')
    expect(agentChatHref('team:demo')).not.toMatch(/blueprint=/)
    setConversationIdForAgent('remote:omb', 'sess-remote')
    expect(agentChatHref('remote:omb')).toBe('/chat?remote=omb&session=sess-remote')
    expect(agentChatHref('remote:omb')).not.toMatch(/blueprint=/)
  })

  it('keeps the selected id after the module-level helpers are called again (unmount)', () => {
    setConversationIdForAgent('cli_agent', 'cli-cli_agent-abc')
    expect(peekConversationIdForAgent('cli_agent')).toBe('cli-cli_agent-abc')
    expect(conversationIdForAgent('cli_agent')).toBe('cli-cli_agent-abc')
    expect(agentChatHref('cli_agent')).toContain('session=cli-cli_agent-abc')
  })

  it('emits AGENT_CONVERSATION_EVENT when the selected id is stored', () => {
    const seen: string[] = []
    const onChange = (event: Event) => {
      const detail = (event as CustomEvent<{ conversationId?: string }>).detail
      if (detail?.conversationId) seen.push(detail.conversationId)
    }
    window.addEventListener(AGENT_CONVERSATION_EVENT, onChange)
    setConversationIdForAgent('codey', 'sess-b')
    window.removeEventListener(AGENT_CONVERSATION_EVENT, onChange)
    expect(seen).toEqual(['sess-b'])
    setConversationIdForAgent('codey', 'sess-b')
    expect(seen).toEqual(['sess-b'])
  })

  it('reuses the stored id when new chat per task is off', () => {
    const reused = conversationIdForTask('codey', { newChatPerTask: false })
    expect(reused).toBe(conversationIdForAgent('codey'))
  })

  it('mints a new session per task when on, without sharing transcripts', () => {
    const one = conversationIdForTask('worker', { newChatPerTask: true, taskId: 'alpha' })
    const two = conversationIdForTask('worker', { newChatPerTask: true, taskId: 'beta' })
    expect(one).not.toBe(two)
    expect(one).not.toBe(conversationIdForAgent('worker'))
    expect(listTaskSessions('worker')).toEqual(expect.arrayContaining([one, two]))
    expect(activeTaskSessionCount('worker')).toBeGreaterThanOrEqual(2)
  })
})

describe('fetchAgentThread', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('returns server messages when the thread endpoint succeeds', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'jeeves',
          conversation_id: 'agt-1-jeeves',
          messages: [
            { role: 'user', content: 'hi' },
            {
              role: 'status',
              content: 'Started a new grok session.',
              ts: '2026-09-05T12:00:00Z',
            },
            { role: 'assistant', content: 'hello' },
          ],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('jeeves')
    expect(thread.messages).toEqual([
      { role: 'user', content: 'hi' },
      {
        role: 'status',
        content: 'Started a new grok session.',
        ts: '2026-09-05T12:00:00Z',
      },
      { role: 'assistant', content: 'hello' },
    ])
    expect(thread.conversation_id).toBe('agt-1-jeeves')
    expect(thread.summaries).toEqual([])
  })

  it('keeps prior_history as a system archive row', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'cli_agent',
          conversation_id: 'cli-cli_agent-abc',
          messages: [
            { role: 'system', content: '**User:** old', kind: 'prior_history' },
            { role: 'status', content: 'Switched to grok session sid-1.' },
          ],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('cli_agent')
    expect(thread.messages).toEqual([
      { role: 'system', content: '**User:** old', kind: 'prior_history' },
      { role: 'status', content: 'Switched to grok session sid-1.' },
    ])
  })

  it('reconstructs chrome from turns + ui_events', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'jeeves',
          conversation_id: 'agt-1-jeeves',
          turns: [{ role: 'user', content: 'hi', seq: 0 }],
          ui_events: [
            {
              role: 'status',
              content: 'Started a new grok session.',
              ts: '2026-09-05T12:00:00Z',
              seq: 1,
            },
          ],
          messages: [{ role: 'user', content: 'stale' }],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('jeeves')
    expect(thread.messages).toEqual([
      { role: 'user', content: 'hi' },
      {
        role: 'status',
        content: 'Started a new grok session.',
        ts: '2026-09-05T12:00:00Z',
      },
    ])
  })

  it('keeps created_at as ts so status chrome can show when it occurred', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'jeeves',
          conversation_id: 'agt-1-jeeves',
          messages: [
            {
              role: 'info',
              content: 'Rate limited — retrying with grok',
              created_at: '2026-09-05T12:00:00Z',
            },
          ],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('jeeves')
    expect(thread.messages).toEqual([
      {
        role: 'status',
        content: 'Rate limited — retrying with grok',
        ts: '2026-09-05T12:00:00Z',
      },
    ])
  })

  it('normalises info/system thread rows to status chrome', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'jeeves',
          conversation_id: 'agt-1-jeeves',
          messages: [
            { role: 'info', content: 'Connecting…' },
            { role: 'system', content: 'Session ready.' },
            { role: 'user', content: 'hi' },
          ],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('jeeves')
    expect(thread.messages).toEqual([
      { role: 'status', content: 'Connecting…' },
      { role: 'status', content: 'Session ready.' },
      { role: 'user', content: 'hi' },
    ])
  })

  it('returns summaries from the thread endpoint', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'jeeves',
          conversation_id: 'agt-1-jeeves',
          messages: [{ role: 'user', content: 'hi' }],
          summaries: [
            {
              id: 1,
              conversation_id: 'agt-1-jeeves',
              span: { start: 0, end: 0 },
              parent_summary_id: null,
              body: 'digest',
              created_at: '2026-09-03T00:00:00Z',
              replaced_count: 1,
            },
          ],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('jeeves')
    expect(thread.summaries).toHaveLength(1)
    expect(thread.summaries[0].body).toBe('digest')
  })

  it('requests a specific conversation id for a scale-out session', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        agent_id: 'codey',
        conversation_id: 'sess-worker-2',
        messages: [],
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    const thread = await fetchAgentThread('codey', 'sess-worker-2')
    expect(thread.conversation_id).toBe('sess-worker-2')
    expect(String(fetchMock.mock.calls[0][0])).toContain('conversation_id=sess-worker-2')
  })

  it('surfaces session_missing so Chat does not swap transcripts', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'codey',
          conversation_id: 'sess-gone',
          session_missing: true,
          messages: [],
        }),
      } as Response),
    )
    const thread = await fetchAgentThread('codey', 'sess-gone')
    expect(thread.session_missing).toBe(true)
    expect(thread.messages).toEqual([])
    expect(thread.conversation_id).toBe('sess-gone')
  })

  it('surfaces failure when fetch is offline (REQ-171A-4 / #604)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new Error('offline')),
    )
    await expect(fetchAgentThread('jeeves')).rejects.toThrow('offline')
  })

  it('surfaces failure when the thread endpoint returns 500', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: 'thread store unavailable' }),
      } as Response),
    )
    await expect(fetchAgentThread('jeeves')).rejects.toThrow('thread store unavailable')
  })

  it('calls the thread endpoint for a remote agent id', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        agent_id: 'remote:omb',
        conversation_id: 'remote-omb',
        kind: 'remote',
        editable: false,
        messages: [{ role: 'user', content: 'seeded remote' }],
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    const thread = await fetchAgentThread('remote:omb', 'remote-omb')
    expect(thread.messages).toEqual([{ role: 'user', content: 'seeded remote' }])
    expect(thread.editable).toBe(false)
    expect(String(fetchMock.mock.calls[0][0])).toContain('agent=remote%3Aomb')
    expect(String(fetchMock.mock.calls[0][0])).toContain('conversation_id=remote-omb')
  })

  it('appends &flush=1 when flush option is true', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        agent_id: 'remote:herdr',
        conversation_id: 'remote-herdr-session',
        messages: [],
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    await fetchAgentThread('remote:herdr', 'remote-herdr-session', { flush: true })
    expect(String(fetchMock.mock.calls[0][0])).toContain('&flush=1')
  })
})

describe('compactAgentThread', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts the backlog and returns the summary tree', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        summary: {
          id: 2,
          conversation_id: 'c1',
          span: { start: 0, end: 1 },
          parent_summary_id: 1,
          body: 'outer',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
        summaries: [
          {
            id: 1,
            conversation_id: 'c1',
            span: { start: 0, end: 1 },
            parent_summary_id: null,
            body: 'inner',
            created_at: '2026-09-03T00:00:00Z',
            replaced_count: 2,
          },
          {
            id: 2,
            conversation_id: 'c1',
            span: { start: 0, end: 1 },
            parent_summary_id: 1,
            body: 'outer',
            created_at: '2026-09-03T00:00:00Z',
            replaced_count: 2,
          },
        ],
        raw_count: 2,
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    const result = await compactAgentThread({
      conversationId: 'c1',
      agentId: 'jeeves',
      messages: [
        { role: 'user', content: 'hi' },
        { role: 'assistant', content: 'hello' },
      ],
    })
    expect(result.summary.parent_summary_id).toBe(1)
    expect(result.summaries).toHaveLength(2)
    expect(fetchMock).toHaveBeenCalled()
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toBe('/chat/compact/')
    expect(init.method).toBe('POST')
  })

  it('posts through_message_id for compress-to-here', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        summary: {
          id: 1,
          conversation_id: 'c1',
          span: { start: 0, end: 0 },
          parent_summary_id: null,
          body: 'digest',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 1,
        },
        summaries: [
          {
            id: 1,
            conversation_id: 'c1',
            span: { start: 0, end: 0 },
            parent_summary_id: null,
            body: 'digest',
            created_at: '2026-09-03T00:00:00Z',
            replaced_count: 1,
          },
        ],
        raw_count: 2,
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    await compactAgentThread({
      conversationId: 'c1',
      agentId: 'jeeves',
      messages: [
        { role: 'user', content: 'hi' },
        { role: 'assistant', content: 'hello' },
      ],
      spanStart: 0,
      spanEnd: 0,
      throughMessageId: 12,
    })
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body))
    expect(body.through_message_id).toBe(12)
    expect(body.span_end).toBe(0)
  })

  it('posts start_offset and confirm for start-context-from-here', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        applied: false,
        warning: true,
        reason: 'over_full_warning',
        info: 'Starting context here still leaves usage at 93% (cull trigger 90%). Confirm to proceed or cancel.',
        start_offset: 2,
        estimated_pct: 93,
        cull_trigger_pct: 90,
        context: [{ role: 'user', content: 'keep' }],
        context_meta: { start_offset: 2, last_event: null },
      }),
    } as Response)
    vi.stubGlobal('fetch', fetchMock)
    const result = await startContextFromHere({
      conversationId: 'c1',
      agentId: 'jeeves',
      messages: [
        { role: 'user', content: 'drop' },
        { role: 'assistant', content: 'also' },
        { role: 'user', content: 'keep' },
      ],
      startOffset: 2,
      confirm: false,
    })
    expect(result.warning).toBe(true)
    expect(result.applied).toBe(false)
    expect(result.start_offset).toBe(2)
    const body = JSON.parse(String(fetchMock.mock.calls[0][1].body))
    expect(body.start_offset).toBe(2)
    expect(body.confirm).toBe(false)
  })
})

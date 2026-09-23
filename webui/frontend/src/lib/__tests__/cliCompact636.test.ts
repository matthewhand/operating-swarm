/**
 * #636 — orchestrating a CLI-seat compact: summarise server-side (the same
 * POST /chat/compact/ the API flow uses), then start a fresh CLI session via
 * the existing start_new select path so the new process carries the summary.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const calls: { path: string; body?: unknown }[] = []

vi.mock('../api', () => ({
  apiPost: vi.fn(async (path: string, body?: unknown) => {
    calls.push({ path, body })
    if (path === '/chat/compact/') {
      return {
        summary: { id: 'sum-1', span: [0, 10], body: 'Summary body' },
        summaries: [{ id: 'sum-1', span: [0, 10], body: 'Summary body' }],
        raw_count: 10,
      }
    }
    if (path === '/v1/cli-sessions/select/') {
      return {
        object: 'cli_session_select',
        agent_id: 'cli_agent',
        cli: 'grok',
        conversation_id: 'conv-new-1',
        cli_session_id: null,
        messages: [],
        status: 'Started a new grok session.',
        collapsed_prior: false,
        import: 'none',
      }
    }
    return {}
  }),
  apiGet: vi.fn(async () => ({})),
}))

import { compactCliThread } from '../cliCompact'

describe('#636 compactCliThread', () => {
  beforeEach(() => {
    calls.length = 0
    try {
      localStorage.clear()
    } catch {
      /* non-browser */
    }
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('summarises via /chat/compact/ then starts a new CLI session', async () => {
    const result = await compactCliThread({
      conversationId: 'conv-1',
      agentId: 'cli_agent',
      cli: 'grok',
      messages: [
        { role: 'user', content: 'hello' },
        { role: 'assistant', content: 'hi' },
      ],
      defaultLlmReady: true,
    })

    expect(calls.map((c) => c.path)).toEqual([
      '/chat/compact/',
      '/v1/cli-sessions/select/',
    ])
    expect(calls[1].body).toMatchObject({ agent: 'cli_agent', start_new: true })
    expect(result.summaryBody).toBe('Summary body')
    expect(result.newConversationId).toBe('conv-new-1')
    expect(result.status).toBe('Started a new grok session.')
  })

  it('refuses when no default API is configured and the provider lacks a hook', async () => {
    await expect(
      compactCliThread({
        conversationId: 'conv-1',
        agentId: 'cli_agent',
        cli: 'grok',
        messages: [{ role: 'user', content: 'hello' }],
        defaultLlmReady: false,
      }),
    ).rejects.toThrow(/no api is configured/i)
    expect(calls).toEqual([])
  })

  it('refuses without messages', async () => {
    await expect(
      compactCliThread({
        conversationId: 'conv-1',
        agentId: 'cli_agent',
        cli: 'grok',
        messages: [],
        defaultLlmReady: true,
      }),
    ).rejects.toThrow(/nothing to compact/i)
    expect(calls).toEqual([])
  })

  it('persists the new conversation id for the seat', async () => {
    await compactCliThread({
      conversationId: 'conv-1',
      agentId: 'cli_agent',
      cli: 'grok',
      messages: [{ role: 'user', content: 'hello' }],
      defaultLlmReady: true,
    })
    const raw = localStorage.getItem('swarm_agent_chat:cli_agent')
    expect(raw).toBe('conv-new-1')
  })
})

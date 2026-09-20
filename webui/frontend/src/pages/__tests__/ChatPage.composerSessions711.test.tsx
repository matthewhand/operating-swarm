/**
 * #711 — the composer picker's CLI stage 2 offers the CLI's resumable
 * sessions (REQ-104 payload), fetched when the picker opens (not on mount),
 * and picking one runs exactly what the History switcher runs:
 * POST /v1/cli-sessions/select/ → CLI_SESSION_SWITCHED_EVENT.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import ChatPage from '../ChatPage'

type WsHandler = ((ev?: Event) => void) | null

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  onopen: WsHandler = null
  onmessage: WsHandler = null
  onclose: WsHandler = null
  send = vi.fn()
  close = vi.fn()
  url: string
  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

function renderChat(initialEntry = '/chat') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const REAL_CLI_AGENTS = {
  clis: ['grok'],
  known: ['grok'],
  configured: ['grok'],
  discovered: ['grok'],
  installed: ['grok'],
  suggestions: {},
  default_cli: 'grok',
  native_consensus: { grok: ['--best-of-n', '{n}'] },
  catalog: {},
  list_models: { grok: ['grok', 'models'] },
  rail: [
    {
      id: 'cli_agent',
      object: 'cli.agent',
      name: 'cli_agent',
      cli: 'grok',
      kind: 'cli',
      description: 'Host CLI',
      installed: true,
    },
  ],
}

const SESSION_LIST = {
  object: 'cli_session_list',
  agent_id: 'cli_agent',
  cli: 'grok',
  can_list: true,
  sessions: [
    { id: 'sess-1', title: 'Refactor auth', snippet: 'let me refactor', updated_at: '2026-09-20T10:00:00Z', source: 'provider' },
  ],
  recent: [],
  empty_reason: null,
}

const SELECT_RESULT = {
  object: 'cli_session_select',
  agent_id: 'cli_agent',
  cli: 'grok',
  conversation_id: 'conv-9',
  cli_session_id: 'sess-1',
  messages: [],
  status: 'Switched to sess-1',
  collapsed_prior: false,
  import: 'full',
}

type FetchCall = { url: string; init?: RequestInit }

function stubChat(opts: { selectFails?: boolean } = {}) {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  const calls: FetchCall[] = []
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    if (url.includes('/v1/cli-sessions/select')) {
      if (opts.selectFails) {
        return { ok: false, status: 500, json: async () => ({ detail: 'boom' }) } as Response
      }
      return { ok: true, status: 200, json: async () => SELECT_RESULT } as Response
    }
    if (url.includes('/v1/cli-sessions')) {
      return { ok: true, status: 200, json: async () => SESSION_LIST } as Response
    }
    if (url.includes('/v1/cli-agents/') && url.includes('/models')) {
      return { ok: true, status: 200, json: async () => ({ cli: 'grok', models: ['grok-4'] }) } as Response
    }
    if (url.includes('/v1/cli-agents')) {
      return { ok: true, status: 200, json: async () => REAL_CLI_AGENTS } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
        messages: [],
      }),
    } as Response
  })
  vi.stubGlobal('fetch', fetchMock)
  return { calls, fetchMock }
}

function postBodies(calls: FetchCall[], path: string): Array<Record<string, unknown>> {
  return calls
    .filter((c) => c.url.includes(path) && c.init?.method === 'POST' && typeof c.init.body === 'string')
    .map((c) => JSON.parse(c.init!.body as string) as Record<string, unknown>)
}

describe('#711 CLI resumable sessions in the composer picker', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('stage 2 lists the sessions; picking one runs the REQ-104 select flow', async () => {
    const { calls } = stubChat()
    const switched: Array<CustomEvent<Record<string, unknown>>> = []
    window.addEventListener('swarm:cli-session-switched', (e) => {
      switched.push(e as CustomEvent<Record<string, unknown>>)
    })
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    // Deferred fetch: opening the picker pulls the session payload.
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/v1/cli-sessions'))).toBe(true)
    })

    // Descend into the CLI provider; the session row rides stage 2.
    fireEvent.click(await screen.findByText('grok'))
    fireEvent.click(await screen.findByText('Refactor auth'))

    await waitFor(() => {
      expect(postBodies(calls, '/v1/cli-sessions/select')).toHaveLength(1)
    })
    expect(postBodies(calls, '/v1/cli-sessions/select')[0]).toMatchObject({
      agent: 'cli_agent',
      cli: 'grok',
      session_id: 'sess-1',
      start_new: false,
    })
    await waitFor(() => {
      expect(switched).toHaveLength(1)
    })
    expect(switched[0].detail).toMatchObject({
      agentId: 'cli_agent',
      conversationId: 'conv-9',
    })
  })

  it('does not fetch cli-sessions on mount — only when the picker opens', async () => {
    const { calls } = stubChat()
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/v1/cli-agents'))).toBe(true)
    })
    expect(calls.some((c) => c.url.includes('/v1/cli-sessions'))).toBe(false)

    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    await waitFor(() => {
      expect(calls.some((c) => c.url.includes('/v1/cli-sessions'))).toBe(true)
    })
  })

  it('a failed select surfaces a toast, never a silent no-op', async () => {
    stubChat({ selectFails: true })
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('grok'))
    fireEvent.click(await screen.findByText('Refactor auth'))
    expect(await screen.findByText('Could not start CLI session')).toBeTruthy()
  })
})

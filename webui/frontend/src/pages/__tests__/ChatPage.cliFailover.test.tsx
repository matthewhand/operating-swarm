import { act, fireEvent, render, screen } from '@testing-library/react'
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

const CLI_AGENTS = {
  clis: ['agy', 'claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
  known: ['agy', 'claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
  configured: ['pi', 'agy', 'claude', 'codex'],
  discovered: ['pi', 'agy', 'claude', 'codex'],
  installed: ['pi', 'agy', 'claude', 'codex'],
  suggestions: {},
  default_cli: 'pi',
  native_consensus: {},
  catalog: {},
  list_models: {},
  rail: [
    {
      id: 'cli_agent',
      object: 'cli.agent',
      name: 'cli_agent',
      cli: 'pi',
      kind: 'cli',
      description: 'Host CLI',
      installed: true,
    },
  ],
}

function stubChat() {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/cli-agents/') && url.includes('/models')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ cli: 'pi', models: [] }),
        } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => CLI_AGENTS,
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
          messages: [],
        }),
      } as Response
    }),
  )
}

function sendComposer(text: string) {
  const composer = screen.getByRole('textbox', { name: 'Chat message' })
  fireEvent.change(composer, { target: { value: text } })
  fireEvent.submit(composer.closest('form')!)
  const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
  return JSON.parse(ws.send.mock.calls[0][0] as string)
}

describe('ChatPage cli_agent dropdown is strict (#99)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('WS frame for cli=pi includes failover: false and no other CLIs', async () => {
    stubChat()
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=pi')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const frame = sendComposer('hello pi')
    expect(frame).toMatchObject({
      message: 'hello pi',
      blueprint: 'cli_agent',
      params: { cli: 'pi', failover: false },
    })
    expect(frame.params.cli).toBe('pi')
    expect(frame.params.failover).toBe(false)
    expect(frame.params.fallback).toBeUndefined()
  })

  it('empty session still sends the dropdown CLI, not a cascade', async () => {
    stubChat()
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=pi')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const frame = sendComposer('mint a session')
    expect(frame.params).toMatchObject({ cli: 'pi', failover: false })
    expect(frame.params.fallback).toBeUndefined()
    expect(frame.params.cli).toBe('pi')
  })
})

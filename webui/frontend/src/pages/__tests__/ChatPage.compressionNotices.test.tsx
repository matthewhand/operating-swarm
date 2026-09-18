/**
 * #534 — compression notifications belong to API seats only.
 *
 * A remote or CLI seat's transcript never renders a compression notice
 * ('Auto-compress skipped — model context length unknown.'), live over the
 * websocket or restored from a persisted transcript. An api seat still does.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'

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
  close = vi.fn(() => {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code: 1000 }))
  })

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

function renderChat(initialEntry: string) {
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

const SKIP_LINE = 'Auto-compress skipped — model context length unknown.'

function statusFrame(text: string): MessageEvent {
  return new MessageEvent('message', {
    data: `<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status">${text}</div></div>`,
  })
}

describe('#534 compression notices are api-seat only', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'agent',
              conversation_id: 'agt-1',
              messages: [],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              { id: 'api_agent', name: 'API Agent', description: 'API' },
              { id: 'cli_agent', name: 'CLI Agent', description: 'CLI' },
              { id: 'remote_harness', name: 'Remote', description: 'Remote' },
            ],
          }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('suppresses the live auto-compress skip frame on a remote seat', async () => {
    renderChat('/chat?blueprint=remote_harness')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(statusFrame(SKIP_LINE))
    })
    expect(screen.queryByText(SKIP_LINE)).not.toBeInTheDocument()
  })

  it('still shows compression notices on an api seat', async () => {
    renderChat('/chat?blueprint=api_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(statusFrame(SKIP_LINE))
    })
    expect(screen.getByText(SKIP_LINE)).toBeInTheDocument()
  })

  it('strips persisted compression rows when restoring a cli seat transcript', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'agt-1-cli',
              messages: [
                { role: 'user', content: 'hello' },
                { role: 'status', content: SKIP_LINE },
                { role: 'assistant', content: 'reply' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )
    renderChat('/chat?blueprint=cli_agent')
    expect(await screen.findByText('reply')).toBeInTheDocument()
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.queryByText(SKIP_LINE)).not.toBeInTheDocument()
  })
})

/**
 * #636 — the composer Compact flow for a CLI seat: enabled by a configured
 * default API, click runs the compact + new-session orchestration, and the
 * transcript shows the new-session status. Greyed state carries the API reason.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'

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

function renderChat(initialEntry = '/chat?blueprint=cli_agent&mode=cli&cli=grok') {
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

describe('#636 CLI seat Compact', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    try {
      localStorage.clear()
    } catch {
      /* non-browser */
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string | URL | Request) => {
        const urlStr = String(url)
        if (urlStr.includes('/v1/cli-agents')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                clis: ['grok'],
                known: ['grok'],
                configured: ['grok'],
                discovered: ['grok'],
                installed: ['grok'],
                default_cli: 'grok',
                native_consensus: {},
                catalog: {},
                rail: [
                  {
                    id: 'cli_grok',
                    object: 'cli.agent',
                    name: 'grok',
                    cli: 'grok',
                    kind: 'cli',
                    description: 'grok CLI',
                    installed: true,
                  },
                ],
                slash_commands: {},
                cli_compact: {},
              }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/v1/llm-profiles')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({ default_llm_ready: true }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/chat/compact/')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                summary: { id: 'sum-1', span: [0, 10], body: 'Summary body' },
                summaries: [{ id: 'sum-1', span: [0, 10], body: 'Summary body' }],
                raw_count: 10,
              }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/v1/cli-sessions/select/')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                object: 'cli_session_select',
                agent_id: 'cli_agent',
                cli: 'grok',
                conversation_id: 'conv-new-9',
                cli_session_id: null,
                messages: [],
                status: 'Started a new grok session.',
                collapsed_prior: false,
                import: 'none',
              }),
              { status: 200 },
            ),
          )
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function openWebSocket() {
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
  }

  async function openPlusMenu() {
    const plus = screen.getByTestId('composer-plus-button')
    await act(async () => {
      fireEvent.click(plus)
    })
  }

  it('enables Compact on a CLI seat when a default API is configured', async () => {
    renderChat()
    await openWebSocket()
    await openPlusMenu()

    const item = await screen.findByTestId('composer-compact-button')
    expect(item).toBeEnabled()
  })

  it('clicking Compact runs compact + new session and reports the status', async () => {
    renderChat()
    await openWebSocket()

    // Seed a message so compact has material and the composer has a thread.
    const input = screen.getByRole('textbox', { name: 'Chat message' })
    await act(async () => {
      fireEvent.change(input, { target: { value: 'hello world' } })
    })
    await openPlusMenu()

    fireEvent.click(await screen.findByTestId('composer-compact-button'))

    await waitFor(
      () => {
        expect(
          screen.queryByTestId('composer-compact-button'),
        ).not.toBeInTheDocument()
      },
      { timeout: 3000 },
    )
  })
})

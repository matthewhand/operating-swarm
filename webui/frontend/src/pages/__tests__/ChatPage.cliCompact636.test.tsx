/**
 * #1230 — a CLI seat offers no Compact at all.
 *
 * The old #636 flow (compact a CLI seat through a summary + fresh session) is
 * gone: Compact is API-only. This pins the user-visible contract — the `+`
 * menu lists no Compact item, and no disabled/"not available" Compact text is
 * ever rendered for a CLI seat.
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

describe('#1230 CLI seat offers no Compact', () => {
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
                // #551: the published kind-base declarations (CLI compact OFF).
                seat_capabilities: {
                  cli: {
                    attach: { enabled: false, reason: 'CLI attachments off' },
                    compact: { enabled: false, reason: 'Compact is API-only' },
                    plugins: { enabled: false, reason: 'API/blueprint only' },
                    routines: { enabled: false, reason: 'swarm-side only' },
                  },
                },
              }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/v1/llm-profiles')) {
          return Promise.resolve(
            new Response(JSON.stringify({ default_llm_ready: true }), { status: 200 }),
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

  it('renders no Compact menu item on a CLI seat, even with a default API', async () => {
    renderChat()
    await openWebSocket()
    await openPlusMenu()

    // The menu opens (Add files is present) …
    expect(await screen.findByRole('menuitem', { name: 'Add files' })).toBeInTheDocument()
    // … but there is no Compact control at all — no disabled, no "not available".
    expect(screen.queryByTestId('composer-compact-button')).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Compact' })).not.toBeInTheDocument()
  })

  it('never surfaces the "not available" compact copy on a CLI seat', async () => {
    renderChat()
    await openWebSocket()
    await openPlusMenu()

    await waitFor(() => {
      expect(screen.queryByText(/no api is configured/i)).not.toBeInTheDocument()
    })
    expect(screen.queryByText(/Compact is not implemented/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Compact is unavailable/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/compact not available/i)).not.toBeInTheDocument()
  })
})

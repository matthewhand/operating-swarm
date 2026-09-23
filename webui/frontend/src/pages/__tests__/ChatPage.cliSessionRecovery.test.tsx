import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { CLI_SESSION_RECOVERY_MESSAGE } from '../../lib/cliSessionRecovery'

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

function LocationProbe() {
  const [params] = useSearchParams()
  return <div data-testid="chat-location">{params.toString()}</div>
}

function renderChat(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route
              path="/chat"
              element={
                <>
                  <LocationProbe />
                  <ChatPage />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function okJson(body: unknown): Response {
  return {
    ok: true,
    status: 200,
    json: async () => body,
  } as Response
}

function threadCalls(): Array<{ url: string; init?: RequestInit }> {
  return (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
    .map(([input, init]) => ({ url: String(input), init: init as RequestInit | undefined }))
    .filter((row) => row.url.includes('/chat/thread/'))
}

const POISON = "No CLI agents are configured. Add a 'cli_agents' block to your swarm config."

describe('ChatPage CLI session recovery (#274)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          const action =
            typeof init?.body === 'string'
              ? (JSON.parse(init.body) as { action?: string }).action
              : undefined
          if (action === 'clear') {
            return okJson({
              agent_id: 'cli_agent',
              conversation_id: 'poison-cli',
              messages: [],
              summaries: [],
            })
          }
          return okJson({
            agent_id: 'cli_agent',
            conversation_id: 'poison-cli',
            kind: 'cli',
            messages: [
              { role: 'user', content: 'hello' },
              {
                role: 'assistant',
                content: POISON,
                fatal_config_error: true,
              },
            ],
            summaries: [],
          })
        }
        return okJson({
          data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
        })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('shows a recovery card when hydrate ends on a fatal CLI config error', async () => {
    renderChat('/chat?blueprint=cli_agent&session=poison-cli')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('hello')).toBeInTheDocument()
    expect(screen.getByText(POISON)).toBeInTheDocument()
    const banner = await screen.findByTestId('cli-session-recovery')
    expect(banner).toHaveTextContent(CLI_SESSION_RECOVERY_MESSAGE)
    expect(screen.getByTestId('cli-session-recovery-fresh')).toBeInTheDocument()
    expect(screen.getByTestId('cli-session-recovery-retry')).toBeInTheDocument()
    expect(screen.getByTestId('cli-session-recovery-clear')).toBeInTheDocument()
  })

  it('Start Fresh Session opens a new conversation with the same agent', async () => {
    renderChat('/chat?blueprint=cli_agent&session=poison-cli')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await screen.findByTestId('cli-session-recovery')
    fireEvent.click(screen.getByTestId('cli-session-recovery-fresh'))
    await waitFor(() => {
      const loc = screen.getByTestId('chat-location').textContent || ''
      expect(loc).toContain('blueprint=cli_agent')
      expect(loc).toContain('session=')
      expect(loc).not.toContain('session=poison-cli')
    })
  })

  it('Retry re-sends the last user turn', async () => {
    renderChat('/chat?blueprint=cli_agent&session=poison-cli')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await screen.findByTestId('cli-session-recovery')
    fireEvent.click(screen.getByTestId('cli-session-recovery-retry'))
    await waitFor(() => {
      const sent = MockWebSocket.instances.some((ws) =>
        ws.send.mock.calls.some((args) => String(args[0]).includes('hello')),
      )
      expect(sent).toBe(true)
    })
  })

  it('Clear History posts the clear action for the poisoned thread', async () => {
    renderChat('/chat?blueprint=cli_agent&session=poison-cli')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await screen.findByTestId('cli-session-recovery')
    fireEvent.click(screen.getByTestId('cli-session-recovery-clear'))
    await waitFor(() => {
      const cleared = threadCalls().some((row) => {
        const body = typeof row.init?.body === 'string' ? row.init.body : ''
        return body.includes('"action":"clear"') && row.url.includes('agent=cli_agent')
      })
      expect(cleared).toBe(true)
    })
  })
})

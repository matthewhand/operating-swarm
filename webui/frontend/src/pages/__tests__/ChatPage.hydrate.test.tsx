import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
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

function renderSwitchableChat(initialEntry = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <nav>
            <Link to="/chat?blueprint=codey">Go Codey</Link>
            <Link to="/chat?blueprint=stewie">Go Stewie</Link>
          </nav>
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
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

function failThread(): Response {
  return {
    ok: false,
    status: 500,
    json: async () => ({ error: 'thread store unavailable' }),
  } as Response
}

function threadCalls(): string[] {
  return (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
    .map(([input]) => String(input))
    .filter((url) => url.includes('/chat/thread/'))
}

describe('ChatPage hydrate honesty (REQ-171A-4 / #604)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('keeps in-memory bubbles and toasts when REST 500 follows an agent switch', async () => {
    let failNextThread = false
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          if (failNextThread) return failThread()
          const agent = new URL(url, 'http://localhost').searchParams.get('agent')
          if (agent === 'codey') {
            return okJson({
              agent_id: 'codey',
              conversation_id: 'agt-codey',
              messages: [
                { role: 'user', content: 'prior question A' },
                { role: 'assistant', content: 'prior answer A' },
              ],
            })
          }
          if (agent === 'stewie') {
            return okJson({
              agent_id: 'stewie',
              conversation_id: 'agt-stewie',
              messages: [
                { role: 'user', content: 'prior question B' },
                { role: 'assistant', content: 'prior answer B' },
              ],
            })
          }
          return okJson({ agent_id: agent, messages: [], summaries: [] })
        }
        return okJson({
          data: [
            { id: 'codey', name: 'Codey', description: 'Code assistant' },
            { id: 'stewie', name: 'Stewie', description: 'Helpful agent' },
          ],
        })
      }),
    )

    renderSwitchableChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('prior question A')).toBeInTheDocument()
    expect(screen.getByText('prior answer A')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Go Stewie' }))
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })
    expect(await screen.findByText('prior question B')).toBeInTheDocument()

    failNextThread = true
    fireEvent.click(screen.getByRole('link', { name: 'Go Codey' }))
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    expect(await screen.findByText('Could not load chat')).toBeInTheDocument()
    expect(screen.getByText('The transcript could not be fetched. Existing messages were kept.')).toBeInTheDocument()
    expect(screen.getByText('prior question A')).toBeInTheDocument()
    expect(screen.getByText('prior answer A')).toBeInTheDocument()
    expect(screen.queryByTestId('chat-hydrate-error')).not.toBeInTheDocument()
    expect(screen.queryByText(/Message Codey/i)).not.toBeInTheDocument()
  })

  it('shows an explicit error state on first load when GET fails and the bucket is empty', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) return failThread()
        return okJson({
          data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
        })
      }),
    )

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const error = await screen.findByTestId('chat-hydrate-error')
    expect(error).toHaveAttribute('role', 'alert')
    expect(error).toHaveTextContent('Could not load this chat')
    expect(error).toHaveTextContent('thread store unavailable')
    expect(screen.queryByText(/Message Codey/i)).not.toBeInTheDocument()
    expect(await screen.findByText('Could not load chat')).toBeInTheDocument()
  })

  it('hydrates ?remote= from the thread endpoint and restores a seeded thread on refresh', async () => {
    const stub = () =>
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return okJson({
            agent_id: 'remote:omb',
            conversation_id: 'remote-omb',
            kind: 'remote',
            editable: false,
            messages: [
              { role: 'user', content: 'seeded remote user' },
              { role: 'assistant', content: 'seeded remote reply' },
            ],
          })
        }
        if (url.includes('/v1/remotes')) {
          return okJson({
            object: 'list',
            kinds: [{ id: 'omb', label: 'OpenMousBot' }],
            configured: [
              {
                id: 'omb',
                kind: 'omb',
                label: 'OpenMousBot',
                title: 'OpenMousBot',
                host_label: '',
                base_url: 'http://127.0.0.1:8802',
                source: 'config',
              },
            ],
          })
        }
        return okJson({ data: [] })
      })

    vi.stubGlobal('fetch', stub())
    const first = renderChat('/chat?remote=omb')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('seeded remote user')).toBeInTheDocument()
    expect(screen.getByText('seeded remote reply')).toBeInTheDocument()
    expect(screen.getByTestId('chat-status')).toHaveTextContent('Reconnected remote')
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-agent-kind',
      'remote',
    )
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-messages-editable',
      'false',
    )
    expect(threadCalls().some((url) => url.includes('agent=remote%3Aomb'))).toBe(true)
    first.unmount()

    MockWebSocket.instances = []
    vi.stubGlobal('fetch', stub())
    renderChat('/chat?remote=omb')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('seeded remote user')).toBeInTheDocument()
    expect(screen.getByText('seeded remote reply')).toBeInTheDocument()
    expect(threadCalls().some((url) => url.includes('/chat/thread/'))).toBe(true)
    expect(threadCalls().some((url) => url.includes('agent=remote%3Aomb'))).toBe(true)
  })

  it('calls the thread endpoint for a remote session instead of returning early', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return okJson({
            agent_id: 'remote:omb',
            conversation_id: 'remote-omb-sess-remote',
            kind: 'remote',
            editable: false,
            messages: [{ role: 'user', content: 'remote session turn' }],
          })
        }
        return okJson({ data: [] })
      }),
    )

    renderChat('/chat?remote=omb&session=sess-remote')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('remote session turn')).toBeInTheDocument()
    await waitFor(() => {
      expect(
        threadCalls().some(
          (url) =>
            url.includes('/chat/thread/') &&
            url.includes('agent=remote%3Aomb') &&
            url.includes('conversation_id=remote-omb-sess-remote'),
        ),
      ).toBe(true)
    })
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-messages-editable',
      'false',
    )
  })

  it('#1322 hydrates a textless voice note as an audio bubble after reload', async () => {
    const note =
      '![Voice note](/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio)'
    const stub = () =>
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return okJson({
            agent_id: 'codey',
            conversation_id: 'agt-codey',
            messages: [{ role: 'user', content: note }],
          })
        }
        return okJson({ data: [] })
      })

    vi.stubGlobal('fetch', stub())
    const first = renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const player = await screen.findByTestId('voice-note-player')
    expect(player.tagName).toBe('AUDIO')
    expect(player).toHaveAttribute('controls')
    expect(player).toHaveAttribute(
      'src',
      '/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio',
    )
    expect(screen.queryByText(/Attached/i)).not.toBeInTheDocument()
    first.unmount()

    MockWebSocket.instances = []
    vi.stubGlobal('fetch', stub())
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const again = await screen.findByTestId('voice-note-player')
    expect(again).toHaveAttribute(
      'src',
      '/v1/chat/attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/content?media=audio',
    )
  })
})

/**
 * #1709 — the main pane must FULLY switch when an add-chat lands on a new
 * `?session=` for the same seat. Nothing of the previous chat may survive on
 * screen: not its transcript rows, not its per-thread state.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useNavigate } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'

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

function AddChatButton() {
  const navigate = useNavigate()
  return (
    <button
      type="button"
      data-testid="add-chat"
      onClick={() => navigate('/chat?blueprint=codey&session=fresh-codey')}
    >
      add chat
    </button>
  )
}

function renderChat(initialEntry = '/chat?blueprint=codey&session=sess-old') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <AddChatButton />
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

interface ThreadStub {
  conversationId: string
  messages: { role: string; content: string }[]
}

function stubFetch(threads: ThreadStub[]) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/chat/thread/')) {
        const wanted = new URL(url, 'http://x').searchParams.get('conversation_id')
        const hit =
          threads.find((row) => row.conversationId === wanted) ??
          ({ conversationId: wanted ?? '', messages: [] } as ThreadStub)
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            conversation_id: hit.conversationId,
            session_title: hit.conversationId,
            messages: hit.messages,
            summaries: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    }),
  )
}

async function openSocket() {
  await act(async () => {
    MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
  })
}

describe('#1709 the main pane fully switches to the added chat', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubFetch([
      {
        conversationId: 'sess-old',
        messages: [
          { role: 'user', content: 'prior question about the old chat' },
          { role: 'assistant', content: 'prior answer about the old chat' },
        ],
      },
      { conversationId: 'fresh-codey', messages: [] },
    ])
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('drops the previous transcript and shows the composer for the new session', async () => {
    renderChat()
    await openSocket()

    expect(await screen.findByText('prior question about the old chat')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByTestId('add-chat'))
    })

    await waitFor(() =>
      expect(screen.queryByText('prior question about the old chat')).not.toBeInTheDocument(),
    )
    expect(screen.queryByText('prior answer about the old chat')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('names the new session on screen so the switch is visible, not silent', async () => {
    renderChat()
    await openSocket()
    await screen.findByText('prior question about the old chat')

    await act(async () => {
      fireEvent.click(screen.getByTestId('add-chat'))
    })

    // A brand new session has no rows, so the transcript alone cannot show
    // which chat is open — the restore notice names it.
    expect(await screen.findByText('Switched to session fresh-codey')).toBeInTheDocument()
  })
})

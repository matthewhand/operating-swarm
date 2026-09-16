import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }
}

const USAGE_FRAME = {
  type: 'context_usage',
  conversation_id: 'c1',
  agent_id: 'support',
  tokens: 12300,
  window: null,
  pct: null,
  estimate: true,
  breakdown: { messages: 8000, summaries: 2000, system: 1500, tools: 800 },
}

function renderChat(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[path]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage context-window usage (#215)', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows the composer badge from a WS context_usage frame',
    async () => {
      renderChat('/chat?blueprint=support')
      await act(async () => {
        MockWebSocket.instances[0]?.open()
      })
      expect(screen.queryByTestId('context-usage-badge')).toBeNull()

      await act(async () => {
        MockWebSocket.instances[0]?.onmessage?.(
          new MessageEvent('message', { data: JSON.stringify(USAGE_FRAME) }),
        )
      })

      const badge = screen.getByTestId('context-usage-badge')
      expect(badge).toHaveTextContent('~12.3k tokens, window unknown')
      expect(screen.getByTestId('chat-bottom-dock')).toContainElement(badge)
    },
  )

  it('renders used/max when the seat window is known', async () => {
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await act(async () => {
      MockWebSocket.instances[0]?.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({ ...USAGE_FRAME, tokens: 16000, window: 128000, pct: 13 }),
        }),
      )
    })
    expect(screen.getByTestId('context-usage-badge')).toHaveTextContent('~16k / 128k')
  })

  it('does not render the composer badge for CLI seats', async () => {
    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await act(async () => {
      MockWebSocket.instances[0]?.onmessage?.(
        new MessageEvent('message', { data: JSON.stringify(USAGE_FRAME) }),
      )
    })
    expect(screen.queryByTestId('context-usage-badge')).toBeNull()
  })
})

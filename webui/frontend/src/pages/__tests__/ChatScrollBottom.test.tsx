import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }
  send() {}
  close() {}
}

describe('REQ-202: Chat scrollbar to page bottom; composer inside pane but non-scrolling', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
        }),
      }),
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('scroll container extends full height and houses sticky bottom composer dock', () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    // Log container is the full-height scroll pane
    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    expect(scrollPane).toHaveClass('overflow-y-auto')
    expect(scrollPane).toHaveClass('os-chat-transcript')

    // Bottom dock is inside the scrollPane
    const bottomDock = screen.getByTestId('chat-bottom-dock')
    expect(scrollPane).toContainElement(bottomDock)
    expect(bottomDock).toHaveClass('sticky')
    expect(bottomDock).toHaveClass('bottom-0')

    // The composer input lives inside this sticky dock
    const composerInput = screen.getByRole('textbox', { name: 'Chat message' })
    expect(bottomDock).toContainElement(composerInput)

    // #773: the token meter lives in the composer area (canonical badge)
    const header = screen.getByRole('banner')
    expect(screen.queryByTestId('token-meter-button')).toBeNull()
    expect(header).toBeInTheDocument()

    // Messages container uses a live composer inset (not a stale fixed pb-* guess)
    const messagesContainer = screen.getByTestId('chat-messages-container')
    expect(scrollPane).toContainElement(messagesContainer)
    expect(messagesContainer).toHaveClass('os-chat-messages')
    expect(scrollPane).toHaveAttribute('data-composer-inset')
  })
})

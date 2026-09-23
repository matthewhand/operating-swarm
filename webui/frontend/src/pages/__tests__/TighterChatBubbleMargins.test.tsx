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
  onmessage: ((e: { data: string }) => void) | null = null
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

  emitMessage(data: Record<string, unknown>) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('REQ-192: Tighter chat bubble margins and transcript width', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ results: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders transcript container with os-chat-transcript and tightened padding classes', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const transcript = screen.getByRole('log', { name: 'Conversation' })
    expect(transcript).toBeInTheDocument()
    expect(transcript).toHaveClass('os-chat-transcript')
    expect(transcript).toHaveClass('px-2')
    expect(transcript).toHaveClass('sm:px-3')
    expect(transcript).toHaveClass('py-3')
    expect(transcript).not.toHaveClass('px-4')
  })

  it('renders messages and status lines within tightened transcript', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    const ws = MockWebSocket.instances[0]
    await act(async () => {
      ws?.open()
    })

    // Emit user echo and assistant message
    await act(async () => {
      ws?.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">Hello from user</div></div>',
        }),
      )
      ws?.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-abc123" class="assistant-message"></div></div>',
        }),
      )
      ws?.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-abc123" class="assistant-message" hx-swap-oob="true">Hello from assistant</div>',
        }),
      )
    })

    const transcript = screen.getByRole('log', { name: 'Conversation' })
    expect(transcript.querySelector('.chat-bubble')).toBeInTheDocument()
    expect(transcript.querySelector('.chat-start')).toBeInTheDocument()
    expect(transcript.querySelector('.chat-end')).toBeInTheDocument()
  })
})

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

describe('REQ-201: Token counter in top navbar beside agent/model picker', () => {
  beforeEach(() => {
    localStorage.clear()
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

  it('renders token counter in top navbar header and removes duplicate from composer footer', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const tokenButton = screen.getByTestId('token-meter-button')
    expect(tokenButton).toBeInTheDocument()

    // Token button is inside the top header (navbar)
    const header = screen.getByRole('banner')
    expect(header).toContainElement(tokenButton)

    // No token meter button exists inside the bottom dock footer
    const bottomDock = screen.getByTestId('chat-bottom-dock')
    expect(bottomDock.querySelector('[data-testid="token-meter-button"]')).toBeNull()
  })

  it('does not render token meter in navbar for CLI agents', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=cli_agent']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.queryByTestId('token-meter-button')).toBeNull()
  })

  it('does not render token meter in navbar for remote agents', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?remote=hermes']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.queryByTestId('token-meter-button')).toBeNull()
  })
})

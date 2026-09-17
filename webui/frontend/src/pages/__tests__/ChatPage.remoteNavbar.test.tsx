import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev?: Event) => void) | null = null
  onclose: ((ev?: Event) => void) | null = null
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

function remotesCatalog() {
  return {
    object: 'list',
    kinds: [{ id: 'anythingllm', label: 'AnythingLLM' }],
    configured: [
      {
        id: 'anythingllm',
        kind: 'anythingllm',
        title: 'AnythingLLM',
        source: 'config',
        base_url: 'http://127.0.0.1:3001',
      },
    ],
  }
}

function stubFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/operate/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          remote: 'anythingllm',
          op: 'list',
          ok: true,
          data: {
            agents: [{ id: 'ws-docs', name: 'Docs' }],
            sessions: [{ id: 'ws-docs:t1', title: 'thread one' }],
          },
        }),
      } as Response
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return {
        ok: true,
        status: 200,
        json: async () => remotesCatalog(),
      } as Response
    }
    return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
  })
}

describe('ChatPage remote navbar agents + sessions', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    window.localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('fetch', stubFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('shows remote-end agents dropdown and a sessions button', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?remote=anythingllm']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const fetchMock = vi.mocked(fetch)
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) =>
          String(call[0]).includes('/v1/remotes/anythingllm/operate/'),
        ),
      ).toBe(true)
    })
    expect(screen.getByTestId('navbar-routing-picker')).toHaveAttribute('data-seat-kind', 'remote')
    const agentPill = await screen.findByTestId('routing-pill-model')
    expect(agentPill).toHaveAttribute('aria-label', 'Remote agent')
    fireEvent.click(agentPill)
    expect(await screen.findByRole('menuitem', { name: 'Docs' })).toBeInTheDocument()
    const sessionsBtn = screen.getByTestId('os-remote-session-switcher')
    expect(sessionsBtn).toHaveAttribute('aria-label', 'Select AnythingLLM session')
    fireEvent.click(sessionsBtn)
    await waitFor(() => {
      expect(screen.getByText('thread one')).toBeInTheDocument()
    })
  })
})

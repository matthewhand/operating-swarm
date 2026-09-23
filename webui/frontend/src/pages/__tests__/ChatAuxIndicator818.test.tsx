/**
 * #818 — the navbar indicator surfaces background LLM inference live.
 *
 * WS frames (`aux_task_started` / `aux_task_update`) drive the indicator;
 * the kill switch sends `cancel_auxiliary` back over the same socket.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  sentFrames: string[] = []

  send = vi.fn((data: string) => {
    this.sentFrames.push(data)
  })
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

  deliver(payload: unknown) {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }))
  }
}

describe('#818 navbar auxiliary-inference indicator', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
  })

  afterEach(() => {
    vi.restoreAllMocks()
    window.localStorage.clear()
  })

  function renderChat() {
    return render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
  }

  it('renders idle → active → decay flow from WS frames', async () => {
    renderChat()
    const ws = MockWebSocket.instances[0]
    await act(async () => ws.open())

    // Idle: nothing shows.
    expect(screen.queryByTestId('aux-activity')).not.toBeInTheDocument()

    await act(async () => {
      ws.deliver({ type: 'aux_task_started', task_id: 'aux-1', label: 'Summarizing context', model: 'gpt-4o-mini' })
    })
    expect(screen.getByTestId('aux-activity')).toBeInTheDocument()
    expect(screen.getByLabelText('1 background tasks active')).toBeInTheDocument()

    // Finish: the row lingers in the decay window.
    await act(async () => {
      ws.deliver({ type: 'aux_task_update', task_id: 'aux-1', state: 'done', duration_s: 1.4 })
    })
    expect(screen.getByLabelText('Background task activity')).toBeInTheDocument()

    // Open the audit list.
    fireEvent.click(screen.getByTestId('aux-activity-toggle'))
    expect(screen.getByTestId('aux-activity-dialog')).toBeInTheDocument()
    expect(screen.getByTestId('aux-activity-row')).toHaveTextContent('✓ Summarizing context (1.4s)')
  })

  it('the kill switch sends cancel_auxiliary over the socket', async () => {
    renderChat()
    const ws = MockWebSocket.instances[0]
    await act(async () => ws.open())

    await act(async () => {
      ws.deliver({ type: 'aux_task_started', task_id: 'aux-7', label: 'Runaway summarizer' })
    })
    fireEvent.click(screen.getByTestId('aux-activity-toggle'))
    fireEvent.click(screen.getByTestId('aux-cancel-aux-7'))

    await waitFor(() => {
      expect(ws.sentFrames.some((f) => f.includes('"cancel_auxiliary"') && f.includes('aux-7'))).toBe(
        true,
      )
    })
  })
})

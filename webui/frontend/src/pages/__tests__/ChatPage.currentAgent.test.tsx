import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'
import {
  CURRENT_AGENT_STORAGE_KEY,
  loadCurrentAgent,
  subscribeCurrentAgent,
  type CurrentAgent,
} from '../../lib/currentAgent'

/**
 * REQ-912 (#511) / REQ-914 (#513) / REQ-917 (#516): the rail and the routines
 * calendar are siblings of ChatPage, not descendants, so the selected seat has
 * to be published. These tests pin the publisher side — that ChatPage writes the
 * seat and its kind, with the scope prefix preserved.
 */

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null

  send = vi.fn()
  close = vi.fn(() => {
    this.readyState = 3
  })

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }
}

function renderChat(entry: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  localStorage.clear()
  MockWebSocket.instances = []
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
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
  localStorage.removeItem(CURRENT_AGENT_STORAGE_KEY)
  vi.restoreAllMocks()
})

describe('ChatPage publishes the current agent seat', () => {
  it('publishes an API blueprint seat with kind "api"', async () => {
    renderChat('/chat?blueprint=support')
    await waitFor(() => {
      expect(loadCurrentAgent()).toEqual({ id: 'support', kind: 'api' })
    })
  })

  it('publishes a remote seat as kind "remote" and keeps the scope prefix', async () => {
    renderChat('/chat?remote=omb')
    await waitFor(() => {
      expect(loadCurrentAgent()).toEqual({ id: 'remote:omb', kind: 'remote' })
    })
  })

  it('publishes a team thread with its team: prefix', async () => {
    renderChat('/chat?team=alpha')
    await waitFor(() => {
      expect(loadCurrentAgent()).toEqual({ id: 'team:alpha', kind: 'api' })
    })
  })

  it('emits the change to in-page subscribers, not just to storage', async () => {
    const seen: Array<CurrentAgent | null> = []
    const off = subscribeCurrentAgent((agent) => {
      if (agent) seen.push(agent)
    })
    renderChat('/chat?blueprint=support')
    await waitFor(() => {
      expect(seen.some((agent) => agent?.id === 'support' && agent.kind === 'api')).toBe(true)
    })
    act(() => off())
  })
})

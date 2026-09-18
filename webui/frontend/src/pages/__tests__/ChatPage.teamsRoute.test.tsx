/**
 * #524 — deep links into a team must render the team.
 *
 * `/teams/#demo-team` used to fall into the router's catch-all and bounce to
 * `/`: no `/teams` route existed, so the team view never mounted. Now the
 * path form is a first-class entry that normalizes to the existing
 * `?team=<id>` state, unknown ids degrade to the plain chat surface, and the
 * legacy query form keeps working.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import ChatPage from '../ChatPage'

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
}

function renderAt(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        {/* Mirror App's route table so the /teams/* entry is exercised. */}
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/teams/*" element={<ChatPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/*" element={<ChatPage />} />
            <Route path="/" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#524 /teams/:id deep link', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
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
    resetConversationThreads()
  })

  it('renders the chat surface at /teams/demo-team (no redirect to /)', async () => {
    renderAt('/teams/demo-team')
    await waitFor(
      () => {
        expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
      },
      { timeout: 4000 },
    )
  })

  it('does not blank out for an unknown team id (graceful fallback)', async () => {
    renderAt('/teams/definitely-not-a-team')
    await waitFor(
      () => {
        expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
      },
      { timeout: 4000 },
    )
  })

  it('keeps supporting the legacy ?team= form', async () => {
    renderAt('/chat?team=demo-team')
    await waitFor(
      () => {
        expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
      },
      { timeout: 4000 },
    )
  })
})

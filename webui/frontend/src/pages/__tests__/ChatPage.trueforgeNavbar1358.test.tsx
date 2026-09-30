/**
 * #1358 — the TrueForge navbar Agent + Session pickers are sourced from the
 * dedicated TrueForge endpoint (`/v1/remotes/trueforge/trueforge/`), never the
 * generic operate path and never the default inference profile. Selecting a
 * session loads that context for follow-ups (`?remote=trueforge&session=<id>`).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation, Route, Routes } from 'react-router-dom'
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

function LocationProbe() {
  const location = useLocation()
  return <span data-testid="location-search">{location.search}</span>
}

function remotesCatalog() {
  return {
    object: 'list',
    kinds: [{ id: 'trueforge', label: 'TrueForge' }],
    configured: [
      {
        id: 'trueforge',
        kind: 'trueforge',
        title: 'TrueForge',
        source: 'config',
        base_url: 'http://127.0.0.1:8791',
        capabilities: { list: true, send: true, sessions: true },
      },
    ],
  }
}

function trueforgeCatalog() {
  return {
    object: 'trueforge.catalog',
    remote: 'trueforge',
    kind: 'trueforge',
    ok: true,
    detail: 'TrueForge listed 2 agent(s)',
    http_status: 200,
    rows_are: 'agents',
    resume_key: 'session_id',
    agents: [
      { id: 'agent-1', label: 'orchestrator', name: 'orchestrator' },
      { id: 'agent-2', label: 'coder', name: 'coder' },
    ],
    sessions: [
      {
        id: 'sess-9',
        title: 'refactor the parser',
        snippet: 'orchestrator',
        agent: 'orchestrator',
        updated_at: '2026-09-22T08:30:00Z',
      },
      { id: 'sess-4', title: 'second thread', agent: 'coder' },
    ],
  }
}

function stubFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/trueforge/')) {
      return { ok: true, status: 200, json: async () => trueforgeCatalog() } as Response
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return { ok: true, status: 200, json: async () => remotesCatalog() } as Response
    }
    return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
  })
}

describe('#1358 ChatPage TrueForge navbar pickers', () => {
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

  it('sources agents + sessions from TrueForge and loads a picked session', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?remote=trueforge']}>
            <LocationProbe />
            <Routes>
              <Route path="/chat" element={<ChatPage />} />
            </Routes>
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
          String(call[0]).includes('/v1/remotes/trueforge/trueforge/'),
        ),
      ).toBe(true)
    })
    // The generic operate path is never used for TrueForge.
    expect(
      fetchMock.mock.calls.some((call) =>
        String(call[0]).includes('/v1/remotes/trueforge/operate/'),
      ),
    ).toBe(false)

    // Agent picker: only the TrueForge agents, with a live search filter.
    fireEvent.click(await screen.findByTestId('os-navbar-agent-picker'))
    await screen.findByTestId('os-navbar-agent-option-agent-1')
    expect(screen.getAllByRole('menuitem')).toHaveLength(2)
    fireEvent.change(screen.getByTestId('os-navbar-agent-picker-search'), {
      target: { value: 'code' },
    })
    expect(screen.getByTestId('os-navbar-agent-option-agent-2')).toBeInTheDocument()
    expect(screen.queryByTestId('os-navbar-agent-option-agent-1')).toBeNull()
    fireEvent.keyDown(document, { key: 'Escape' })

    // Session picker: catalog sessions, selecting one loads its context.
    const sessionsBtn = await screen.findByTestId('os-remote-session-switcher')
    fireEvent.click(sessionsBtn)
    const row = await screen.findByText('second thread')
    row.closest('[data-session-id]')?.dispatchEvent(
      new MouseEvent('click', { bubbles: true }),
    )
    await waitFor(() => {
      expect(screen.getByTestId('location-search').textContent).toContain('session=sess-4')
    })
  })
})

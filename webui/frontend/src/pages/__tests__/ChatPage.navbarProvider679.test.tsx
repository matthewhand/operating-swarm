/**
 * #679 — the top navbar carries NO provider/model selector for any seat kind.
 *
 * The composer's routing picker (renderRoutingPicker → NavbarRoutingPicker in
 * the composer control row) is the single provider/model surface. The navbar
 * header keeps only session switchers, tools, and identity — provider/model
 * chrome there is redundant and eats horizontal space.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'

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

function SearchProbe() {
  const [params] = useSearchParams()
  return <div data-testid="search-probe">{params.toString()}</div>
}

function renderChat(initialEntry: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <SearchProbe />
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function stubSeatFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              {
                id: 'demo-team',
                object: 'team_roster',
                name: 'Demo Team',
                members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
              },
            ],
          }),
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'x',
            conversation_id: 'x',
            messages: [],
          }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
    }),
  )
}

/**
 * The header block (from `os-chat-header` to its close) must not mount a
 * routing picker or any provider/model control. Source-level pin: the
 * composer picker is invoked from the composer control row only.
 */
function headerSource(): string {
  // #856 slice J: the os-chat-header JSX moved verbatim into the ChatHeader
  // module — the pin reads its real home.
  const src = readFileSync(
    join(__dirname, '..', '..', 'features', 'chat', 'ChatHeader.tsx'),
    'utf8',
  )
  const start = src.indexOf('<header className="os-chat-header')
  expect(start).toBeGreaterThan(0)
  const end = src.indexOf('</header>', start)
  expect(end).toBeGreaterThan(start)
  return src.slice(start, end)
}

describe('#679 the navbar carries no provider/model selector', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    window.localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubSeatFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('the header source mounts no NavbarRoutingPicker / renderRoutingPicker', () => {
    const header = headerSource()
    expect(header).not.toMatch(/NavbarRoutingPicker/)
    expect(header).not.toMatch(/renderRoutingPicker\(\)/)
    expect(header).not.toMatch(/routing-pill/)
  })

  it.each([
    ['/chat?blueprint=codey', 'api'],
    ['/chat?team=demo-team', 'team'],
    ['/chat?remote=anythingllm', 'remote'],
  ])('seat %s renders no routing pill inside the navbar', async (entry) => {
    renderChat(entry)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toBeInTheDocument()
    })
    // The pill exists ONLY in the composer control row, never the header.
    const header = document.querySelector('.os-chat-header')
    expect(header).toBeTruthy()
    expect(header!.querySelector('[data-testid="routing-pill-agent"]')).toBeNull()
    expect(header!.querySelector('select[aria-label="Team members"]')).toBeNull()
  })

  // The positive control — the composer owns the provider/model picker — is
  // already pinned end-to-end by ChatPage.remoteNavbar.test.tsx,
  // ChatPage.herdrComposer789.test.tsx, and ChatPage.teamComposer755.test.tsx,
  // all of which drive routing picks through the composer's palette.
})

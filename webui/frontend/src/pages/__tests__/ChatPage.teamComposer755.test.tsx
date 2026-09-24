/**
 * #755 — team member routing lives in the composer's routing picker, not a
 * legacy navbar `<select>`.
 *
 * The picker mounts with seatKind=team; the palette lists All members, the
 * roster (name + kind/role), and Manage Team as the footer action. Picks
 * write the same URL contract the select wrote (#288: members=all for the
 * All members choice, session=<id> for a member) and the send target follows.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'

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

const DEMO_ROSTER = {
  object: 'list',
  data: [
    {
      id: 'demo-team',
      object: 'team_roster',
      name: 'Demo Team',
      description: 'Example multi-agent roster',
      members: [
        { id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' },
        { id: 'stewie', name: 'Stewie', kind: 'agent', role: 'ops' },
      ],
    },
  ],
}

function SearchProbe() {
  const [params] = useSearchParams()
  return <div data-testid="search-probe">{params.toString()}</div>
}

function renderTeamChat(initialEntry = '/chat?team=demo-team') {
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

function stubTeamFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return {
          ok: true,
          status: 200,
          json: async () => DEMO_ROSTER,
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'team-demo-team',
            conversation_id: 'team-demo-team',
            messages: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    }),
  )
}

async function openSocket() {
  await act(async () => {
    MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
  })
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]!
}

async function openPalette() {
  fireEvent.click(await screen.findByTestId('routing-pill-agent'))
  return screen.findByTestId('os-model-search-palette')
}

describe('#755 team routing in the composer picker', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    window.localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubTeamFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('mounts the team picker in the composer and retires the navbar select', async () => {
    renderTeamChat()
    await openSocket()

    const picker = await screen.findByTestId('navbar-routing-picker')
    expect(picker).toHaveAttribute('data-seat-kind', 'team')
    // The legacy navbar dropdown is gone.
    expect(screen.queryByRole('combobox', { name: 'Team members' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Demo Team' })).toBeInTheDocument()
  })

  it('lists All members, the roster with kind/role, and Manage Team as the footer action', async () => {
    renderTeamChat()
    await openSocket()
    await openPalette()

    expect(await screen.findByTestId('os-model-row-all')).toBeInTheDocument()
    expect(screen.getByTestId('os-model-row-codey')).toHaveTextContent('Codey (agent/coder)')
    expect(screen.getByTestId('os-model-row-stewie')).toHaveTextContent('Stewie (agent/ops)')
    // Manage Team is the palette's footer action, not a roster row.
    expect(screen.getByTestId('os-model-manage-api')).toHaveTextContent('Manage teams')
  })

  it('picks a member and writes session=<id>; All members writes members=all', async () => {
    renderTeamChat()
    await openSocket()
    await openPalette()

    fireEvent.click(await screen.findByTestId('os-model-row-codey'))
    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('session=codey')
    })
    expect(screen.getByTestId('search-probe').textContent).not.toContain('members=')

    await openPalette()
    fireEvent.click(await screen.findByTestId('os-model-row-all'))
    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('members=all')
    })
    expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
  })

  it('sends to the picked member as target', async () => {
    renderTeamChat()
    const ws = await openSocket()
    await openPalette()

    fireEvent.click(await screen.findByTestId('os-model-row-stewie'))
    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('session=stewie')
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'ping stewie' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    const raw = String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')))
    const { kind: _k, conversationId: _c, ...inner } = JSON.parse(raw) as Record<string, unknown>
    expect(inner).toEqual({
      message: 'ping stewie',
      params: { team: 'demo-team', target: 'stewie', enabled_tools: [] },
    })
  })

  it('Manage Team navigates to /teams/#team_id and never sends', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    renderTeamChat()
    const ws = await openSocket()
    await openPalette()

    fireEvent.click(screen.getByTestId('os-model-manage-api'))
    expect(assign).toHaveBeenCalledWith('/teams/#demo-team')
    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
  })
})

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

function stubTeamFetch(options?: {
  threadMessages?: { role: string; content: string }[]
  onThreadGet?: () => void
  roster?: unknown
}) {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return {
          ok: true,
          status: 200,
          json: async () => options?.roster ?? DEMO_ROSTER,
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        if (init?.method !== 'POST') options?.onThreadGet?.()
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'team-demo-team',
            conversation_id: 'team-demo-team',
            messages: options?.threadMessages ?? [],
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

function lastUserFrame(ws: MockWebSocket) {
  const frames = ws.send.mock.calls
    .map((call) => JSON.parse(String(call[0])))
    .filter((frame) => frame.kind === 'chat.send' && frame.message && frame.type !== 'status')
    .map(({ kind: _k, conversationId: _c, ...inner }) => inner)
  return frames[frames.length - 1]
}

describe('ChatPage team member ?session= (REQ-171A-1 / #601)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubTeamFetch()
  })

  afterEach(() => {
    clearAllQueuedSends()
    resetConversationThreads()
    vi.unstubAllGlobals()
  })

  it('writes ?team=&session= for a member and restores picker + WS target after remount', async () => {
    const first = renderTeamChat('/chat?team=demo-team')
    await openSocket()

    // #755: the member pick now rides the composer routing picker.
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-stewie'))

    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('team=demo-team')
      expect(screen.getByTestId('search-probe')).toHaveTextContent('session=stewie')
    })
    expect(screen.getByTestId('navbar-routing-picker')).toHaveAttribute('data-seat-kind', 'team')

    first.unmount()
    renderTeamChat('/chat?team=demo-team&session=stewie')
    const ws = await openSocket()

    expect(screen.getByTestId('search-probe')).toHaveTextContent('session=stewie')

    fireEvent.change(await screen.findByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'after reload' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    await waitFor(() => {
      expect(lastUserFrame(ws)).toEqual({
        message: 'after reload',
        params: { team: 'demo-team', target: 'stewie', enabled_tools: [] },
      })
    })
  })

  it('clears session for All members and sends target all after remount', async () => {
    const first = renderTeamChat('/chat?team=demo-team&session=codey')
    await openSocket()

    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-all'))

    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('team=demo-team')
      expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
    })

    first.unmount()
    renderTeamChat('/chat?team=demo-team')
    const ws = await openSocket()

    // #169: a fresh team chat re-defaults to the seat (first member); the
    // explicit "All members" pick is what sends to everyone.
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-all'))
    expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
    fireEvent.change(await screen.findByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'everyone' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    await waitFor(() => {
      expect(lastUserFrame(ws)).toEqual({
        message: 'everyone',
        params: { team: 'demo-team', target: 'all', enabled_tools: [] },
      })
    })
  })

  it('does not write a session id or status line when Manage Team is chosen', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    renderTeamChat('/chat?team=demo-team')
    await openSocket()

    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-manage-api'))

    expect(assign).toHaveBeenCalledWith('/teams/#demo-team')
    expect(screen.getByTestId('search-probe')).toHaveTextContent('team=demo-team')
    expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
    expect(screen.queryByTestId('chat-status')).not.toBeInTheDocument()
    expect(
      MockWebSocket.instances[0]!.send.mock.calls.some((c) => String(c[0]).includes('"kind":"chat.send"')),
    ).toBe(false)
  })

  it('does not refetch the team thread when only ?session= changes', async () => {
    let threadGets = 0
    stubTeamFetch({
      threadMessages: [{ role: 'assistant', content: 'from disk' }],
      onThreadGet: () => {
        threadGets += 1
      },
    })

    renderTeamChat('/chat?team=demo-team')
    await openSocket()
    expect(await screen.findByText('from disk')).toBeInTheDocument()
    const getsAfterHydrate = threadGets
    expect(getsAfterHydrate).toBeGreaterThan(0)

    // #169: the default seat is the first member; an explicit "All members"
    // clears the session without refetching, then picking Codey writes
    // ?session=codey — still no thread refetch.
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-all'))
    await waitFor(() => {
      expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
    })
    expect(threadGets).toBe(getsAfterHydrate)

    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-codey'))

    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('session=codey')
    })
    expect(screen.getByText('from disk')).toBeInTheDocument()
    expect(screen.getByText('Team target: All members → Codey (agent/coder)')).toBeInTheDocument()
    expect(threadGets).toBe(getsAfterHydrate)
  })

  it('defaults the member picker to the Chief of Staff, else the first member (#169)', async () => {
    stubTeamFetch({
      roster: {
        object: 'list',
        data: [
          {
            id: 'demo-team',
            object: 'team_roster',
            name: 'Demo Team',
            members: [
              { id: 'zed', name: 'Zed', kind: 'agent', role: 'ops' },
              { id: 'cosmo', name: 'Cosmo', kind: 'agent', role: 'chief_of_staff' },
              { id: 'arc', name: 'Arc', kind: 'agent', role: 'coder' },
            ],
          },
        ],
      },
    })
    renderTeamChat('/chat?team=demo-team')
    await openSocket()
    // The seat default resolves before any pick; no ?session= is written.
    await screen.findByTestId('navbar-routing-picker')
    expect(screen.getByTestId('search-probe').textContent).not.toContain('session=')
    expect(screen.getByTestId('search-probe')).toHaveTextContent('team=demo-team')
  })
})

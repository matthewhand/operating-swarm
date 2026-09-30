/**
 * #1445 — switching away from AnythingLLM or a team must refresh the chat
 * header. ChatPage stays mounted across same-route search-param changes, so
 * leftover `agentKind` / `selectedRemoteId` used to keep AnythingLLM chrome
 * (session switcher + identity) on the team or API seat.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useNavigate } from 'react-router-dom'
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

const DEMO_ROSTER = {
  object: 'list',
  data: [
    {
      id: 'demo-team',
      object: 'team_roster',
      name: 'Demo Team',
      members: [
        { id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' },
        { id: 'stewie', name: 'Stewie', kind: 'agent', role: 'ops' },
      ],
    },
  ],
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
        capabilities: { list: true, send: true, sessions: true },
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
            agents: [
              { id: 'ws-docs', name: 'Docs' },
              { id: 'ws-ops', name: 'Ops' },
            ],
            sessions: [{ id: 'ws-docs:t1', title: 'thread one' }],
          },
        }),
      } as Response
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return { ok: true, status: 200, json: async () => remotesCatalog() } as Response
    }
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return { ok: true, status: 200, json: async () => DEMO_ROSTER } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
      }),
    } as Response
  })
}

function RouteButtons() {
  const navigate = useNavigate()
  return (
    <div>
      <button type="button" data-testid="go-anythingllm" onClick={() => navigate('/chat?remote=anythingllm')}>
        go anythingllm
      </button>
      <button type="button" data-testid="go-team" onClick={() => navigate('/chat?team=demo-team')}>
        go team
      </button>
      <button type="button" data-testid="go-codey" onClick={() => navigate('/chat?blueprint=codey')}>
        go codey
      </button>
    </div>
  )
}

function renderChat(initialEntry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <RouteButtons />
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1445 stale AnythingLLM / team header', () => {
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

  it('AnythingLLM → team drops the remote identity and session switcher', async () => {
    renderChat('/chat?remote=anythingllm')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const remoteHeader = await screen.findByTestId('selected-agent-header')
    expect(remoteHeader).toHaveAttribute('data-seat', 'remote:anythingllm')
    expect(remoteHeader).toHaveTextContent('AnythingLLM')
    expect(await screen.findByTestId('os-remote-session-switcher')).toHaveAttribute(
      'aria-label',
      'Select AnythingLLM session',
    )

    fireEvent.click(screen.getByTestId('go-team'))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
        'data-seat',
        'team:demo-team',
      )
    })
    const teamHeader = screen.getByTestId('selected-agent-header')
    expect(teamHeader).toHaveTextContent('Demo Team')
    expect(teamHeader).not.toHaveTextContent('AnythingLLM')
    expect(screen.queryByTestId('os-remote-session-switcher')).not.toBeInTheDocument()
    expect(screen.getByTestId('header-team-avatar')).toBeInTheDocument()
    expect(screen.queryByTestId('header-avatar-generations')).not.toBeInTheDocument()
  })

  it('team → AnythingLLM replaces the team face with the remote identity', async () => {
    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByTestId('selected-agent-header')).toHaveAttribute(
      'data-seat',
      'team:demo-team',
    )
    expect(screen.getByTestId('header-team-avatar')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('go-anythingllm'))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
        'data-seat',
        'remote:anythingllm',
      )
    })
    const remoteHeader = screen.getByTestId('selected-agent-header')
    expect(remoteHeader).toHaveTextContent('AnythingLLM')
    expect(remoteHeader).not.toHaveTextContent('Demo Team')
    expect(screen.queryByTestId('header-team-avatar')).not.toBeInTheDocument()
    expect(await screen.findByTestId('os-remote-session-switcher')).toBeInTheDocument()
  })

  it('AnythingLLM → API agent drops remotes chrome and shows the agent name', async () => {
    renderChat('/chat?remote=anythingllm')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByTestId('os-remote-session-switcher')).toBeInTheDocument()

    fireEvent.click(screen.getByTestId('go-codey'))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute('data-seat', 'api:codey')
    })
    const apiHeader = screen.getByTestId('selected-agent-header')
    expect(apiHeader).toHaveTextContent('Codey')
    expect(apiHeader).not.toHaveTextContent('AnythingLLM')
    expect(screen.queryByTestId('os-remote-session-switcher')).not.toBeInTheDocument()
    expect(screen.queryByTestId('header-team-avatar')).not.toBeInTheDocument()
  })
})

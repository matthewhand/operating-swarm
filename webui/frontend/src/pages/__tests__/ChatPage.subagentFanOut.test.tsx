import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { render, screen, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearDynamicSubagents, loadDynamicSubagents } from '../../lib/dynamicSubagents'

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.onclose?.()
  }

  open() {
    this.onopen?.()
  }
}

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/chat/thread/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'codey',
          conversation_id: 'conv-test',
          messages: [],
        }),
      } as Response
    }
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    }
    if (url.includes('/v1/remotes')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', configured: [], data: [] }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ data: [] }),
    } as Response
  })
}

function renderChat(initialEntry = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage Dynamic Subagent Fan-Out UI/UX', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    window.localStorage.clear()
    clearDynamicSubagents()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    clearDynamicSubagents()
    resetConversationThreads()
  })

  it('renders inline subagent fan-out block when subagent_fan_out ws frame arrives', async () => {
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeDefined()

    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'subagent_fan_out',
            title: '3 Subagents Fanned Out',
            subagents: [
              {
                id: 'subagent-spec',
                name: 'Spec Specialist',
                role: 'advisor',
                status: 'completed',
                summary: 'Outlined system specifications.',
              },
              {
                id: 'subagent-builder',
                name: 'Code Builder',
                role: 'engineer',
                status: 'running',
                summary: 'Writing implementation components.',
              },
            ],
            communications: [
              {
                id: 'comm-spec-builder',
                from: 'Spec Specialist',
                to: 'Code Builder',
                label: 'Spec → Builder',
                messages: [
                  {
                    id: 'm1',
                    from: 'Spec Specialist',
                    to: 'Code Builder',
                    content: 'Here are the design tokens and API endpoints.',
                  },
                ],
              },
            ],
          }),
        }),
      )
    })

    // SubagentFanOutBlock is rendered inline
    expect(await screen.findByTestId('subagent-fan-out-block')).toBeInTheDocument()
    expect(screen.getByText('3 Subagents Fanned Out')).toBeInTheDocument()
    expect(screen.getByText('Spec Specialist')).toBeInTheDocument()
    expect(screen.getByText('Code Builder')).toBeInTheDocument()
    expect(screen.getByText('Outlined system specifications.')).toBeInTheDocument()

    // Subagents automatically registered in dynamic subagents storage
    const stored = loadDynamicSubagents()
    expect(stored.map((s) => s.id)).toContain('subagent-spec')
    expect(stored.map((s) => s.id)).toContain('subagent-builder')

    // Click comms pill to reveal transcript
    const pill = screen.getByTestId('inter-agent-comm-pill')
    expect(pill).toHaveTextContent('Spec → Builder')
    fireEvent.click(pill)

    expect(await screen.findByTestId('inter-agent-transcript')).toBeInTheDocument()
    expect(
      screen.getByText('Here are the design tokens and API endpoints.'),
    ).toBeInTheDocument()
  })

  it('renders inline subagent fan-out block when teammate_task with subagents arrives', async () => {
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const ws = MockWebSocket.instances[0]
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'teammate_task',
            title: 'Fanned Out Teammates',
            subagents: [
              {
                id: 'remote-worker-1',
                name: 'Remote Worker 1',
                status: 'completed',
                summary: 'Completed data migration step',
              },
            ],
          }),
        }),
      )
    })

    expect(await screen.findByTestId('subagent-fan-out-block')).toBeInTheDocument()
    expect(screen.getByText('Remote Worker 1')).toBeInTheDocument()
    expect(screen.getByText('Completed data migration step')).toBeInTheDocument()
  })
})

/**
 * #1352 — ChatPage wires the selected agent's provider (as configured for the
 * seat / Edit agent) onto the navbar agent options, so the picker lists only
 * that provider's agents. The default inference profile is never the source.
 *
 * The seat is an API agent (`codey`); the palette also carries an `opencode`
 * CLI seat, a `codex` CLI seat, and a `support` API agent. Only the selected
 * agent's provider may appear.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'
import { saveInferenceList } from '../../lib/agentEdits'

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

function blueprint(id: string, name: string) {
  return {
    id,
    object: 'blueprint',
    name,
    description: '',
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  }
}

const BLUEPRINTS = {
  object: 'list',
  data: [blueprint('codey', 'Codey'), blueprint('support', 'Support')],
}

const CLI_AGENTS = {
  clis: ['opencode', 'codex'],
  known: ['opencode', 'codex'],
  installed: ['opencode', 'codex'],
  configured: ['opencode', 'codex'],
  discovered: ['opencode', 'codex'],
  default_cli: 'opencode',
  list_models: {},
  native_consensus: {},
  catalog: {},
  remote_boxes: [],
  rail: [
    { id: 'opencode-seat', object: 'cli.agent', name: 'Opencode seat', cli: 'opencode', kind: 'cli' },
    { id: 'codex-seat', object: 'cli.agent', name: 'Codex seat', cli: 'codex', kind: 'cli' },
  ],
}

function stubSeatFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/cli-agents/') && url.includes('/models/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ cli: 'opencode', models: ['opencode-go/x'] }),
        } as Response
      }
      if (url.includes('/v1/cli-agents/')) {
        return { ok: true, status: 200, json: async () => CLI_AGENTS } as Response
      }
      if (url.includes('/v1/blueprints/custom/')) {
        return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
      }
      if (url.includes('/v1/blueprints/')) {
        return { ok: true, status: 200, json: async () => BLUEPRINTS } as Response
      }
      if (url.includes('/v1/llm-profiles/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'llm_profiles',
            profiles: [],
            default_llm_profile: 'litellm/orchestration',
            default_is_auto: false,
            override_per_task: false,
            task_llm_profiles: {},
            routes: {},
            warnings: [],
            task_classes: [],
          }),
        } as Response
      }
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ agent_id: 'codey', conversation_id: 'x', messages: [] }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({ object: 'list', data: [] }) } as Response
    }),
  )
}

function renderChat(initialEntry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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

async function waitForHeader() {
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
  await waitFor(() => {
    expect(screen.getByTestId('selected-agent-header')).toBeInTheDocument()
  })
  await waitFor(() => {
    expect(screen.getByTestId('os-navbar-agent-picker')).not.toBeDisabled()
  })
}

describe('#1352 ChatPage navbar agent picker provider scoping', () => {
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

  it('lists only agents from the selected agent’s provider (API)', async () => {
    renderChat('/chat?blueprint=codey')
    await waitForHeader()

    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    await waitFor(() => {
      expect(screen.getByTestId('os-navbar-agent-option-support')).toBeInTheDocument()
    })
    // Same provider (API) → shown; the selected agent is marked.
    expect(screen.getByTestId('os-navbar-agent-option-codey')).toHaveAttribute(
      'aria-current',
      'true',
    )
    // Foreign providers (CLI) are never offered on an API seat.
    expect(screen.queryByTestId('os-navbar-agent-option-opencode-seat')).toBeNull()
    expect(screen.queryByTestId('os-navbar-agent-option-codex-seat')).toBeNull()
  })

  it('changing the agent’s provider in Edit agent changes what the picker shows', async () => {
    // Edit agent: codey now routes through the `opencode` CLI provider.
    saveInferenceList('codey', [{ id: 'opencode', kind: 'cli', label: 'opencode' }])
    renderChat('/chat?blueprint=codey')
    await waitForHeader()

    fireEvent.click(screen.getByTestId('os-navbar-agent-picker'))
    await waitFor(() => {
      expect(screen.getByTestId('os-navbar-agent-option-opencode-seat')).toBeInTheDocument()
    })
    // The selected agent’s new provider scope includes its CLI sibling…
    expect(screen.getByTestId('os-navbar-agent-option-codey')).toBeInTheDocument()
    // …and drops the old API siblings + the other CLI provider.
    expect(screen.queryByTestId('os-navbar-agent-option-support')).toBeNull()
    expect(screen.queryByTestId('os-navbar-agent-option-codex-seat')).toBeNull()
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { USER_PREFS_CHANGED_EVENT, type UserPrefs } from '../../lib/userPrefs'

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

function renderChat(initialEntry = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage REQ-121 start context from here', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('shows Start context from here in cull mode and warns when still over-full', async () => {
    let startCalls = 0
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/v1/preferences/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'user_preferences',
            empty: false,
            favourites: [],
            hidden_agents: [],
            hostname_override: '',
            context_auto_compress_pct: 80,
            context_strategy: 'cull',
            context_cull_trigger_pct: 90,
            context_cull_fraction_pct: 50,
            values: {},
          }),
        } as Response
      }
      if (url.includes('/chat/context-start/') && init?.method === 'POST') {
        startCalls += 1
        const body = JSON.parse(String(init.body || '{}'))
        if (!body.confirm) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              applied: false,
              warning: true,
              reason: 'over_full_warning',
              info: 'Starting context here still leaves usage at 93% (cull trigger 90%). Confirm to proceed or cancel.',
              start_offset: 1,
              estimated_pct: 93,
              cull_trigger_pct: 90,
              context: [{ role: 'assistant', content: 'first answer' }],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            applied: true,
            warning: false,
            reason: 'start_from_here',
            start_offset: 1,
            context_meta: {
              start_offset: 1,
              last_event: { kind: 'start_from_here', at: '2026-09-05T00:00:00Z' },
            },
          }),
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            conversation_id: 'c-cull',
            kind: 'api',
            editable: true,
            messages: [
              { role: 'user', content: 'first question' },
              { role: 'assistant', content: 'first answer' },
              { role: 'user', content: 'later stays raw' },
            ],
            summaries: [],
            context_meta: { start_offset: 0, last_event: null },
          }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
    })
    vi.stubGlobal('fetch', fetchMock)

    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('first answer')).toBeInTheDocument()
    const buttons = await screen.findAllByRole('button', { name: 'Start context from here' })
    expect(buttons.length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: 'Compress to here' })).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(buttons[0])
    })
    expect(await screen.findByTestId('start-from-here-warning')).toHaveTextContent(
      'Starting context here still leaves usage at 93%',
    )
    expect(startCalls).toBe(1)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: 'Confirm' }))
    })
    expect(await screen.findByTestId('context-starts-here')).toBeInTheDocument()
    expect(startCalls).toBe(2)
    const confirmed = fetchMock.mock.calls.find(
      (entry) =>
        String(entry[0]).includes('/chat/context-start/') &&
        String(entry[1]?.body || '').includes('"confirm":true'),
    )
    expect(confirmed).toBeTruthy()
  })

  it('token popup shows cull strategy after prefs load', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/preferences/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: false,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_strategy: 'cull',
              context_cull_trigger_pct: 90,
              context_cull_fraction_pct: 50,
              context_auto_compress_pct: 80,
              values: {},
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // #776: usage surfaces as the composer badge (server frame), which opens
    // the diagnostics modal on click — the old navbar meter is gone.
    await act(async () => {
      MockWebSocket.instances[0]?.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'context_usage',
            conversation_id: 'c1',
            agent_id: 'support',
            tokens: 12300,
            window: 128000,
            pct: 10,
            estimate: true,
            breakdown: { messages: 8000, summaries: 2000, system: 1500, tools: 800 },
          }),
        }),
      )
    })
    fireEvent.click(screen.getByTestId('context-usage-badge'))
    expect(await screen.findByTestId('token-diagnostics-modal')).toBeInTheDocument()
    expect(await screen.findByTestId('diag-context-strategy')).toHaveTextContent('Cull')
    expect(screen.getByTestId('diag-last-context-event')).toHaveTextContent('None yet')
  })

  it('updates the bubble context menu when Settings switches Cull/Compress (#331)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/preferences/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: false,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              context_auto_compress_pct: 80,
              context_strategy: 'compress',
              context_cull_trigger_pct: 90,
              context_cull_fraction_pct: 50,
              values: {},
            }),
          } as Response
        }
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'codey',
              conversation_id: 'c-strategy',
              kind: 'api',
              editable: true,
              messages: [
                { role: 'user', content: 'first question' },
                { role: 'assistant', content: 'first answer' },
              ],
              summaries: [],
              context_meta: { start_offset: 0, last_event: null },
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const bubble = await screen.findByText('first answer')
    fireEvent.contextMenu(bubble, { clientX: 120, clientY: 80 })
    expect(await screen.findByTestId('context-menu-compress-to-here')).toBeInTheDocument()
    expect(screen.queryByTestId('context-menu-start-from-here')).not.toBeInTheDocument()

    await act(async () => {
      window.dispatchEvent(
        new CustomEvent<UserPrefs>(USER_PREFS_CHANGED_EVENT, {
          detail: {
            object: 'user_preferences',
            principal: '',
            guest: false,
            empty: false,
            favourites: [],
            hidden_agents: [],
            hostname_override: '',
            context_auto_compress_pct: 80,
            context_strategy: 'cull',
            context_cull_trigger_pct: 90,
            context_cull_fraction_pct: 50,
            values: {},
            agent_dropdowns: {},
          },
        }),
      )
    })
    expect(await screen.findByTestId('context-menu-start-from-here')).toBeInTheDocument()
    expect(screen.queryByTestId('context-menu-compress-to-here')).not.toBeInTheDocument()
  })
})

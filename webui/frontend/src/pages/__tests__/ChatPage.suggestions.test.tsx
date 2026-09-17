import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useSearchParams } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { localSettingsKey } from '../../lib/agentSettings'

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

const KICKSTART = ['What should we explore first?', 'Show me how this agent is set up']
const CONTINUE = ['Can you expand on that?', 'What are the main risks?']

function stubFetch(opts: { useSuggestions?: boolean; cli?: boolean } = {}) {
  const useSuggestions = opts.useSuggestions ?? true
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/suggestions/')) {
        const chips = url.includes('mode=continue') ? CONTINUE : KICKSTART
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'suggestions', suggestions: chips }),
        } as Response
      }
      if (url.includes('/settings/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            new_chat_per_task: false,
            use_suggestions: useSuggestions,
          }),
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: opts.cli ? 'cli_agent' : 'codey',
            conversation_id: 'conv-1',
            messages: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [
            { id: 'codey', name: 'Codey', description: 'Coder' },
            {
              id: 'cli_agent',
              name: 'CLI',
              description: 'CLI seat',
              tags: ['cli'],
            },
            {
              id: 'api_agent',
              name: 'API',
              description: 'API seat',
              tags: ['api'],
            },
            {
              id: 'remote_harness',
              name: 'Remote',
              description: 'Remote seat',
              tags: ['remote'],
            },
          ],
        }),
      } as Response
    }),
  )
}

function renderChat(entry = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage REQ-85 suggestion chips', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    window.localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  async function openChat(entry = '/chat?blueprint=codey') {
    renderChat(entry)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    return MockWebSocket.instances[0]!
  }

  it('empty thread + suggestions on → kickstart chips', async () => {
    window.localStorage.setItem(
      localSettingsKey('codey'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch()
    await openChat()
    const chips = await screen.findByTestId('suggestion-chips')
    expect(chips).toBeInTheDocument()
    expect(screen.getByRole('button', { name: KICKSTART[0] })).toBeInTheDocument()
    expect(chips.querySelector('.chat-bubble')).toBeNull()
  })

  it('click chip sends that exact user message', async () => {
    window.localStorage.setItem(
      localSettingsKey('codey'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch()
    const ws = await openChat()
    const chip = await screen.findByRole('button', { name: KICKSTART[0] })
    fireEvent.click(chip)
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toMatchObject({
      message: KICKSTART[0],
      blueprint: 'codey',
    })
  })

  it('after a stub generation, chips refresh', async () => {
    window.localStorage.setItem(
      localSettingsKey('codey'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch()
    const ws = await openChat()
    await screen.findByTestId('suggestion-chips')
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">hi</div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-abc" class="assistant-message"></div></div>',
        }),
      )
    })
    expect(
      screen.getAllByTestId('suggestion-chip').every((el) => !(el as HTMLButtonElement).disabled),
    ).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: KICKSTART[0] }))
    expect(ws.send).not.toHaveBeenCalled()
    const queued = screen.getAllByTestId('queued-row')
    expect(queued).toHaveLength(1)
    expect(queued[0]).toHaveTextContent(KICKSTART[0])
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-abc" hx-swap-oob="true">Done.</div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({ type: 'suggestions', suggestions: CONTINUE }),
        }),
      )
    })
    expect(await screen.findByRole('button', { name: CONTINUE[0] })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: KICKSTART[0] })).not.toBeInTheDocument()
  })

  it('suggestions off → no chips', async () => {
    stubFetch({ useSuggestions: false })
    await openChat()
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.queryByTestId('suggestion-chips')).not.toBeInTheDocument()
  })

  it('CLI agent with suggestions on still shows chips (launch spiel #529)', async () => {
    window.localStorage.setItem(
      localSettingsKey('cli_agent'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch({ cli: true })
    await openChat('/chat?blueprint=cli_agent')
    expect(await screen.findByTestId('suggestion-chips')).toBeInTheDocument()
  })

  it('API agent with suggestions on still shows chips', async () => {
    window.localStorage.setItem(
      localSettingsKey('api_agent'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch()
    await openChat('/chat?blueprint=api_agent')
    expect(await screen.findByTestId('suggestion-chips')).toBeInTheDocument()
  })

  it('remote agent with suggestions on still shows chips', async () => {
    window.localStorage.setItem(
      localSettingsKey('remote_harness'),
      JSON.stringify({ use_suggestions: true }),
    )
    stubFetch()
    await openChat('/chat?blueprint=remote_harness')
    expect(await screen.findByTestId('suggestion-chips')).toBeInTheDocument()
  })

  it('does not apply the previous seat settings after a switch (#333)', async () => {
    let releaseCodey: (value?: unknown) => void = () => {}
    const codeyGate = new Promise((resolve) => {
      releaseCodey = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/agents/codey/settings/')) {
          await codeyGate
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'codey',
              new_chat_per_task: true,
              use_suggestions: true,
            }),
          } as Response
        }
        if (url.includes('/settings/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'api_agent',
              new_chat_per_task: false,
              use_suggestions: false,
            }),
          } as Response
        }
        if (url.includes('/suggestions/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'suggestions',
              suggestions: KICKSTART,
            }),
          } as Response
        }
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: url.includes('api_agent') ? 'api_agent' : 'codey',
              conversation_id: 'conv-1',
              messages: [],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              { id: 'codey', name: 'Codey', description: 'Coder' },
              { id: 'api_agent', name: 'API', description: 'API seat', tags: ['api'] },
            ],
          }),
        } as Response
      }),
    )

    function Switcher() {
      const [, setParams] = useSearchParams()
      return (
        <button type="button" onClick={() => setParams({ blueprint: 'api_agent' })}>
          switch-api
        </button>
      )
    }

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
            <Switcher />
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(screen.getByRole('button', { name: 'switch-api' }))
    await act(async () => {
      MockWebSocket.instances.at(-1)?.open()
    })
    await act(async () => {
      releaseCodey()
      await codeyGate
    })
    await act(async () => {
      await Promise.resolve()
    })
    expect(screen.queryByTestId('suggestion-chips')).not.toBeInTheDocument()
  })
})

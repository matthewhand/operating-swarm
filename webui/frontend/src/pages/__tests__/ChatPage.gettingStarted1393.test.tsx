import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { loadAgentEdit, saveAgentEdit } from '../../lib/agentEdits'

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

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/agents/') && url.includes('/skills')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'agent_skill_list',
            agent_id: 'codey',
            first_run_pending: true,
            gettingStarted: { skill: 'welcome-tour' },
            skills: [
              {
                name: 'welcome-tour',
                description: 'Walk the first conversation.',
                instructions: 'Greet the operator and list three first steps.',
              },
            ],
          }),
        } as Response
      }
      if (url.includes('/suggestions/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'suggestions', suggestions: [] }),
        } as Response
      }
      if (url.includes('/settings/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            new_chat_per_task: false,
            use_suggestions: false,
          }),
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            conversation_id: 'conv-codey',
            messages: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'Coder' }],
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

describe('ChatPage getting-started after pack import (#1393)', () => {
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

  it('empty first chat surfaces the imported getting-started skill', async () => {
    stubFetch()
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const banner = await screen.findByTestId('getting-started-flow')
    expect(banner).toHaveTextContent('welcome-tour')
    expect(banner).toHaveTextContent('When to use')
    expect(banner).toHaveTextContent('Walk the first conversation.')
    expect(await screen.findByRole('button', { name: 'Walk the first conversation.' })).toBeInTheDocument()
  })

  it('clicking the getting-started chip sends the first-chat prompt', async () => {
    stubFetch()
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    const chip = await screen.findByRole('button', { name: 'Walk the first conversation.' })
    fireEvent.click(chip)
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    const sent = ws.send.mock.calls
      .map((call) => String(call[0]))
      .find((raw) => !raw.includes('"kind":"subscribe"'))
    expect(JSON.parse(String(sent))).toMatchObject({
      message: 'Walk the first conversation.',
      blueprint: 'codey',
    })
  })

  it('empty first chat does not overwrite sidepane skill selections', async () => {
    saveAgentEdit('codey', { skills: ['conventional-commit'] })
    stubFetch()
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await screen.findByTestId('getting-started-flow')
    expect(loadAgentEdit('codey').skills).toEqual(['conventional-commit'])
  })
})

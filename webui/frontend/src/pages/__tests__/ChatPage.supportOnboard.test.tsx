import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { SUPPORT_JOURNEY_KICKSTART } from '../../lib/supportJourney'

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
            agent_id: 'support',
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
            agent_id: 'support',
            conversation_id: 'conv-support',
            messages: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [
            {
              id: 'support',
              name: 'Support',
              description: 'Onboarding. First team.',
              role: 'support',
            },
          ],
        }),
      } as Response
    }),
  )
}

function renderChat(entry = '/chat') {
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

describe('ChatPage REQ-137 Support journey chips', () => {
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

  async function openSupport() {
    stubFetch()
    renderChat('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    return MockWebSocket.instances[0]!
  }

  it('empty Support thread shows journey chips without Use suggestions', async () => {
    const ws = await openSupport()
    expect(await screen.findByTestId('suggestion-chips')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SUPPORT_JOURNEY_KICKSTART[0] })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SUPPORT_JOURNEY_KICKSTART[1] })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SUPPORT_JOURNEY_KICKSTART[2] })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: SUPPORT_JOURNEY_KICKSTART[3] })).toBeInTheDocument()
    expect(screen.getByText(/one pane/i)).toBeInTheDocument()
    expect(ws).toBeTruthy()
  })

  it('clicking the BA → Engineer → Tester chip sends that message', async () => {
    const ws = await openSupport()
    const chip = await screen.findByRole('button', {
      name: 'Create a BA → Engineer → Tester workflow',
    })
    fireEvent.click(chip)
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
      message: 'Create a BA → Engineer → Tester workflow',
      blueprint: 'support',
    })
  })

  it('clicking Create a team sends that message', async () => {
    const ws = await openSupport()
    const chip = await screen.findByRole('button', { name: 'Create a team' })
    fireEvent.click(chip)
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
      message: 'Create a team',
      blueprint: 'support',
    })
  })
})

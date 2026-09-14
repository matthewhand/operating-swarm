import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import {
  loadUnreadAgentIds,
  markAgentUnread,
  UNREAD_AGENTS_STORAGE_KEY,
} from '../../lib/unreadAgents'
import ChatPage from '../ChatPage'

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
  emitFinal(text: string, id = 'message-response-final-1') {
    // Real chat WS frames are HTMx HTML partials (chatWs.parseChatWsMessage).
    this.onmessage?.(
      new MessageEvent('message', {
        data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${text}</div>`,
      }),
    )
  }
}

function stubChat() {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            clis: ['grok'],
            known: ['grok'],
            configured: ['grok'],
            discovered: ['grok'],
            installed: ['grok'],
            suggestions: {},
            default_cli: 'grok',
            native_consensus: {},
            catalog: {},
            list_models: {},
            rail: [
              {
                id: 'codey',
                object: 'cli.agent',
                name: 'codey',
                cli: 'grok',
                kind: 'cli',
                description: 'Host CLI',
                installed: true,
              },
            ],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'CLI' }],
          messages: [],
        }),
      } as Response
    }),
  )
}

function renderChat(initialEntry = '/chat?blueprint=codey&cli=grok') {
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

function scrollPane() {
  return screen.getByRole('log', { name: 'Conversation' }) as HTMLElement
}

function pinPane(el: HTMLElement, pinned: boolean) {
  Object.defineProperty(el, 'scrollHeight', { value: 3000, configurable: true })
  Object.defineProperty(el, 'clientHeight', { value: 1000, configurable: true })
  Object.defineProperty(el, 'scrollTop', {
    value: pinned ? 2000 : 100,
    configurable: true,
    writable: true,
  })
}

describe('ChatPage rail unread vs pinned-to-bottom (#96)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
    try {
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true })
    } catch {
      /* already configurable */
    }
  })

  it('clears the seat unread when visible and pinned to the bottom', { timeout: 10000 }, async () => {
    stubChat()
    markAgentUnread('codey')
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(loadUnreadAgentIds()).toContain('codey')

    const el = scrollPane()
    pinPane(el, true)
    await act(async () => {
      fireEvent.scroll(el)
    })

    expect(loadUnreadAgentIds()).not.toContain('codey')
    expect(localStorage.getItem(UNREAD_AGENTS_STORAGE_KEY)).not.toContain('codey')
  })

  it('does not clear the seat unread while the tab is hidden', { timeout: 10000 }, async () => {
    stubChat()
    markAgentUnread('codey')
    Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true })
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const el = scrollPane()
    pinPane(el, true)
    await act(async () => {
      fireEvent.scroll(el)
    })

    expect(loadUnreadAgentIds()).toContain('codey')
  })

  it('does not clear the seat unread while scrolled up', { timeout: 10000 }, async () => {
    stubChat()
    markAgentUnread('codey')
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const el = scrollPane()
    pinPane(el, false)
    await act(async () => {
      fireEvent.scroll(el)
    })

    expect(loadUnreadAgentIds()).toContain('codey')
  })

  it('marks the selected seat unread when a turn completes while scrolled up', { timeout: 10000 }, async () => {
    stubChat()
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const el = scrollPane()
    pinPane(el, false)
    await act(async () => {
      fireEvent.scroll(el)
    })
    await act(async () => {
      MockWebSocket.instances[0]?.emitFinal('finished reply')
    })

    expect(loadUnreadAgentIds()).toContain('codey')
  })

  it('does not mark the selected seat unread when the turn completes while pinned at the bottom', { timeout: 10000 }, async () => {
    stubChat()
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const el = scrollPane()
    pinPane(el, true)
    await act(async () => {
      fireEvent.scroll(el)
    })
    await act(async () => {
      MockWebSocket.instances[0]?.emitFinal('finished reply')
    })

    expect(loadUnreadAgentIds()).not.toContain('codey')
  })
})

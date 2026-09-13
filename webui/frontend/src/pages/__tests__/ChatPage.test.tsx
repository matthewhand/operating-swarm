import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Link, MemoryRouter, Route, Routes, useSearchParams } from 'react-router-dom'
import ChatPage, { chatLoginHref, chatLoginNext } from '../ChatPage'
import { ToastProvider, TOAST_KIND_WS_DISCONNECT } from '../../components/DaisyUI'
import AgentAvatar from '../../components/AgentAvatar'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'
import { AVATAR_THEME_STORAGE_KEY, saveAvatarTheme } from '../../lib/avatarTheme'
import { OPEN_AGENT_EDITOR_EVENT } from '../../lib/agentSettings'
import { saveEnabledPluginToolIds } from '../../lib/chatPluginTools'

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
  close = vi.fn(() => {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code: 1000 }))
  })

  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }

  /** Simulate handshake/network failure before onopen (opaque browser 1006). */
  failBeforeOpen(code = 1006) {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code }))
  }

  /** Simulate DjangoChatConsumer auth gate (accept then close 4401). */
  rejectAuth() {
    this.open()
    this.readyState = 3
    this.onclose?.(
      new CloseEvent('close', { code: 4401, reason: 'authentication required' }),
    )
  }
}

function renderChat(initialEntry = '/chat') {
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

describe('chatLoginHref helpers', () => {
  it('builds a rooted next path and encodes the Sign-in CTA', () => {
    expect(chatLoginNext(new URLSearchParams())).toBe('/chat')
    expect(chatLoginNext(new URLSearchParams('blueprint=codey'))).toBe(
      '/chat?blueprint=codey',
    )
    expect(chatLoginHref(new URLSearchParams('blueprint=codey'))).toBe(
      `/accounts/login/?next=${encodeURIComponent('/chat?blueprint=codey')}`,
    )
  })
})

describe('ChatPage reconnect focus', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('does not auto-focus the composer on the initial connect', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    expect(composer).not.toHaveFocus()
    expect(composer).not.toBeDisabled()
  })

  it('moves focus to the composer after a successful reconnect', async () => {
    renderChat()

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // Drop the socket so the reconnect CTA appears.
    await act(async () => {
      MockWebSocket.instances[0]?.close()
    })

    const reconnect = await screen.findByRole('button', { name: /Reconnect/i })
    fireEvent.click(reconnect)

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    })
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    await waitFor(() => {
      expect(composer).not.toBeDisabled()
    })
    expect(composer).toHaveFocus()
  })
})

describe('ChatPage Unavailable / Sign-in CTA + connection status', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('keeps the composer typeable while connecting and stays silent when healthy', async () => {
    renderChat()

    const statusRegion = screen.getByRole('status', { name: 'Connection status' })
    expect(statusRegion).toHaveAttribute('aria-live', 'polite')
    expect(statusRegion).toHaveTextContent(/Connecting/i)

    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    // #167: a connecting/closed socket must never block typing.
    expect(composer).not.toBeDisabled()
    expect(composer).toHaveAttribute('placeholder', 'Message …')
    expect(screen.queryByRole('button', { name: /^Send$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()
    expect(screen.getByTestId('chat-conn-status')).toBeInTheDocument()
    expect(screen.queryByText(/^Connected$/)).not.toBeInTheDocument()

    fireEvent.change(composer, { target: { value: 'typed while connecting' } })
    expect(composer).toHaveValue('typed while connecting')
    // A draft reveals Send; offline it queues instead of being disabled away.
    expect(screen.getByRole('button', { name: /^Send$/i })).toBeInTheDocument()

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    await waitFor(() => {
      expect(screen.queryByTestId('chat-conn-status')).not.toBeInTheDocument()
    })
    expect(composer).not.toBeDisabled()
    expect(screen.queryByText(/^Connected$/)).not.toBeInTheDocument()
    expect(statusRegion).toHaveTextContent('')
  })

  it('shows session-cookie Sign-in CTA when the server closes with 4401', async () => {
    renderChat('/chat?blueprint=hybrid_team')

    await act(async () => {
      MockWebSocket.instances[0]?.rejectAuth()
    })

    const signIn = await screen.findByRole('link', { name: /Sign in/i })
    expect(signIn).toHaveAttribute(
      'href',
      `/accounts/login/?next=${encodeURIComponent('/chat?blueprint=hybrid_team')}`,
    )
    expect(screen.getByRole('button', { name: /Reconnect/i })).toBeInTheDocument()
    const statusRegion = screen.getByRole('status', { name: 'Connection status' })
    expect(statusRegion).toHaveTextContent(/Unavailable — sign in required/i)
    expect(screen.getByText(/session cookie/i)).toBeInTheDocument()
  })

  it('does not blame login when the socket never opens (ASGI/network)', async () => {
    renderChat()

    await act(async () => {
      MockWebSocket.instances[0]?.failBeforeOpen()
    })

    expect(
      await screen.findByText(/Unavailable — websocket unreachable/i),
    ).toBeInTheDocument()
    expect(screen.getByText(/ALLOWED_HOSTS/i)).toBeInTheDocument()
    expect(screen.queryByText(/session cookie/i)).not.toBeInTheDocument()
  })

  it('clears the composer draft on Escape', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'draft that should clear' } })
    expect(composer).toHaveValue('draft that should clear')

    fireEvent.keyDown(composer, { key: 'Escape' })
    expect(composer).toHaveValue('')
  })
})

describe('ChatPage disconnect toasts (REQ-112 #489)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  function disconnectToasts() {
    return document.querySelectorAll(`[data-toast-kind="${TOAST_KIND_WS_DISCONNECT}"]`)
  }

  it('shows at most one disconnect toast, clears it on reconnect, and keeps unrelated toasts', async () => {
    renderChat()

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await act(async () => {
      MockWebSocket.instances[0]?.close()
    })

    expect(await screen.findByText('Chat disconnected')).toBeInTheDocument()
    expect(disconnectToasts()).toHaveLength(1)

    fireEvent.click(screen.getByRole('button', { name: 'Voice input' }))
    expect(await screen.findByText(/Speech recognition is not available/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Reconnect/i }))
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    })
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.failBeforeOpen()
    })

    expect(await screen.findByText('Chat websocket unreachable')).toBeInTheDocument()
    expect(disconnectToasts()).toHaveLength(1)
    expect(screen.queryByText('Chat disconnected')).not.toBeInTheDocument()
    expect(screen.getByText(/Speech recognition is not available/i)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /Reconnect/i }))
    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(3)
    })
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    await waitFor(() => {
      expect(disconnectToasts()).toHaveLength(0)
    })
    expect(screen.queryByText('Chat disconnected')).not.toBeInTheDocument()
    expect(screen.queryByText('Chat websocket unreachable')).not.toBeInTheDocument()
    expect(screen.getByText(/Speech recognition is not available/i)).toBeInTheDocument()
  })

  it('does not stack disconnect toasts when ChatPage remounts while the socket is down', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <ChatPage key="one" />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await act(async () => {
      MockWebSocket.instances[0]?.failBeforeOpen()
    })
    expect(await screen.findByText('Chat websocket unreachable')).toBeInTheDocument()
    expect(disconnectToasts()).toHaveLength(1)

    rerender(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <ChatPage key="two" />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    await waitFor(() => {
      expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2)
    })
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.failBeforeOpen()
    })

    expect(disconnectToasts()).toHaveLength(1)
    expect(screen.getAllByText('Chat websocket unreachable')).toHaveLength(1)
  })
})

describe('ChatPage agent header (no blueprint dropdown)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('uses the ?blueprint= id as the chat header without a catalog dropdown', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=just_launched_team')

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByRole('heading', { name: 'just_launched_team' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Blueprint' })).not.toBeInTheDocument()
  })

  it('shows the discoverable agent name in the header', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=codey')

    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByRole('heading', { name: 'Codey' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Blueprint' })).not.toBeInTheDocument()
  })

  it('renders the selected agent avatar next to the name (REQ-60)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const identity = await screen.findByTestId('selected-agent-header')
    const heading = within(identity).getByRole('heading', { name: 'Codey' })
    const avatar = identity.querySelector('[data-agent-avatar]')
    expect(avatar).toBeTruthy()
    expect(avatar).toHaveAttribute('data-agent-avatar', 'default')
    expect(avatar).toHaveClass('os-chat-header__avatar')
    expect(identity.firstElementChild).toBe(avatar)
    expect(heading.compareDocumentPosition(avatar!) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
    expect(within(identity).getByRole('button', { name: 'Open Codey definition' })).toBeInTheDocument()
  })

  it('uses the same custom face in the header as AgentAvatar would on the rail', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [
            {
              id: 'codey',
              name: 'Codey',
              description: 'Code assistant',
              avatar_path: '/avatars/codey_avatar.png',
            },
          ],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const identity = await screen.findByTestId('selected-agent-header')
    const headerImg = identity.querySelector('img')
    expect(identity.querySelector('[data-agent-avatar]')).toHaveAttribute(
      'data-agent-avatar',
      'custom',
    )
    expect(headerImg).toHaveAttribute('src', '/avatars/codey_avatar.png')

    const rail = render(
      <AgentAvatar src="/avatars/codey_avatar.png" size="sm" />,
    )
    expect(rail.container.querySelector('img')).toHaveAttribute(
      'src',
      headerImg?.getAttribute('src'),
    )
    rail.unmount()
  })
})

function deliverMockInference(
  ws: MockWebSocket,
  reply: string,
  id = 'message-response-mock1',
) {
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">echo</div></div>`,
    }),
  )
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`,
    }),
  )
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${reply}</div>`,
    }),
  )
}

describe('ChatPage Send path with mock inference', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.removeItem('swarm_notify_agents')
    window.localStorage.removeItem('swarm_agent_chat:support')
    window.localStorage.removeItem('swarm_chat_plugin_tools')
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => false })
  })

  it('renders mock assistant content after the user types and clicks Send', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'ping the mock' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    expect(ws.send).toHaveBeenCalled()
    expect(JSON.parse(ws.send.mock.calls[0][0] as string)).toMatchObject({
      message: 'ping the mock',
      blueprint: 'support',
      params: { skill: 'support-session-ownership', enabled_tools: [] },
    })

    await act(async () => {
      deliverMockInference(ws, 'MOCK_INFERENCE_VITEST_REPLY')
    })

    expect(screen.getByText('MOCK_INFERENCE_VITEST_REPLY')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'follow-up' },
    })
    expect(screen.getByRole('button', { name: /^Send$/i })).toBeEnabled()
  })

  it('sends the per-chat enabled_tools allowlist on Send (#805)', async () => {
    window.localStorage.setItem('swarm_agent_chat:support', 'conv-support-805')
    saveEnabledPluginToolIds('conv-support-805', ['web_search', 'web_fetch'])
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'use search' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    expect(JSON.parse(ws.send.mock.calls[0][0] as string)).toMatchObject({
      message: 'use search',
      blueprint: 'support',
      params: {
        skill: 'support-session-ownership',
        enabled_tools: ['web_search', 'web_fetch'],
      },
    })
  })
})

describe('ChatPage Send button honesty while streaming', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('keeps a real Send control (no busy spinner) while an assistant reply streams', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-abc123" class="assistant-message"></div></div>',
        }),
      )
    })

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'follow-up while streaming' },
    })
    const send = screen.getByRole('button', { name: /^Send$/i })
    expect(send).not.toHaveAttribute('aria-busy', 'true')
    expect(send).not.toHaveClass('loading')
    expect(send.querySelector('.loading')).toBeNull()

    const loaders = screen.getAllByRole('status', { name: 'Loading' })
    expect(loaders.length).toBeGreaterThan(0)
  })

  it('notifies rail bump when a generation completes', async () => {
    const completed: string[] = []
    const onComplete = (event: Event) => {
      completed.push((event as CustomEvent<{ agentId?: string }>).detail?.agentId || '')
    }
    window.addEventListener('swarm:generation-complete', onComplete)
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-done1" hx-swap-oob="true">finished</div>',
        }),
      )
    })
    expect(completed).toEqual(['codey'])
    window.removeEventListener('swarm:generation-complete', onComplete)
  })

  it('REQ-98: Notification constructor runs only when On + granted + hidden tab', async () => {
    const { NOTIFY_AGENTS_STORAGE_KEY, resetNotifyDedupe } = await import(
      '../../lib/agentNotifications'
    )
    localStorage.setItem(NOTIFY_AGENTS_STORAGE_KEY, JSON.stringify(['codey']))
    resetNotifyDedupe()
    const instances: Array<{ title: string; body?: string }> = []
    class MockNotification {
      static permission: NotificationPermission = 'granted'
      static requestPermission = vi.fn(async () => 'granted' as NotificationPermission)
      title: string
      options?: NotificationOptions
      onclick: ((this: Notification, ev: Event) => void) | null = null
      close = vi.fn()
      constructor(title: string, options?: NotificationOptions) {
        this.title = title
        this.options = options
        instances.push({ title, body: options?.body })
      }
    }
    vi.stubGlobal('Notification', MockNotification)
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true })

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-done-n1" hx-swap-oob="true">finished quietly</div>',
        }),
      )
    })
    expect(instances.length).toBeGreaterThan(0)
    expect(instances[0].body).toContain('finished quietly')

    instances.length = 0
    localStorage.setItem(NOTIFY_AGENTS_STORAGE_KEY, '[]')
    resetNotifyDedupe()
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-done-n2" hx-swap-oob="true">should not popup</div>',
        }),
      )
    })
    expect(instances).toHaveLength(0)
  })
})

describe('ChatPage auto-reconnect backoff', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('reconnects with backoff after unexpected drop, and skips auth 4401', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    await act(async () => {
      const ws = MockWebSocket.instances[0]!
      ws.readyState = 3
      ws.onclose?.(new CloseEvent('close', { code: 1006 }))
    })

    expect(MockWebSocket.instances).toHaveLength(1)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000)
    })
    expect(MockWebSocket.instances.length).toBeGreaterThanOrEqual(2)

    // Auth gate must not auto-reconnect.
    const authClient = MockWebSocket.instances.length
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.rejectAuth()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000)
    })
    expect(MockWebSocket.instances.length).toBe(authClient)
  })
})

describe('ChatPage computer-control pane (REQ-80)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows a top-right Computer control tool by default (not agent-attached)', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const tools = screen.getByRole('toolbar', { name: 'Chat tools' })
    const trigger = screen.getByRole('button', { name: 'Computer control' })
    expect(tools).toContainElement(trigger)
    expect(trigger).toHaveAttribute('aria-label', 'Computer control')
    expect(trigger).not.toHaveTextContent(/Computer control/i)
    expect(trigger.closest('.tooltip')).toHaveAttribute('data-tip', 'Computer control')

    fireEvent.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Computer control', hidden: true })
    expect(dialog).toHaveClass('modal-open')
    expect(dialog).toHaveClass('modal-end')
    expect(dialog).toHaveTextContent(/Routines/)
    expect(dialog).toHaveTextContent(/screen/)
    expect(dialog.textContent).not.toMatch(/WIP|:8001/i)
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })
})

describe('ChatPage header Edit control (REQ-120)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('is an icon-only pencil that still opens the agent editor', async () => {
    const opened: unknown[] = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent).detail)
    }
    window.addEventListener(OPEN_AGENT_EDITOR_EVENT, onOpen)

    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const header = screen.getByTestId('selected-agent-header')
    const edit = within(header).getByRole('button', { name: 'Edit agent' })
    expect(edit).toHaveAttribute('aria-label', 'Edit agent')
    expect(edit).toHaveClass('btn-square')
    expect(edit.querySelector('svg')).toBeTruthy()
    expect(edit).not.toHaveTextContent(/^Edit$/i)
    expect(within(header).queryByText('Edit')).not.toBeInTheDocument()
    expect(edit.closest('.tooltip')).toHaveAttribute('data-tip', 'Edit agent')

    fireEvent.click(edit)
    expect(opened).toEqual([{ agentId: 'support' }])
    window.removeEventListener(OPEN_AGENT_EDITOR_EVENT, onOpen)
  })
})

describe('ChatPage markdown bubbles', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('defaults /chat to Support with a quiet system pill, not a transcript dump', async () => {
    const briefing =
      '**Agents**\n- Support · support\n\n**Inference** off\n\n**Gate** — dangerous tool call? yes/no. Until wired, all approved.\n**Skeptic** — prompt done? If not, findings go back to retry.'
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/support/context')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'support.context',
              briefing,
              welcome: briefing,
              inference: { configured: false },
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              { id: 'codey', name: 'Codey', description: 'Code' },
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

    renderChat('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.getByRole('heading', { name: 'Support' })).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Blueprint' })).not.toBeInTheDocument()
    expect(screen.queryByTestId('chat-md')).not.toBeInTheDocument()
    expect(screen.queryByText('Connected and ready')).not.toBeInTheDocument()
    expect(screen.queryByText(/Welcome —/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Inference/)).not.toBeInTheDocument()
    expect(screen.queryByText(/Gate/)).not.toBeInTheDocument()
  })

  it('renders assistant markdown (bold/code) in the bubble', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-md1" class="assistant-message"></div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-md1" hx-swap-oob="true" class="assistant-message">**hello** and `code`</div>',
        }),
      )
    })

    expect(screen.getByText('hello').tagName).toBe('STRONG')
    expect(screen.getByText('code').tagName).toBe('CODE')
    expect(screen.getByRole('button', { name: 'Read aloud' })).toBeInTheDocument()
  })

  it('shows the default agent avatar in the header and on assistant bubbles', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const identity = screen.getByLabelText('Agent identity: Support')
    expect(within(identity).getByRole('heading', { name: 'Support' })).toBeInTheDocument()
    expect(identity.querySelector('[data-agent-avatar="default"]')).toBeTruthy()
  })

  it('paints the selected agent custom avatar in header, empty chat, and bubbles', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [
            {
              id: 'codey',
              name: 'Codey',
              description: 'Code assistant',
              avatar_path: '/avatars/codey_avatar.png',
            },
          ],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const identity = await screen.findByLabelText('Agent identity: Codey')
    expect(within(identity).getByRole('heading', { name: 'Codey' })).toBeInTheDocument()
    const headerAvatar = identity.querySelector('[data-agent-avatar="custom"]')
    expect(headerAvatar).toBeTruthy()
    const headerImg = identity.querySelector('img')
    expect(headerImg).toHaveAttribute('src', '/avatars/codey_avatar.png')
  })
})

describe('ChatPage per-agent persistence (no retention chrome)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('restores a persisted agent thread after load and keeps retention off the chrome', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'jeeves',
              conversation_id: 'agt-1-jeeves',
              messages: [
                { role: 'user', content: 'prior question' },
                { role: 'assistant', content: 'prior answer' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'jeeves', name: 'Jeeves', description: 'Butler' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=jeeves')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('prior question')).toBeInTheDocument()
    expect(screen.getByText('prior answer')).toBeInTheDocument()
    expect(screen.getByTestId('chat-status')).toHaveTextContent('Restored session')
    expect(screen.queryByText(/Move to trash/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Empty trash/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Disk used/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /archive/i })).not.toBeInTheDocument()
  })

  it('renders a CLI session notice without a chat-start/chat-end bubble', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'agt-1-cli',
              messages: [
                { role: 'user', content: 'hello' },
                {
                  role: 'status',
                  content: 'Started a new grok session.',
                  ts: '2026-09-05T12:00:00Z',
                },
                { role: 'assistant', content: 'hi' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const notices = await screen.findAllByTestId('chat-status')
    expect(notices[0]).toHaveTextContent('Resumed CLI session')
    const started = notices.find((n) => n.textContent?.includes('Started a new grok session.'))
    expect(started).toBeTruthy()
    expect(started).toHaveAttribute('data-role', 'status')
    expect(started).toHaveClass('os-chat-status')
    expect(started!.className).not.toMatch(/chat-start|chat-end/)
    expect(started!.querySelector('.chat-bubble')).toBeNull()
    expect(started!.querySelector('span')).toHaveTextContent('Started a new grok session.')
    expect(started!.querySelector('[data-testid="chat-status-time"]')).toBeTruthy()
    expect(started).toHaveAttribute('data-ts', '2026-09-05T12:00:00Z')
    expect(screen.getByText('hello').closest('.chat-end')).toBeTruthy()
    expect(screen.getByText('hi').closest('.chat-start')).toBeTruthy()
    const startedPos = started!.compareDocumentPosition(screen.getByText('hi'))
    expect(startedPos & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('reconstructs status chrome from turns + ui_events metadata', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'agt-1-cli',
              turns: [
                { role: 'user', content: 'hello', seq: 0 },
                { role: 'assistant', content: 'hi', seq: 2 },
              ],
              ui_events: [
                {
                  role: 'status',
                  content: 'Started a new grok session.',
                  ts: '2026-09-05T12:00:00Z',
                  seq: 1,
                },
              ],
              messages: [{ role: 'user', content: 'stale mixed should be ignored' }],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const notices = await screen.findAllByTestId('chat-status')
    const started = notices.find((n) => n.textContent?.includes('Started a new grok session.'))
    expect(started).toBeTruthy()
    expect(started!.querySelector('[data-testid="chat-status-time"]')).toBeTruthy()
    expect(started).toHaveAttribute('data-ts', '2026-09-05T12:00:00Z')
    expect(screen.queryByText('stale mixed should be ignored')).not.toBeInTheDocument()
    expect(screen.getByText('hello')).toBeInTheDocument()
    expect(screen.getByText('hi')).toBeInTheDocument()
  })

  it('renders prior history as a System/Agent family pill, not a deleted transcript', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'cli-cli_agent-abc',
              messages: [
                {
                  role: 'system',
                  content: '**User:** old question\n\n**Assistant:** old answer',
                  kind: 'prior_history',
                },
                { role: 'status', content: 'Switched to grok session sid-1.' },
                { role: 'user', content: 'from cli' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent&session=cli-cli_agent-abc')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const pill = await screen.findByRole('button', { name: /Prior history/i })
    expect(pill).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByTestId('system-preload-content')).not.toBeInTheDocument()
    const switchNotice = screen
      .getAllByTestId('chat-status')
      .find((n) => n.textContent?.includes('Switched to grok session sid-1.'))
    expect(switchNotice).toBeTruthy()
    expect(screen.getByText('from cli')).toBeInTheDocument()

    fireEvent.click(pill)
    expect(pill).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByTestId('system-preload-content')).toHaveTextContent('old question')
    expect(screen.getByTestId('system-preload-content')).toHaveTextContent('old answer')
  })

  it('REQ-92: live new-session status lands immediately before the assistant reply', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
        }),
      } as Response),
    )

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'hello grok' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">hello grok</div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-cli1" class="assistant-message"></div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status">Started a new grok session.</div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-cli1" class="assistant-message" hx-swap-oob="true">reply after start</div>',
        }),
      )
    })

    const started = screen.getByText('Started a new grok session.')
    const reply = screen.getByText('reply after start')
    expect(started.compareDocumentPosition(reply) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(started.closest('.chat-start')).toBeNull()
  })

  it('REQ-92: a resume turn does not print a second Started a new line', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'agt-1-cli',
              messages: [
                { role: 'user', content: 'hello' },
                { role: 'status', content: 'Started a new grok session.' },
                { role: 'assistant', content: 'hi' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('Started a new grok session.')).toBeInTheDocument()

    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">again</div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-cli2" class="assistant-message"></div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line os-chat-status">Resumed grok session.</div></div>',
        }),
      )
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-cli2" class="assistant-message" hx-swap-oob="true">second reply</div>',
        }),
      )
    })

    expect(screen.getAllByText('Started a new grok session.')).toHaveLength(1)
    const resumed = screen.getByText('Resumed grok session.')
    expect(resumed.compareDocumentPosition(screen.getByText('second reply')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('renders info and system thread rows as centred status chrome', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'agt-1-cli',
              messages: [
                { role: 'info', content: 'Connecting…' },
                { role: 'system', content: 'Session ready.' },
                { role: 'user', content: 'ping' },
                { role: 'assistant', content: 'pong' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI Agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const lines = await screen.findAllByTestId('chat-status')
    expect(lines).toHaveLength(3)
    expect(lines[0]).toHaveTextContent('Resumed CLI session')
    expect(lines[1]).toHaveTextContent('Connecting…')
    expect(lines[2]).toHaveTextContent('Session ready.')
    for (const line of lines) {
      expect(line).toHaveClass('os-chat-status')
      expect(line.className).not.toMatch(/chat-start|chat-end/)
      expect(line.querySelector('.chat-bubble')).toBeNull()
    }
    expect(screen.getByText('ping').closest('.chat-end')).toBeTruthy()
    expect(screen.getByText('pong').closest('.chat-start')).toBeTruthy()
  })

  it('REQ-161: restores API / CLI / remote / team threads with a quiet status line', async () => {
    const fixtures: Array<{ entry: string; agent: string; status: string }> = [
      { entry: '/chat?blueprint=codey', agent: 'codey', status: 'Restored session' },
      { entry: '/chat?blueprint=grok_agent', agent: 'grok_agent', status: 'Resumed CLI session' },
      { entry: '/chat?remote=omb', agent: 'remote:omb', status: 'Reconnected remote' },
      { entry: '/chat?team=demo-team', agent: 'team-demo-team', status: 'Restored session' },
    ]
    for (const fixture of fixtures) {
      MockWebSocket.instances = []
      vi.stubGlobal(
        'fetch',
        vi.fn().mockImplementation(async (input: RequestInfo) => {
          const url = String(input)
          if (url.includes('/chat/thread/')) {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: fixture.agent,
                conversation_id: `c-${fixture.agent}`,
                messages: [
                  { role: 'user', content: `prior ${fixture.agent}` },
                  { role: 'assistant', content: 'ok' },
                ],
              }),
            } as Response
          }
          if (url.includes('team_rosters')) {
            return {
              ok: true,
              status: 200,
              json: async () => [{ id: 'demo-team', name: 'Demo Team', members: [] }],
            } as Response
          }
          return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
        }),
      )
      const view = renderChat(fixture.entry)
      await act(async () => {
        MockWebSocket.instances[0]?.open()
      })
      expect(await screen.findByTestId('chat-status')).toHaveTextContent(fixture.status)
      expect(screen.getByText(`prior ${fixture.agent}`)).toBeInTheDocument()
      view.unmount()
    }
  })

  it('REQ-127: composer textarea keeps fenced newlines and user bubbles render pre/code', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'codey',
              conversation_id: 'c-codey',
              messages: [
                {
                  role: 'user',
                  content: '```python\ndef hello():\n    return 1\n```',
                },
              ],
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const fence = await screen.findByTestId('chat-md')
    expect(fence.querySelector('pre')).toBeTruthy()
    expect(fence.querySelector('code')).toBeTruthy()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer.tagName).toBe('TEXTAREA')
    fireEvent.change(composer, {
      target: { value: '```python\nprint(1)\nprint(2)\n```' },
    })
    expect((composer as HTMLTextAreaElement).value).toContain('\n')
    expect((composer as HTMLTextAreaElement).value.split('\n')).toHaveLength(4)
  })
})

describe('ChatPage Grok composer and per-agent threads', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('uses a pill composer with + operator menu and mic', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.getByRole('textbox', { name: 'Chat message' })).toHaveAttribute(
      'placeholder',
      'Message …',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    expect(screen.getByRole('menuitem', { name: 'Compact' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Blueprints' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Teams' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Settings' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open settings' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Edit agent' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()
    expect(screen.getByLabelText('Tokens in context')).toBeInTheDocument()
    expect(document.querySelector('.os-chat-header [data-avatar-theme="blobs"]')).toBeInTheDocument()
  })

  it('REQ-76: circular up-arrow send appears only while the field has text', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(screen.queryByRole('button', { name: /^Send$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add' })).toBeInTheDocument()

    fireEvent.change(composer, { target: { value: 'hi' } })
    const send = screen.getByRole('button', { name: /^Send$/i })
    expect(send).toBeEnabled()
    expect(send).toHaveClass('os-composer__send')
    expect(send.querySelector('svg')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()

    fireEvent.change(composer, { target: { value: '   ' } })
    expect(screen.queryByRole('button', { name: /^Send$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()

    fireEvent.change(composer, { target: { value: 'hi' } })
    expect(screen.getByRole('button', { name: /^Send$/i })).toBeInTheDocument()
    fireEvent.change(composer, { target: { value: '' } })
    expect(screen.queryByRole('button', { name: /^Send$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()

    fireEvent.change(composer, { target: { value: 'hi' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(composer).toHaveValue('')
    expect(screen.queryByRole('button', { name: /^Send$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Voice input' })).toBeInTheDocument()
  })

  it('ghosts composer shortcut chips until hover or focus, swapping Enter/Esc by draft', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(screen.queryByTestId('first-load-tips')).not.toBeInTheDocument()
    const sendHint = screen.getByTestId('composer-send-hint')
    expect(sendHint).toHaveClass('os-composer__hint')
    expect(composer.closest('.os-composer')).toContainElement(sendHint)

    fireEvent.focus(composer)
    expect(screen.getByTestId('composer-send-hint')).toBeInTheDocument()
    fireEvent.change(composer, { target: { value: 'draft' } })
    expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('composer-clear-hint')).toBeInTheDocument()

    fireEvent.change(composer, { target: { value: '' } })
    expect(screen.getByTestId('composer-send-hint')).toBeInTheDocument()
  })

  it('shows a Blobs header avatar by default and falls back to bland when opted in', async () => {
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const headerBlob = document.querySelector('.os-chat-header [data-avatar-theme="blobs"]')
    expect(headerBlob).toBeInTheDocument()
    expect(headerBlob).toHaveAttribute('data-eye-state', 'idle')

    act(() => {
      saveAvatarTheme('bland')
    })
    expect(document.querySelector('.os-chat-header [data-avatar-theme="blobs"]')).not.toBeInTheDocument()
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
  })

  it('shows Bee header avatars when the Bee theme is selected', async () => {
    saveAvatarTheme('bee')
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const headerBee = document.querySelector('.os-chat-header [data-avatar-theme="bee"]')
    expect(headerBee).toBeInTheDocument()
    expect(headerBee?.querySelector('[data-googly="true"]')).toBeTruthy()
    expect(['side-on', 'face-only']).toContain(
      headerBee?.querySelector('svg')?.getAttribute('data-bee-variant')
      || headerBee?.getAttribute('data-bee-variant'),
    )
    localStorage.removeItem(AVATAR_THEME_STORAGE_KEY)
  })

  it('opens a unique websocket thread per agent', async () => {
    const first = renderChat('/chat?blueprint=codey')
    expect(MockWebSocket.instances[0]?.url).toContain('/ws/ai-demo/')
    const codeyUrl = MockWebSocket.instances[0]!.url
    first.unmount()

    renderChat('/chat?blueprint=stewie')
    const stewieUrl = MockWebSocket.instances[MockWebSocket.instances.length - 1]!.url
    expect(stewieUrl).toContain('/ws/ai-demo/')
    expect(stewieUrl).not.toBe(codeyUrl)
  })

  it('opens the session id from ?session= without leaving Chat mounted', async () => {
    renderChat('/chat?blueprint=codey&session=sess-worker-2')
    expect(MockWebSocket.instances[0]?.url).toContain('/ws/ai-demo/sess-worker-2/')
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('renders a bordered Summary block after Compact (nested parent stays inside)', async () => {
    const compactPayload = {
      summary: {
        id: 2,
        conversation_id: 'c-compact',
        span: { start: 0, end: 1 },
        parent_summary_id: 1,
        body: 'outer digest',
        created_at: '2026-09-03T00:00:00Z',
        replaced_count: 2,
      },
      summaries: [
        {
          id: 1,
          conversation_id: 'c-compact',
          span: { start: 0, end: 1 },
          parent_summary_id: null,
          body: 'inner digest',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
        {
          id: 2,
          conversation_id: 'c-compact',
          span: { start: 0, end: 1 },
          parent_summary_id: 1,
          body: 'outer digest',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/chat/compact/') && init?.method === 'POST') {
          return {
            ok: true,
            status: 200,
            json: async () => compactPayload,
          } as Response
        }
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'jeeves',
              conversation_id: 'c-compact',
              messages: [
                { role: 'user', content: 'prior question' },
                { role: 'assistant', content: 'prior answer' },
              ],
              summaries: [],
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

    renderChat('/chat?blueprint=jeeves')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('prior question')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'Compact' }))
    })

    const blocks = await screen.findAllByTestId('chat-summary')
    expect(blocks.length).toBe(2)
    expect(blocks[0]).toHaveClass('chat-summary')
    expect(blocks[1]).toHaveClass('chat-summary')
    expect(blocks[1]).toHaveClass('chat-summary--nested')
    expect(screen.getAllByText('Summary').length).toBe(2)
    expect(screen.getByText('outer digest')).toBeInTheDocument()
    expect(screen.getByText('inner digest')).toBeInTheDocument()
    expect(screen.queryByText('prior question')).not.toBeInTheDocument()
  })
})

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

function stubTeamAndBlueprints() {
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
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
        }),
      } as Response
    }),
  )
}

describe('ChatPage remotes dropdown (REQ-59)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('lists only configured remotes plus Add remote on remote agents', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [
                { id: 'hermes', label: 'Hermes' },
                { id: 'omb', label: 'OpenMousBot' },
                { id: 'rakazo', label: 'Rakazo' },
              ],
              configured: [
                {
                  id: 'omb',
                  kind: 'omb',
                  label: 'OpenMousBot',
                  title: 'OpenMousBot',
                  host_label: '',
                  base_url: 'http://127.0.0.1:8802',
                  source: 'config',
                },
              ],
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
    renderChat('/chat?remote=omb')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const pill = await screen.findByTestId('routing-pill-agent')
    expect(screen.getByTestId('navbar-routing-picker')).toHaveAttribute('data-seat-kind', 'remote')
    expect(pill).toHaveAttribute('data-value', 'omb')
    fireEvent.click(pill)
    const menu = await screen.findByTestId('routing-menu-agent')
    const options = within(menu)
      .getAllByRole('menuitem')
      .map((opt) => opt.textContent)
    expect(options).toContain('OpenMousBot')
    expect(options).toContain('Add remote')
    expect(options).not.toContain('Hermes')
    expect(options).not.toContain('Rakazo')
    expect(options).not.toContain('OMB')
    expect(options).not.toContain('No remotes')
    expect(screen.getByTestId('navbar-routing-picker').textContent).not.toMatch(/\bOMB\b/)
  })

  it('shows the bound remote name for a remote agent (Issue #745)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [{ id: 'omb', label: 'OpenMousBot' }],
              configured: [
                {
                  id: 'omb',
                  kind: 'omb',
                  label: 'OpenMousBot',
                  title: 'OpenMousBot',
                  host_label: '',
                  base_url: 'http://127.0.0.1:8802',
                  source: 'config',
                },
              ],
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
    renderChat('/chat?remote=omb')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const pill = await screen.findByTestId('routing-pill-agent')
    expect(pill).toHaveAttribute('data-value', 'omb')
    fireEvent.click(pill)
    const menu = await screen.findByTestId('routing-menu-agent')
    expect(within(menu).getByRole('menuitem', { name: 'OpenMousBot' })).toBeInTheDocument()
    expect(within(menu).queryByRole('menuitem', { name: 'No remotes' })).not.toBeInTheDocument()
  })

  it('opens Add remote instead of No remotes chrome when none are configured', async () => {
    const opened: unknown[] = []
    const listener = (event: Event) => opened.push((event as CustomEvent).detail)
    window.addEventListener('swarm:open-settings', listener)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [{ id: 'omb', label: 'OpenMousBot' }],
              configured: [],
              data: [],
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
    renderChat('/chat?blueprint=starter-remote')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: 'Add remote' })).toBeInTheDocument()
    })
    expect(screen.queryByRole('combobox', { name: 'Remote' })).not.toBeInTheDocument()
    expect(screen.queryByText('No remotes')).not.toBeInTheDocument()
    expect(opened).toContainEqual({ section: 'remotes', addRemote: true })
    window.removeEventListener('swarm:open-settings', listener)
  })

  it('offers Pick a remote when remotes exist but the agent is unbound', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              kinds: [
                { id: 'hermes', label: 'Hermes' },
                { id: 'omb', label: 'OpenMousBot' },
              ],
              configured: [
                {
                  id: 'omb',
                  kind: 'omb',
                  label: 'OpenMousBot',
                  title: 'OpenMousBot',
                  host_label: '',
                  base_url: 'http://127.0.0.1:8802',
                  source: 'config',
                },
              ],
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
    renderChat('/chat?blueprint=starter-remote')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const pill = await screen.findByTestId('routing-pill-agent')
    expect(pill).toHaveTextContent('Pick a remote')
    fireEvent.click(pill)
    const menu = await screen.findByTestId('routing-menu-agent')
    const options = within(menu)
      .getAllByRole('menuitem')
      .map((opt) => opt.textContent)
    expect(options).toContain('OpenMousBot')
    expect(options).not.toContain('No remotes')
  })

  it('hides the Remotes control on local API and CLI agents', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          kinds: [{ id: 'omb', label: 'OpenMousBot' }],
          configured: [{ id: 'omb', kind: 'omb', label: 'OpenMousBot' }],
        }),
      } as Response),
    )
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByRole('combobox', { name: 'Remote' })).not.toBeInTheDocument()
  })

  it('hides the Remotes control on local teams', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'local-team',
                name: 'Local Team',
                members: [{ id: 'codey', kind: 'agent' }],
              },
            ],
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ data: [] }),
        } as Response
      }),
    )
    renderChat('/chat?team=local-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByRole('combobox', { name: 'Remote' })).not.toBeInTheDocument()
  })

  it('shows the Remotes control on remote-backed teams', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => [
              {
                id: 'remote-team',
                name: 'Remote Team',
                members: [{ id: 'omb-bot', kind: 'remote' }],
              },
            ],
          } as Response
        }
        if (url.includes('/v1/remotes')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              kinds: [{ id: 'omb', label: 'OpenMousBot' }],
              configured: [{ id: 'omb', kind: 'omb', label: 'OpenMousBot' }],
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
    renderChat('/chat?team=remote-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByTestId('navbar-routing-picker')).toHaveAttribute(
      'data-seat-kind',
      'remote',
    )
  })
})

describe('ChatPage team member dropdown', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubTeamAndBlueprints()
  })

  afterEach(() => {
    clearAllQueuedSends()
    vi.unstubAllGlobals()
  })

  it('lists All members first, then name + kind/role, then Manage Teams (unlabeled)', async () => {
    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const select = await screen.findByRole('combobox', { name: 'Team members' })
    expect(select).not.toHaveAccessibleName('Blueprint')
    const options = within(select).getAllByRole('option')
    expect(options.map((opt) => opt.textContent)).toEqual([
      'All members',
      'Codey (agent/coder)',
      'Stewie (agent/ops)',
      'Manage Team',
    ])
    expect(select).toHaveValue('codey') // #169: seat default = first roster member
    expect(screen.queryByText('Blueprint')).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Demo Team' })).toBeInTheDocument()
  })

  it('shows Mode A kind-clear names in the team chat header dropdown', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [
                {
                  id: 'demo-harness-kinds',
                  object: 'team_roster',
                  name: 'Demo Harness Kinds',
                  members: [
                    { id: 'grok-cli', name: 'Grok CLI', kind: 'cli', role: 'default' },
                    { id: 'litellm-api', name: 'LiteLLM API', kind: 'api', role: 'default' },
                    { id: 'openmousbot-remote', name: 'OpenMousBot Remote', kind: 'remote', role: 'default' },
                  ],
                },
              ],
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
    renderChat('/chat?team=demo-harness-kinds')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByRole('heading', { name: 'Demo Harness Kinds' })).toBeInTheDocument()
    const select = await screen.findByRole('combobox', { name: 'Team members' })
    const options = within(select).getAllByRole('option').map((opt) => opt.textContent)
    expect(options).toEqual([
      'All members',
      'Grok CLI (cli/default)',
      'LiteLLM API (api/default)',
      'OpenMousBot Remote (remote/default)',
      'Manage Team',
    ])
    expect(options.join(' ')).not.toMatch(/\bOMB\b/)
  })

  it('sends params {team, target} for all-members and a chosen member', async () => {
    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    // #169: the dropdown now defaults to the first member; go explicit for the all-members frame.
    fireEvent.change(screen.getByRole('combobox', { name: 'Team members' }), {
      target: { value: 'all' },
    })
    fireEvent.change(composer, { target: { value: 'hello team' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toEqual({
      message: 'hello team',
      params: { team: 'demo-team', target: 'all', enabled_tools: [] },
    })

    fireEvent.change(screen.getByRole('combobox', { name: 'Team members' }), {
      target: { value: 'codey' },
    })
    fireEvent.change(composer, { target: { value: 'just codey' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    // REQ-171A-3 / #603: second Send while awaitingAssistant is queued
    // (REQ-90 / #447 pane), not a racing second {message}. Drain after
    // the first assistant final so the member target still goes on the wire.
    const queued = await screen.findByTestId('queued-row')
    expect(queued).toHaveTextContent('just codey')
    expect(
      ws.send.mock.calls
        .map((call) => JSON.parse(String(call[0])))
        .filter((frame) => frame.message && frame.type !== 'status'),
    ).toHaveLength(1)

    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-team1" class="assistant-message"></div></div>',
        }),
      )
    })
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-response-team1" class="assistant-message" hx-swap-oob="true">ack</div>',
        }),
      )
    })

    await waitFor(() => {
      const userFrames = ws.send.mock.calls
        .map((call) => JSON.parse(String(call[0])))
        .filter((frame) => frame.message && frame.type !== 'status')
      expect(userFrames).toHaveLength(2)
      expect(userFrames[1]).toEqual({
        message: 'just codey',
        params: { team: 'demo-team', target: 'codey', enabled_tools: [] },
      })
    })
  })

  it('keeps Manage Team last with separator and does not send when that item is chosen', async () => {
    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const select = await screen.findByRole('combobox', { name: 'Team members' })
    const options = within(select).getAllByRole('option')
    expect(options[options.length - 1]).toHaveValue('__manage__')
    expect(options[options.length - 1]).toHaveTextContent('Manage Team')
    const allOptions = Array.from(select.querySelectorAll('option'))
    expect(allOptions[allOptions.length - 2]).toBeDisabled()
    expect(select).toHaveValue('codey') // #169: seat default = first roster member
    expect(MockWebSocket.instances[0]!.send).not.toHaveBeenCalled()
  })

  it('REQ-23 #331 & REQ-152: Manage Team navigates to /teams/#team_id and does not WS-send', async () => {
    const assign = vi.fn()
    vi.stubGlobal('location', { ...window.location, assign })

    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    fireEvent.change(await screen.findByRole('combobox', { name: 'Team members' }), {
      target: { value: '__manage__' },
    })
    expect(assign).toHaveBeenCalledWith('/teams/#demo-team')
    expect(MockWebSocket.instances[0]!.send).not.toHaveBeenCalled()
  })
})

function SearchProbe() {
  const [params] = useSearchParams()
  return <div data-testid="search-probe">{params.toString()}</div>
}

function renderSwitchableChat(initialEntry = '/chat?blueprint=codey') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <nav>
            <Link to="/chat?blueprint=codey">Go Codey</Link>
            <Link to="/chat?blueprint=stewie">Go Stewie</Link>
          </nav>
          <SearchProbe />
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage per-agent thread switch (REQ-14 #319)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          const agent = new URL(url, 'http://localhost').searchParams.get('agent')
          if (agent === 'codey') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: 'codey',
                conversation_id: 'agt-codey',
                messages: [
                  { role: 'user', content: 'prior question A' },
                  { role: 'assistant', content: 'prior answer A' },
                ],
              }),
            } as Response
          }
          if (agent === 'stewie') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: 'stewie',
                conversation_id: 'agt-stewie',
                messages: [
                  { role: 'user', content: 'prior question B' },
                  { role: 'assistant', content: 'prior answer B' },
                ],
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ agent_id: agent, messages: [], summaries: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              { id: 'codey', name: 'Codey', description: 'Code assistant' },
              { id: 'stewie', name: 'Stewie', description: 'Helpful agent' },
            ],
          }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('rehydrates a distinct persisted thread when the rail switches agents', async () => {
    renderSwitchableChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('prior question A')).toBeInTheDocument()
    expect(screen.getByText('prior answer A')).toBeInTheDocument()
    expect(screen.queryByText('prior question B')).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('link', { name: 'Go Stewie' }))
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    expect(await screen.findByText('prior question B')).toBeInTheDocument()
    expect(screen.queryByText('prior question A')).not.toBeInTheDocument()
    expect(screen.getByTestId('search-probe')).toHaveTextContent('blueprint=stewie')

    fireEvent.click(screen.getByRole('link', { name: 'Go Codey' }))
    expect(await screen.findByText('prior question A')).toBeInTheDocument()
    expect(screen.queryByText('prior question B')).not.toBeInTheDocument()

    const threadCalls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes('/chat/thread/'))
    expect(threadCalls.some((url) => url.includes('agent=codey'))).toBe(true)
    expect(threadCalls.some((url) => url.includes('agent=stewie'))).toBe(true)
  })
})

describe('ChatPage selected session persist (#794)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          const cid = new URL(url, 'http://localhost').searchParams.get('conversation_id')
          if (cid === 'sess-notes') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: 'codey',
                conversation_id: 'sess-notes',
                session_title: 'Notes',
                messages: [
                  { role: 'user', content: 'notes from A' },
                  { role: 'assistant', content: 'reply A' },
                ],
              }),
            } as Response
          }
          if (cid === 'sess-old') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: 'codey',
                conversation_id: 'sess-old',
                messages: [
                  { role: 'user', content: 'older session' },
                  { role: 'assistant', content: 'old reply' },
                ],
              }),
            } as Response
          }
          if (cid === 'sess-gone' || cid === 'cli-cli_agent-gone') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: cid?.startsWith('cli-') ? 'cli_agent' : 'codey',
                conversation_id: cid,
                session_missing: true,
                messages: [],
              }),
            } as Response
          }
          if (cid === 'cli-cli_agent-abc') {
            return {
              ok: true,
              status: 200,
              json: async () => ({
                agent_id: 'cli_agent',
                conversation_id: 'cli-cli_agent-abc',
                messages: [
                  { role: 'status', content: 'Switched to grok session sid-1.' },
                  { role: 'user', content: 'from cli A' },
                ],
              }),
            } as Response
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({ agent_id: 'codey', conversation_id: cid, messages: [] }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              { id: 'codey', name: 'Codey', description: 'Code assistant' },
              { id: 'cli_agent', name: 'CLI Agent', description: 'CLI' },
            ],
          }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('rehydrates the selected Django session after unmount without ?session=', async () => {
    const { setConversationIdForAgent } = await import('../../lib/agentChat')
    setConversationIdForAgent('codey', 'sess-old')
    const first = renderChat('/chat?blueprint=codey&session=sess-notes')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('notes from A')).toBeInTheDocument()
    expect(screen.queryByText('older session')).not.toBeInTheDocument()
    first.unmount()

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })
    expect(await screen.findByText('notes from A')).toBeInTheDocument()
    expect(screen.queryByText('older session')).not.toBeInTheDocument()
    const threadCalls = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls
      .map(([input]) => String(input))
      .filter((url) => url.includes('/chat/thread/'))
    expect(threadCalls.some((url) => url.includes('conversation_id=sess-notes'))).toBe(true)
  })

  it('rehydrates the selected CLI conversation after unmount without ?session=', async () => {
    const { setConversationIdForAgent } = await import('../../lib/agentChat')
    setConversationIdForAgent('cli_agent', 'cli-cli_agent-abc')
    const first = renderChat('/chat?blueprint=cli_agent&session=cli-cli_agent-abc')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('from cli A')).toBeInTheDocument()
    first.unmount()

    renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })
    expect(await screen.findByText('from cli A')).toBeInTheDocument()
  })

  it('shows honest status when the stored session is gone — no older transcript', async () => {
    const { setConversationIdForAgent } = await import('../../lib/agentChat')
    setConversationIdForAgent('codey', 'sess-gone')
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByTestId('chat-status')).toHaveTextContent(
      'Stored session sess-gone is gone',
    )
    expect(screen.queryByText('older session')).not.toBeInTheDocument()
    expect(screen.queryByText('notes from A')).not.toBeInTheDocument()
  })
})

describe('ChatPage Support default URL (REQ-5c #322)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('canonicalizes a missing blueprint onto Support without clobbering ?team=', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat']}>
            <SearchProbe />
            <Routes>
              <Route path="/chat" element={<ChatPage />} />
            </Routes>
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('search-probe')).toHaveTextContent('blueprint=support')
    })
    expect(await screen.findByRole('heading', { name: 'Support' })).toBeInTheDocument()
  })
})

describe('ChatPage Compact empty/failure toasts (REQ-37 #365)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('toasts Nothing to compact yet on an empty thread', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'Compact' }))
    })
    expect(await screen.findByText('Nothing to compact yet.')).toBeInTheDocument()
  })

  it('toasts Compact failed when POST /chat/compact/ errors', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/chat/compact/') && init?.method === 'POST') {
          return {
            ok: false,
            status: 500,
            json: async () => ({ error: 'boom' }),
          } as Response
        }
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'codey',
              conversation_id: 'c-fail',
              messages: [
                { role: 'user', content: 'prior question' },
                { role: 'assistant', content: 'prior answer' },
              ],
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
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('prior question')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'Compact' }))
    })
    expect(await screen.findByText('Compact failed')).toBeInTheDocument()
    expect(screen.getByText(/boom/i)).toBeInTheDocument()
  })

  it('drops the token meter after Compact replaces raw turns with a short summary', async () => {
    const compactPayload = {
      summary: {
        id: 1,
        conversation_id: 'c-meter',
        span: { start: 0, end: 1 },
        parent_summary_id: null,
        body: 'short',
        created_at: '2026-09-03T00:00:00Z',
        replaced_count: 2,
      },
      summaries: [
        {
          id: 1,
          conversation_id: 'c-meter',
          span: { start: 0, end: 1 },
          parent_summary_id: null,
          body: 'short',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
      ],
    }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/chat/compact/') && init?.method === 'POST') {
          return {
            ok: true,
            status: 200,
            json: async () => compactPayload,
          } as Response
        }
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'codey',
              conversation_id: 'c-meter',
              messages: [
                { role: 'user', content: 'aaaaaaaaaaaaaaaa' },
                { role: 'assistant', content: 'bbbbbbbbbbbbbbbb' },
              ],
              summaries: [],
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

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('aaaaaaaaaaaaaaaa')).toBeInTheDocument()
    const meter = screen.getByRole('meter', { name: 'Tokens in context' })
    const before = Number(meter.getAttribute('aria-valuenow'))
    expect(before).toBeGreaterThan(0)

    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await act(async () => {
      fireEvent.click(screen.getByRole('menuitem', { name: 'Compact' }))
    })
    await screen.findByTestId('chat-summary')
    expect(Number(meter.getAttribute('aria-valuenow'))).toBeLessThan(before)
  })

  it('hover Compress to here posts a span ending at that message', async () => {
    const compactPayload = {
      summary: {
        id: 1,
        conversation_id: 'c-here',
        span: { start: 0, end: 1 },
        parent_summary_id: null,
        body: 'early digest',
        created_at: '2026-09-03T00:00:00Z',
        replaced_count: 2,
      },
      summaries: [
        {
          id: 1,
          conversation_id: 'c-here',
          span: { start: 0, end: 1 },
          parent_summary_id: null,
          body: 'early digest',
          created_at: '2026-09-03T00:00:00Z',
          replaced_count: 2,
        },
      ],
    }
    const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/chat/compact/') && init?.method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => compactPayload,
        } as Response
      }
      if (url.includes('/chat/thread/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            agent_id: 'codey',
            conversation_id: 'c-here',
            messages: [
              { role: 'user', content: 'first question' },
              { role: 'assistant', content: 'first answer' },
              { role: 'user', content: 'later stays raw' },
            ],
            summaries: [],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText('first answer')).toBeInTheDocument()
    const buttons = screen.getAllByRole('button', { name: 'Compress to here' })
    expect(buttons.length).toBeGreaterThan(0)
    await act(async () => {
      fireEvent.click(buttons[1])
    })
    await screen.findByTestId('chat-summary')
    const compactCall = fetchMock.mock.calls.find(
      (entry) => String(entry[0]).includes('/chat/compact/') && entry[1]?.method === 'POST',
    )
    expect(compactCall).toBeTruthy()
    const posted = JSON.parse(String(compactCall?.[1]?.body || '{}'))
    expect(posted.span_start).toBe(0)
    expect(posted.span_end).toBe(1)
    expect(screen.getByText('later stays raw')).toBeInTheDocument()
  })

  it('opens session token diagnostics popup when clicking token meter (REQ-115)', async () => {
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const meterBtn = screen.getByRole('button', { name: 'Session token usage' })
    expect(meterBtn).toBeInTheDocument()

    fireEvent.click(meterBtn)

    expect(await screen.findByTestId('token-diagnostics-modal')).toBeInTheDocument()
    expect(screen.getByText('Session Token Diagnostics')).toBeInTheDocument()
  })

  it('displays token meter button for API agents and not for CLI or remote agents', async () => {
    const { unmount: unmountApi } = renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.getByTestId('token-meter-button')).toBeInTheDocument()
    unmountApi()

    MockWebSocket.instances = []
    const { unmount: unmountCli } = renderChat('/chat?blueprint=cli_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByTestId('token-meter-button')).toBeNull()
    unmountCli()

    MockWebSocket.instances = []
    const { unmount: unmountRemote } = renderChat('/chat?remote=hermes')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByTestId('token-meter-button')).toBeNull()
    unmountRemote()
  })
})

const REMOTE_ROSTER = {
  object: 'list',
  data: [
    {
      id: 'harness-team',
      object: 'team_roster',
      name: 'Harness Team',
      description: 'Remotes as Team members',
      members: [
        { id: 'hermes', name: 'Hermes', kind: 'remote', role: 'default' },
        { id: 'omb', name: 'OpenMousBot', kind: 'remote', role: 'default' },
        { id: 'rakazo', name: 'Rakazo', kind: 'remote', role: 'default' },
      ],
    },
  ],
}

describe('ChatPage remote members (PR #318 / REQ-23)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => REMOTE_ROSTER,
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ data: [] }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('lists configured remotes as kind=remote in the unlabeled member dropdown', async () => {
    renderChat('/chat?team=harness-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const select = await screen.findByRole('combobox', { name: 'Team members' })
    expect(within(select).getAllByRole('option').map((opt) => opt.textContent)).toEqual([
      'All members',
      'Hermes (remote/default)',
      'OpenMousBot (remote/default)',
      'Rakazo (remote/default)',
      'Manage Team',
    ])
    expect(screen.getByRole('heading', { name: 'Harness Team' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('sends params {team, target} for a remote member', async () => {
    renderChat('/chat?team=harness-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(screen.getByRole('combobox', { name: 'Team members' }), {
      target: { value: 'hermes' },
    })
    fireEvent.change(composer, { target: { value: 'ping hermes' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toEqual({
      message: 'ping hermes',
      params: { team: 'harness-team', target: 'hermes', enabled_tools: [] },
    })
  })
})

describe('ChatPage voice input stub (PR #322 / REQ-77)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('toasts when SpeechRecognition is missing — no live mic / LAN', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Voice input' }))
    expect(await screen.findByText(/Speech recognition is not available/i)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Send' })).not.toBeInTheDocument()
  })

  it('system STT inserts transcript into the composer and does not auto-send', async () => {
    class FakeRec {
      onresult: ((event: { results: Array<Array<{ transcript: string }>> }) => void) | null = null
      onend: (() => void) | null = null
      start() {
        queueMicrotask(() => {
          this.onresult?.({ results: [[{ transcript: 'hello from mic' }]] })
          this.onend?.()
        })
      }
      stop() {
        this.onend?.()
      }
    }
    vi.stubGlobal('SpeechRecognition', FakeRec)
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(screen.getByRole('button', { name: 'Voice input' }))
    expect(await screen.findByDisplayValue('hello from mic')).toBeInTheDocument()
    expect(await screen.findByTestId('stt-path')).toHaveTextContent(/system/i)
    expect(screen.getByRole('button', { name: 'Send' })).toBeInTheDocument()
    const ws = MockWebSocket.instances[0]!
    expect(ws.send).not.toHaveBeenCalled()
  })
})

describe('ChatPage Safety tool popups (REQ-55)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    window.localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [{ id: 'codey', name: 'Codey' }] }),
      } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  async function openAndStart() {
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const ws = MockWebSocket.instances[0]!
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-tool1" class="assistant-message"></div></div>',
        }),
      )
    })
    return ws
  }

  it('shows blue running, green done, and red denied badges', async () => {
    const ws = await openAndStart()
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'tool_status',
            id: 'c1',
            name: 'read_file',
            status: 'running',
          }),
        }),
      )
    })
    expect(screen.getByTestId('tool-status-badge')).toHaveAttribute('data-status', 'running')
    expect(screen.getByText('read_file')).toBeInTheDocument()

    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'tool_status',
            id: 'c1',
            name: 'read_file',
            status: 'done',
          }),
        }),
      )
    })
    expect(screen.getByTestId('tool-status-badge')).toHaveAttribute('data-status', 'done')

    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'tool_status',
            id: 'c2',
            name: 'wipe',
            status: 'denied',
          }),
        }),
      )
    })
    const badges = screen.getAllByTestId('tool-status-badge')
    expect(badges.some((el) => el.getAttribute('data-status') === 'denied')).toBe(true)
  })

  it('prompts on concern and Always allow skips the next prompt for that tool', async () => {
    const ws = await openAndStart()
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'tool_approval',
            id: 'ap1',
            name: 'write_file',
            agent_id: 'codey',
          }),
        }),
      )
    })
    expect(screen.getByRole('dialog', { name: 'Safety approval' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Always allow' }))
    expect(JSON.parse(String(ws.send.mock.calls.at(-1)?.[0]))).toEqual({
      type: 'tool_decision',
      id: 'ap1',
      decision: 'always',
    })
    expect(screen.queryByRole('dialog', { name: 'Safety approval' })).not.toBeInTheDocument()

    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({
            type: 'tool_approval',
            id: 'ap2',
            name: 'write_file',
            agent_id: 'codey',
          }),
        }),
      )
    })
    expect(screen.queryByRole('dialog', { name: 'Safety approval' })).not.toBeInTheDocument()
    expect(JSON.parse(String(ws.send.mock.calls.at(-1)?.[0]))).toEqual({
      type: 'tool_decision',
      id: 'ap2',
      decision: 'always',
    })
  })
})

function mockChatFetches(options: {
  blueprint: string
  name: string
  kind?: 'api' | 'cli' | 'remote'
  messages: { role: 'user' | 'assistant'; content: string; edited?: boolean }[]
}) {
  const kind = options.kind ?? 'api'
  return vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    if (url.includes('/chat/thread/') && (init?.method === 'PATCH' || init?.method === 'patch')) {
      const body = init?.body ? JSON.parse(String(init.body)) : {}
      const messages = options.messages.map((message, index) =>
        index === body.index
          ? { ...message, content: body.content, edited: true }
          : message,
      )
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: options.blueprint,
          conversation_id: `agt-1-${options.blueprint}`,
          kind,
          editable: kind === 'api',
          messages,
        }),
      } as Response
    }
    if (url.includes('/chat/thread/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: options.blueprint,
          conversation_id: `agt-1-${options.blueprint}`,
          kind,
          editable: kind === 'api',
          messages: options.messages,
        }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: [{ id: options.blueprint, name: options.name, description: options.name }],
      }),
    } as Response
  })
}

describe('ChatPage REQ-49 message edit (API vs CLI/remote)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('API fixture chat shows edit on user and assistant; save is what the next send includes', async () => {
    const fetchMock = mockChatFetches({
      blueprint: 'jeeves',
      name: 'Jeeves',
      kind: 'api',
      messages: [
        { role: 'user', content: 'prior question' },
        { role: 'assistant', content: 'prior answer' },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)

    renderChat('/chat?blueprint=jeeves')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('prior question')).toBeInTheDocument()
    expect(screen.getByText('prior answer')).toBeInTheDocument()
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-agent-kind',
      'api',
    )
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-messages-editable',
      'true',
    )

    const editButtons = screen.getAllByRole('button', { name: 'Edit message' })
    expect(editButtons).toHaveLength(2)

    fireEvent.click(editButtons[0])
    const editor = await screen.findByRole('textbox', { name: 'Edit message' })
    fireEvent.change(editor, { target: { value: 'engineered question' } })
    fireEvent.click(screen.getByRole('button', { name: 'Save' }))

    await waitFor(() => {
      expect(screen.getByText('engineered question')).toBeInTheDocument()
    })
    expect(screen.getByTestId('edited-hint')).toBeInTheDocument()

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        (call) =>
          String(call[0]).includes('/chat/thread/') &&
          String(call[1]?.method || '').toUpperCase() === 'PATCH',
      )
      expect(patchCall).toBeTruthy()
      expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual(
        expect.objectContaining({ index: 0, content: 'engineered question' }),
      )
    })

    const ws = MockWebSocket.instances[0]!
    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({ edit: { index: 0, content: 'engineered question' } }),
    )

    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'follow up' } })
    fireEvent.submit(composer.closest('form')!)
    expect(ws.send).toHaveBeenCalledWith(
      JSON.stringify({
        message: 'follow up',
        blueprint: 'jeeves',
        params: { enabled_tools: [] },
      }),
    )
  })

  it('clicking an API bubble enters edit mode', async () => {
    vi.stubGlobal(
      'fetch',
      mockChatFetches({
        blueprint: 'jeeves',
        name: 'Jeeves',
        messages: [
          { role: 'user', content: 'click me' },
          { role: 'assistant', content: 'assistant bubble' },
        ],
      }),
    )

    renderChat('/chat?blueprint=jeeves')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('assistant bubble')).toBeInTheDocument()
    const bubbles = screen.getAllByTestId('chat-bubble')
    fireEvent.click(bubbles[1])
    expect(await screen.findByRole('textbox', { name: 'Edit message' })).toHaveValue(
      'assistant bubble',
    )
  })

  it('CLI fixture chat has no edit control and no click-to-edit', async () => {
    vi.stubGlobal(
      'fetch',
      mockChatFetches({
        blueprint: 'cli:grok',
        name: 'Grok CLI',
        kind: 'cli',
        messages: [
          { role: 'user', content: 'cli user' },
          { role: 'assistant', content: 'cli assistant' },
        ],
      }),
    )

    renderChat('/chat?blueprint=cli:grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('cli user')).toBeInTheDocument()
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-agent-kind',
      'cli',
    )
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-messages-editable',
      'false',
    )
    expect(screen.queryByRole('button', { name: 'Edit message' })).not.toBeInTheDocument()

    fireEvent.click(screen.getAllByTestId('chat-bubble')[0])
    expect(screen.queryByRole('textbox', { name: 'Edit message' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Save' })).not.toBeInTheDocument()
  })

  it('remote fixture chat has no edit control and no click-to-edit', async () => {
    vi.stubGlobal(
      'fetch',
      mockChatFetches({
        blueprint: 'remote:acp',
        name: 'Remote ACP',
        kind: 'remote',
        messages: [
          { role: 'user', content: 'remote user' },
          { role: 'assistant', content: 'remote assistant' },
        ],
      }),
    )

    renderChat('/chat?blueprint=remote:acp')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByText('remote user')).toBeInTheDocument()
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-agent-kind',
      'remote',
    )
    expect(screen.queryByRole('button', { name: 'Edit message' })).not.toBeInTheDocument()
    fireEvent.click(screen.getAllByTestId('chat-bubble')[1])
    expect(screen.queryByRole('textbox', { name: 'Edit message' })).not.toBeInTheDocument()
  })
})

describe('ChatPage dropdown status lines (REQ-46)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  function stubWithThreadStore(store: { messages: { role: string; content: string }[] }) {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          if (init?.method === 'POST') {
            const body = JSON.parse(String(init.body || '{}')) as {
              message?: { role?: string; content?: string }
            }
            if (body.message?.role && body.message.content) {
              store.messages.push({
                role: body.message.role,
                content: body.message.content,
              })
            }
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'team-demo-team',
              conversation_id: 'team-demo-team',
              messages: store.messages,
            }),
          } as Response
        }
        if (url.includes('team_rosters') || url.includes('team-rosters')) {
          return {
            ok: true,
            status: 200,
            json: async () => DEMO_ROSTER,
          } as Response
        }
        if (url.includes('/v1/cli-sessions/hop')) {
          const body = JSON.parse(String(init?.body || '{}')) as {
            from_cli?: string
            to_cli?: string
          }
          const fromCli = body.from_cli || 'antigravity'
          const toCli = body.to_cli || 'grok'
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'cli_session_hop',
              agent_id: 'cli_agent',
              conversation_id: 'thread-1',
              from_cli: fromCli,
              to_cli: toCli,
              kind: 'cli',
              cli_session_id: null,
              mode: 'summary',
              tokens: 12,
              token_budget: 4000,
              omitted: ['secrets', 'tool_noise'],
              empty: false,
              status: `Carried summary context from ${fromCli} → ${toCli} (12 tokens).`,
              export_warning: null,
              import: 'swarm',
              injection: { text: 'seed', mode: 'summary', tokens: 12, empty: false },
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: ['antigravity', 'grok'],
              configured: ['antigravity', 'grok'],
              discovered: ['grok'],
            }),
          } as Response
        }
        if (url.includes('/v1/models')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [
                { id: 'gpt-4', object: 'model', created: 0, owned_by: 'openai' },
                { id: 'grok-4', object: 'model', created: 0, owned_by: 'xai' },
              ],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
          }),
        } as Response
      }),
    )
  }

  it('appends one team-target status event that is not a bubble and survives reload', async () => {
    const store = { messages: [] as { role: string; content: string }[] }
    stubWithThreadStore(store)

    const first = renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    fireEvent.change(await screen.findByRole('combobox', { name: 'Team members' }), {
      target: { value: 'stewie' },
    })

    const status = await screen.findByTestId('chat-status')
    expect(status).toHaveTextContent('Team target: Codey (agent/coder) → Stewie (agent/ops)')
    expect(status).toHaveClass('os-chat-status')
    expect(status.className).not.toMatch(/chat-start|chat-end/)
    expect(status.querySelector('.chat-bubble')).toBeNull()
    expect(screen.getAllByTestId('chat-status')).toHaveLength(1)
    expect(store.messages).toHaveLength(1)
    expect(store.messages[0]).toEqual({
      role: 'status',
      content: 'Team target: Codey (agent/coder) → Stewie (agent/ops)',
    })

    first.unmount()
    renderChat('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    const restored = await screen.findByTestId('chat-status')
    expect(restored).toHaveTextContent('Team target: Codey (agent/coder) → Stewie (agent/ops)')
    expect(restored.className).not.toMatch(/chat-start|chat-end/)
    expect(screen.getAllByTestId('chat-status')).toHaveLength(1)
  })

  it('appends one CLI status event (antigravity → grok) that is not a bubble', async () => {
    const store = { messages: [] as { role: string; content: string }[] }
    stubWithThreadStore(store)

    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=antigravity')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const cliPill = await screen.findByTestId('routing-pill-agent')
    fireEvent.click(cliPill)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'grok' }))

    const statuses = await screen.findAllByTestId('chat-status')
    expect(statuses[0]).toHaveTextContent('CLI: antigravity → grok')
    expect(statuses[0].className).not.toMatch(/chat-start|chat-end/)
    expect(statuses[0].querySelector('.chat-bubble')).toBeNull()
    const carried = await screen.findByText(/Carried summary context from antigravity → grok/)
    expect(carried.closest('[data-testid="chat-status"]')).toHaveClass('os-chat-status')
    expect(carried.closest('[data-testid="chat-status"]')?.className).not.toMatch(
      /chat-start|chat-end/,
    )
    expect(screen.getAllByTestId('chat-status').length).toBeGreaterThanOrEqual(2)
  })

  it('renders one CLI routing picker and hides API and Remotes controls (REQ-133 / REQ-200)', async () => {
    const store = { messages: [] as { role: string; content: string }[] }
    stubWithThreadStore(store)

    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=antigravity')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByTestId('navbar-routing-picker')).toBeInTheDocument()
    expect(screen.getAllByTestId('navbar-routing-picker')).toHaveLength(1)
    expect(screen.getByTestId('routing-pill-agent')).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'CLI' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Model' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'API' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Remote' })).not.toBeInTheDocument()
  })

  it('does not render mystery API/Model dropdowns on API agents in navbar (REQ-186)', async () => {
    const store = { messages: [] as { role: string; content: string }[] }
    stubWithThreadStore(store)

    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.queryByRole('combobox', { name: 'API' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Model' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'CLI' })).not.toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Remote' })).not.toBeInTheDocument()
  })
})

describe('ChatPage per-agent dropdown persist (REQ-180)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  function stubCliChat() {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/cli-agents/') && url.includes('/models')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ cli: 'antigravity', models: ['default', 'grok-4'] }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: ['grok', 'antigravity'],
              installed: ['grok', 'antigravity'],
              configured: ['grok', 'antigravity'],
            }),
          } as Response
        }
        if (url.includes('/v1/preferences')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'user_preferences',
              empty: true,
              favourites: [],
              hidden_agents: [],
              hostname_override: '',
              values: {},
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
            messages: [],
          }),
        } as Response
      }),
    )
  }

  it('keeps CLI + model after reload and uses them on the next send', async () => {
    stubCliChat()

    const first = renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const cliPill = await screen.findByTestId('routing-pill-agent')
    fireEvent.click(cliPill)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'antigravity' }))
    const modelPill = await screen.findByTestId('routing-pill-model')
    fireEvent.click(modelPill)
    fireEvent.click(await screen.findByRole('menuitem', { name: 'grok-4' }))
    expect(screen.getByTestId('routing-pill-agent')).toHaveAttribute('data-value', 'antigravity')
    expect(screen.getByTestId('routing-pill-model')).toHaveAttribute('data-value', 'grok-4')

    first.unmount()
    renderChat('/chat?blueprint=cli_agent&mode=cli')
    await act(async () => {
      MockWebSocket.instances[MockWebSocket.instances.length - 1]?.open()
    })

    const restoredCli = await screen.findByTestId('routing-pill-agent')
    const restoredModel = await screen.findByTestId('routing-pill-model')
    await waitFor(() => {
      expect(restoredCli).toHaveAttribute('data-value', 'antigravity')
      expect(restoredModel).toHaveAttribute('data-value', 'grok-4')
    })

    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'run with saved pin' } })
    fireEvent.submit(composer.closest('form')!)
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
    const sent = JSON.parse(ws.send.mock.calls[0][0] as string)
    expect(sent.message).toBe('run with saved pin')
    expect(sent.blueprint).toBe('cli_agent')
    expect(sent.params).toMatchObject({ cli: 'antigravity', model: 'grok-4' })
  })
})

describe('ChatPage cascading navbar picker (REQ-200)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('shows three pills and records an effort-only status line', async () => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    const store = { messages: [] as { role: string; content: string }[] }
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          if (url.includes('?') === false && store.messages.length) {
            /* keep */
          }
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'cli_agent',
              conversation_id: 'cli_agent',
              messages: store.messages,
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents/') && url.includes('/models')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              cli: 'agy',
              models: ['gemini-3.8-flash-high', 'gemini-3.8-flash-medium', 'claude-sonnet-4-6'],
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: ['agy', 'grok'],
              installed: ['agy', 'grok'],
              configured: ['agy', 'grok'],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
            messages: [],
          }),
        } as Response
      }),
    )

    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=agy&model=gemini-3.8-flash-medium')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(await screen.findByTestId('navbar-routing-picker')).toBeInTheDocument()
    expect(screen.getAllByTestId('navbar-routing-picker')).toHaveLength(1)
    expect(screen.getByTestId('routing-face')).toHaveAttribute(
      'title',
      'agy / gemini-3.8-flash / medium',
    )
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent('agy')
    expect(screen.getByTestId('routing-pill-model')).toHaveTextContent('gemini-3.8-flash')
    expect(screen.getByTestId('routing-pill-effort')).toHaveTextContent('medium')

    fireEvent.click(screen.getByTestId('routing-pill-effort'))
    fireEvent.click(await screen.findByRole('menuitem', { name: 'high' }))
    const status = await screen.findByTestId('chat-status')
    expect(status).toHaveTextContent('Effort: medium → high')
    expect(status.className).not.toMatch(/chat-start|chat-end/)
    expect(screen.getByTestId('routing-pill-agent')).toHaveAttribute('data-value', 'agy')
    expect(screen.getByTestId('routing-pill-model')).toHaveAttribute('data-value', 'gemini-3.8-flash')
    expect(screen.getByTestId('routing-pill-effort')).toHaveAttribute('data-value', 'high')
  })
})


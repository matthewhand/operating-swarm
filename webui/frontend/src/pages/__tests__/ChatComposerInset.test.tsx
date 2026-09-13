import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'
import { COMPOSER_INSET_VAR } from '../../lib/composerInset'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  url: string

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send() {}
  close() {}

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

let dockHeight = 72
const resizeObservers: ResizeObserverCallback[] = []

function fireResizeObservers() {
  resizeObservers.forEach((cb) => {
    cb([], {} as ResizeObserver)
  })
}

class MockResizeObserver {
  constructor(cb: ResizeObserverCallback) {
    resizeObservers.push(cb)
  }
  observe() {
    fireResizeObservers()
  }
  unobserve() {}
  disconnect() {}
}

function mockDockRect() {
  const original = HTMLElement.prototype.getBoundingClientRect
  HTMLElement.prototype.getBoundingClientRect = function () {
    if (this.getAttribute('data-testid') === 'chat-bottom-dock') {
      return {
        x: 0,
        y: 520,
        top: 520,
        left: 0,
        right: 400,
        bottom: 520 + dockHeight,
        width: 400,
        height: dockHeight,
        toJSON: () => ({}),
      } as DOMRect
    }
    return original.call(this)
  }
  return () => {
    HTMLElement.prototype.getBoundingClientRect = original
  }
}

function renderChat() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=support']}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function deliverTurn(ws: MockWebSocket, text: string, id: string) {
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div class="user-message">${text}?</div></div>`,
    }),
  )
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`,
    }),
  )
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${text}</div>`,
    }),
  )
}

async function openAndStream(count = 1) {
  const ws = MockWebSocket.instances[0]
  expect(ws).toBeDefined()
  await act(async () => {
    ws.open()
  })
  await act(async () => {
    for (let i = 0; i < count; i += 1) {
      deliverTurn(ws, `Transcript line ${i + 1}`, `message-response-inset-${i}`)
    }
  })
  return ws
}

describe('REQ #743: chat history never scrolls under floating composer', () => {
  let restoreRect: () => void

  beforeEach(() => {
    dockHeight = 72
    resizeObservers.length = 0
    MockWebSocket.instances = []
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    restoreRect = mockDockRect()
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal('ResizeObserver', MockResizeObserver)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
        }),
      }),
    )
  })

  afterEach(() => {
    restoreRect()
    vi.restoreAllMocks()
  })

  it('keeps the sticky composer dock and insets the message list to the live dock height', async () => {
    renderChat()
    await openAndStream(1)

    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    const bottomDock = screen.getByTestId('chat-bottom-dock')
    const messages = screen.getByTestId('chat-messages-container')

    expect(scrollPane).toContainElement(bottomDock)
    expect(bottomDock).toHaveClass('sticky')
    expect(bottomDock).toHaveClass('bottom-0')
    expect(scrollPane).toHaveAttribute('data-composer-inset', '72')
    expect(scrollPane.style.getPropertyValue(COMPOSER_INSET_VAR)).toBe('72px')
    expect(messages).toHaveClass('os-chat-messages')
    expect(messages.className).not.toMatch(/\bpb-24\b|\bpb-32\b|\bh-96\b/)
  })

  it('tracks a taller composer (quote strip) without a stale fixed pixel inset', async () => {
    renderChat()
    const ws = await openAndStream(1)

    const bubble = await screen.findByText('Transcript line 1')
    fireEvent.contextMenu(bubble, { clientX: 80, clientY: 80 })
    fireEvent.click(await screen.findByTestId('context-menu-reply'))
    expect(await screen.findByTestId('composer-reply-strip')).toBeInTheDocument()

    dockHeight = 148
    await act(async () => {
      fireResizeObservers()
    })

    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    expect(scrollPane).toHaveAttribute('data-composer-inset', '148')
    expect(scrollPane.style.getPropertyValue(COMPOSER_INSET_VAR)).toBe('148px')
    expect(ws).toBeDefined()
  })

  it('includes the working-avatar band in the inset while streaming', async () => {
    renderChat()
    const ws = MockWebSocket.instances[0]
    await act(async () => {
      ws.open()
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div id="message-list" hx-swap-oob="beforeend"><div id="message-response-work-inset" class="assistant-message"></div></div>',
        }),
      )
      // Sweep gate: the working band needs a non-empty streaming text.
      ws.onmessage?.(
        new MessageEvent('message', {
          data: '<div hx-swap-oob="beforeend:#message-response-work-inset">…</div>',
        }),
      )
    })

    expect(screen.getByTestId('composer-working-indicator')).toBeInTheDocument()
    dockHeight = 104
    await act(async () => {
      fireResizeObservers()
    })

    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    expect(Number(scrollPane.getAttribute('data-composer-inset'))).toBe(104)
    expect(Number(scrollPane.getAttribute('data-composer-inset'))).toBeGreaterThan(72)
  })

  it('scrolls a long transcript to the end so the last bubble sits above the composer inset', async () => {
    renderChat()
    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    let scrollTopValue = 0
    Object.defineProperty(scrollPane, 'scrollHeight', { configurable: true, value: 4000 })
    Object.defineProperty(scrollPane, 'clientHeight', { configurable: true, value: 600 })
    Object.defineProperty(scrollPane, 'scrollTop', {
      configurable: true,
      get: () => scrollTopValue,
      set: (value: number) => {
        scrollTopValue = value
      },
    })

    await openAndStream(12)

    expect(scrollTopValue).toBe(4000)
    expect(screen.getByText('Transcript line 12')).toBeInTheDocument()
    expect(scrollPane).toHaveAttribute('data-composer-inset', '72')
  })

  it('idle short chat only reserves the measured composer inset, not a huge empty gap', async () => {
    dockHeight = 68
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const scrollPane = screen.getByRole('log', { name: 'Conversation' })
    const messages = screen.getByTestId('chat-messages-container')
    expect(scrollPane).toHaveAttribute('data-composer-inset', '68')
    expect(messages).toHaveClass('os-chat-messages')
    expect(screen.getByText(/Message Support/i)).toBeInTheDocument()
    expect(Number(scrollPane.getAttribute('data-composer-inset'))).toBeLessThan(120)
  })
})

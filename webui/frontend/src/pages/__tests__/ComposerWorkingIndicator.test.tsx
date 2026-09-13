import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { workingLabel } from '../../lib/chatBubble'

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

async function openSocket() {
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
}

async function startStream(id = 'message-response-work1') {
  const ws = MockWebSocket.instances[0]!
  await act(async () => {
    ws.onmessage?.(
      new MessageEvent('message', {
        data: `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`,
      }),
    )
    // The parity sweep gates the indicator on non-empty text for non-CLI
    // seats, so follow assistant_start with a first-stream chunk.
    ws.onmessage?.(
      new MessageEvent('message', {
        data: `<div hx-swap-oob="beforeend:#${id}">…</div>`,
      }),
    )
  })
}

async function finishStream(id = 'message-response-work1', text = 'done') {
  const ws = MockWebSocket.instances[0]!
  await act(async () => {
    ws.onmessage?.(
      new MessageEvent('message', {
        data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${text}</div>`,
      }),
    )
  })
}

describe('REQ-41 / #736: composer working indicator', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
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
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('shows no composer working avatar while idle', async () => {
    renderChat()
    await openSocket()

    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()
    const dock = screen.getByTestId('chat-bottom-dock')
    expect(dock.querySelector('.os-chat-footer')).toBeNull()
    expect(dock.querySelector('form')?.nextElementSibling).toBeNull()
  })

  it('places a small avatar-only indicator inline in the chat pane while streaming', async () => {
    renderChat()
    await openSocket()
    await screen.findByRole('button', { name: /Open Codey definition/i })
    await startStream()

    const indicator = screen.getByTestId('composer-working-indicator')
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    const dock = screen.getByTestId('chat-bottom-dock')
    const log = screen.getByRole('log', { name: 'Conversation' })

    expect(log).toContainElement(indicator)
    expect(dock).not.toContainElement(indicator)
    expect(dock).toContainElement(composer)
    expect(indicator.compareDocumentPosition(composer) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(dock.querySelector('.os-chat-footer')).toBeNull()
    expect(dock.querySelector('form')?.nextElementSibling).toBeNull()

    expect(indicator).toHaveClass('os-composer-working')
    expect(indicator).not.toHaveTextContent(/is working/)
    expect(indicator).not.toHaveTextContent('·')
    expect(indicator).toHaveAttribute('aria-label', workingLabel('Codey'))

    const tip = indicator.querySelector('.tooltip')
    expect(tip).toHaveAttribute('data-tip', workingLabel('Codey'))

    const avatar = indicator.querySelector('[data-agent-avatar]')
    expect(avatar).toBeTruthy()
    expect(avatar).toHaveAttribute('data-avatar-size', 'xs')
    const sized = indicator.querySelector('.os-blob-avatar--xs, .os-agent-avatar--xs')
    expect(sized).toBeTruthy()
    expect(sized).not.toHaveStyle({ width: '100%', height: '100%' })
  })

  it('exposes the working label only as a hover tooltip', async () => {
    renderChat()
    await openSocket()
    await screen.findByRole('button', { name: /Open Codey definition/i })
    await startStream()

    const indicator = screen.getByTestId('composer-working-indicator')
    const tip = indicator.querySelector('.tooltip')
    expect(tip).toHaveAttribute('data-tip', workingLabel('Codey'))
    expect(screen.queryByText(/Codey is working/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/Codey ·/)).not.toBeInTheDocument()

    fireEvent.mouseEnter(tip!)
    expect(tip).toHaveAttribute('data-tip', workingLabel('Codey'))
    expect(indicator).not.toHaveTextContent(/is working/)
  })

  it('removes the indicator completely when the stream finishes', async () => {
    renderChat()
    await openSocket()
    await startStream()
    expect(screen.getByTestId('composer-working-indicator')).toBeInTheDocument()

    await finishStream()
    expect(screen.queryByTestId('composer-working-indicator')).not.toBeInTheDocument()

    const dock = screen.getByTestId('chat-bottom-dock')
    expect(dock.querySelector('.os-chat-footer')).toBeNull()
    expect(dock.querySelector('form')?.nextElementSibling).toBeNull()
  })
})

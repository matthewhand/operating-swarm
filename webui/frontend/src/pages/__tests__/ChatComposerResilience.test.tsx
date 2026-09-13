import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { clearAllQueuedSends } from '../../lib/chatQueue'

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

  failBeforeOpen(code = 1006) {
    this.readyState = 3
    this.onclose?.(new CloseEvent('close', { code }))
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

function activeWs(): MockWebSocket {
  return MockWebSocket.instances[MockWebSocket.instances.length - 1]!
}

function sentMessages(ws: MockWebSocket): string[] {
  return ws.send.mock.calls.map((call) => {
    try {
      const frame = JSON.parse(String(call[0])) as { message?: unknown }
      return typeof frame.message === 'string' ? frame.message : ''
    } catch {
      return ''
    }
  })
}

describe('Composer resilience (#167)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
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
    clearAllQueuedSends()
  })

  it('keeps the composer typeable while connecting and shows the offline hint', () => {
    renderChat()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer).not.toBeDisabled()
    fireEvent.change(composer, { target: { value: 'typed while connecting' } })
    expect(composer).toHaveValue('typed while connecting')
    expect(screen.getByTestId('chat-conn-status')).toHaveTextContent(/offline|queue/i)
  })

  it('keeps the composer typeable after the socket fails before open', async () => {
    renderChat()
    await act(async () => {
      activeWs().failBeforeOpen()
    })
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer).not.toBeDisabled()
    fireEvent.change(composer, { target: { value: 'typed while unreachable' } })
    expect(composer).toHaveValue('typed while unreachable')
  })

  it('never silently drops a send while offline — queues it and sends nothing', () => {
    renderChat()
    const ws = activeWs()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'queued while offline' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    expect(ws.send).not.toHaveBeenCalled()
    expect(composer).toHaveValue('')
    expect(screen.getByTestId('queued-send-pane')).toHaveTextContent('queued while offline')
  })

  it('sends the { message } frame when the socket is open', async () => {
    renderChat()
    await act(async () => {
      activeWs().open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'hello online' } })
    fireEvent.keyDown(composer, { key: 'Enter' })

    await waitFor(() => {
      expect(activeWs().send).toHaveBeenCalled()
    })
    expect(sentMessages(activeWs())).toContain('hello online')
  })

  it('auto-sends an offline-queued message when the socket reconnects', async () => {
    renderChat()
    const ws = activeWs()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'flush me on reconnect' } })
    fireEvent.keyDown(composer, { key: 'Enter' })
    expect(ws.send).not.toHaveBeenCalled()

    await act(async () => {
      ws.open()
    })

    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(sentMessages(ws)).toContain('flush me on reconnect')
  })

  it.each([
    ['/chat', 'support'],
    ['/chat?blueprint=chatbot', 'api'],
    ['/chat?blueprint=codey', 'blueprint'],
    ['/chat?blueprint=grok', 'cli'],
    ['/chat?remote=waveshare', 'remote'],
  ])('lets the user type offline on a %s seat', (entry) => {
    renderChat(entry)
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer).not.toBeDisabled()
    fireEvent.change(composer, { target: { value: `draft for ${entry}` } })
    expect(composer).toHaveValue(`draft for ${entry}`)
  })
})

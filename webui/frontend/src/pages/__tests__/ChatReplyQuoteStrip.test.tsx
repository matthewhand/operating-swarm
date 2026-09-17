import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  sentFrames: string[] = []

  send = vi.fn((data: string) => {
    this.sentFrames.push(data)
  })
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
}

function deliverMockMessage(ws: MockWebSocket, text: string, id = 'message-response-1') {
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

describe('REQ-198: Chat right-click Reply — quote strip in composer, sent with user message', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
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
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('right-clicking a message opens context menu with Reply option, arming reply strip in composer', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeDefined()

    await act(async () => {
      ws.open()
      deliverMockMessage(ws, 'Checking the compact/compress Issues — sounds like it is ready')
    })

    const bubble = await screen.findByText(/Checking the compact\/compress Issues/i)
    expect(bubble).toBeInTheDocument()

    // Right-click on message bubble
    fireEvent.contextMenu(bubble, { clientX: 200, clientY: 300 })

    // Context menu should appear with Reply
    const contextMenu = await screen.findByTestId('message-context-menu')
    expect(contextMenu).toBeInTheDocument()
    const replyBtn = screen.getByTestId('context-menu-reply')
    expect(replyBtn).toBeInTheDocument()

    // Click Reply
    fireEvent.click(replyBtn)

    // Context menu should close
    expect(screen.queryByTestId('message-context-menu')).not.toBeInTheDocument()

    // Reply strip should appear in composer
    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toBeInTheDocument()
    expect(replyStrip).toHaveTextContent(/Checking the compact\/compress Issues/)

    // Composer placeholder should be "Reply…"
    const input = screen.getByRole('textbox', { name: 'Chat message' })
    expect(input).toHaveAttribute('placeholder', 'Reply…')

    // Dismiss with ×
    const dismissBtn = screen.getByTestId('dismiss-reply-button')
    fireEvent.click(dismissBtn)

    // Reply strip is gone, placeholder restores to "Message …"
    expect(screen.queryByTestId('composer-reply-strip')).not.toBeInTheDocument()
    expect(input).toHaveAttribute('placeholder', 'Message …')
  })

  it('sending a message while reply is armed sends structured quote block on the wire', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeDefined()

    await act(async () => {
      ws.open()
      deliverMockMessage(ws, 'Existing answer text')
    })

    const bubble = await screen.findByText(/Existing answer text/i)
    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })

    const replyBtn = await screen.findByTestId('context-menu-reply')
    fireEvent.click(replyBtn)

    const input = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(input, { target: { value: 'Here is my followup' } })

    // Send the message
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false })

    expect(ws.sentFrames.length).toBeGreaterThan(0)
    const lastSent = JSON.parse(ws.sentFrames[ws.sentFrames.length - 1])
    expect(lastSent.message).toContain('> **Support**: Existing answer text')
    expect(lastSent.message).toContain('Here is my followup')

    // Reply strip should be disarmed after send
    expect(screen.queryByTestId('composer-reply-strip')).not.toBeInTheDocument()
    expect(input).toHaveAttribute('placeholder', 'Message …')
  })

  it('#565: the full multi-line quote goes on the wire, even though the bubble clamps it', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <ToastProvider>
          <MemoryRouter initialEntries={['/chat?blueprint=support']}>
            <ChatPage />
          </MemoryRouter>
        </ToastProvider>
      </QueryClientProvider>,
    )

    const ws = MockWebSocket.instances[0]
    expect(ws).toBeDefined()

    const lines = ['line one', 'line two', 'line three', 'line four', 'line five', 'line six']
    await act(async () => {
      ws.open()
      deliverMockMessage(ws, lines.join('\n'))
    })

    const bubble = await screen.findByText(/line six/i)
    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
    fireEvent.click(await screen.findByTestId('context-menu-reply'))

    const input = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(input, { target: { value: 'clamped on screen only' } })
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false })

    const lastSent = JSON.parse(ws.sentFrames[ws.sentFrames.length - 1])
    // Every quoted line reaches the wire, prefixed — the bubble's 4-line clamp
    // must never reach the payload.
    expect(lastSent.message).toContain('> **Support**: line one')
    for (const line of lines.slice(1)) {
      expect(lastSent.message).toContain(`> ${line}`)
    }
    expect(lastSent.message).toContain('clamped on screen only')
  })
})

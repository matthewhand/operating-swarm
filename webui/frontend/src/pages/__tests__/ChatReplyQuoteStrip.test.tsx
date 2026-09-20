import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import * as clipboard from '../../lib/clipboard'
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

  it('#846: right-click Reply quotes ONLY the highlighted snippet even when the browser collapses the selection', async () => {
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
    await act(async () => {
      ws.open()
      deliverMockMessage(ws, 'alpha bravo charlie delta echo')
    })

    const bubble = await screen.findByText(/alpha bravo charlie delta echo/i)

    // Chromium collapses the selection on right-click mousedown BEFORE the
    // contextmenu event. Simulate: live selection during the row's mouseup
    // cache, collapsed by the time contextmenu reads it.
    let selectionReads = 0
    const live = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => 'charlie delta',
    }
    const collapsed = { isCollapsed: true, rangeCount: 0 }
    const spy = vi.spyOn(window, 'getSelection').mockImplementation(() => {
      selectionReads += 1
      return (selectionReads <= 1 ? live : collapsed) as unknown as Selection
    })

    // The user finishes highlighting (mouseup caches it)…
    fireEvent.mouseUp(bubble)
    // …then right-clicks: the live selection is gone, the cache must supply it.
    fireEvent.contextMenu(bubble, { clientX: 150, clientY: 150 })
    spy.mockRestore()

    const menu = await screen.findByTestId('message-context-menu')
    expect(menu).toBeInTheDocument()
    // Label names the target: a partial selection is a quote.
    expect(screen.getByTestId('context-menu-reply')).toHaveTextContent('Reply to quote')

    fireEvent.click(screen.getByTestId('context-menu-reply'))
    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toHaveTextContent('charlie delta')
    expect(replyStrip).not.toHaveTextContent('alpha bravo')
  })

  it('#846: right-click with no highlight still replies to the whole message', async () => {
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
    await act(async () => {
      ws.open()
      deliverMockMessage(ws, 'whole message body here')
    })

    const bubble = await screen.findByText(/whole message body here/i)
    vi.spyOn(window, 'getSelection').mockReturnValue({ isCollapsed: true, rangeCount: 0 } as unknown as Selection)
    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })

    const replyBtn = await screen.findByTestId('context-menu-reply')
    expect(replyBtn).toHaveTextContent(/^Reply$/)
    fireEvent.click(replyBtn)
    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toHaveTextContent('whole message body here')
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

  it('clicking Reply button on message row arms reply strip (#578)', async () => {
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
      deliverMockMessage(ws, 'Assistant message with row action')
    })

    const replyAction = await screen.findByTestId('message-reply-action')
    expect(replyAction).toBeInTheDocument()
    fireEvent.click(replyAction)

    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toBeInTheDocument()
    expect(replyStrip).toHaveTextContent(/Assistant message with row action/)
  })

  it('right-clicking a selection in a message bubble quotes only the selection (#578)', async () => {
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

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => 'compact/compress Issues',
    } as any)

    fireEvent.contextMenu(bubble, { clientX: 200, clientY: 300 })

    const replyBtn = await screen.findByTestId('context-menu-reply')
    fireEvent.click(replyBtn)

    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toBeInTheDocument()
    expect(replyStrip).toHaveTextContent('compact/compress Issues')
    expect(replyStrip).not.toHaveTextContent('sounds like it is ready')

    const input = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(input, { target: { value: 'Quoting a slice only' } })
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false })

    const lastSent = JSON.parse(ws.sentFrames[ws.sentFrames.length - 1])
    expect(lastSent.message).toContain('> **Support**: compact/compress Issues')
    expect(lastSent.message).toContain('Quoting a slice only')
  })

  it('context menu Copy copies the selected text if present, or whole message (#578)', async () => {
    const copySpy = vi.spyOn(clipboard, 'copyTextToClipboard').mockResolvedValue('copied')

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
      deliverMockMessage(ws, 'Whole assistant response to copy')
    })

    const bubble = await screen.findByText(/Whole assistant response to copy/i)

    // With selection:
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => 'assistant response',
    } as any)

    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
    const copyItem = await screen.findByTestId('context-menu-copy')
    expect(copyItem).toHaveTextContent('Copy selection')
    fireEvent.click(copyItem)
    expect(copySpy).toHaveBeenCalledWith('assistant response')

    await waitFor(() => {
      expect(screen.queryByTestId('message-context-menu')).not.toBeInTheDocument()
    })

    // Without selection:
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: true,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => '',
    } as any)

    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
    const copyItemFull = await screen.findByTestId('context-menu-copy')
    expect(copyItemFull).toHaveTextContent('Copy')
    fireEvent.click(copyItemFull)
    expect(copySpy).toHaveBeenCalledWith('Whole assistant response to copy')
  })

  it('selection spanning outside bubble falls back to quoting the whole message (#578)', async () => {
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
      deliverMockMessage(ws, 'First message text')
    })

    const bubble = await screen.findByText(/First message text/i)

    // Selection ancestor is outside bubble (e.g. document body)
    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: document.body }),
      toString: () => 'spans across bubbles',
    } as any)

    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
    const replyBtn = await screen.findByTestId('context-menu-reply')
    fireEvent.click(replyBtn)

    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toHaveTextContent('First message text')
  })

  it('whitespace-only selection falls back to quoting the whole message (#578)', async () => {
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
      deliverMockMessage(ws, 'Message with whitespace selection')
    })

    const bubble = await screen.findByText(/Message with whitespace selection/i)

    vi.spyOn(window, 'getSelection').mockReturnValue({
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => '    \n  ',
    } as any)

    fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
    const replyBtn = await screen.findByTestId('context-menu-reply')
    fireEvent.click(replyBtn)

    const replyStrip = await screen.findByTestId('composer-reply-strip')
    expect(replyStrip).toHaveTextContent('Message with whitespace selection')
  })
})


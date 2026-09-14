import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import {
  QUEUED_PANE_MAX_HEIGHT_CLASS,
  SUGGESTION_CHIP_EVENT,
  clearAllQueuedSends,
} from '../../lib/chatQueue'

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

function startStreaming(ws: MockWebSocket, id = 'message-response-abc123') {
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`,
    }),
  )
}

function finishStreaming(ws: MockWebSocket, id = 'message-response-abc123', reply = 'done') {
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${reply}</div>`,
    }),
  )
}

async function openSocket() {
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
  return MockWebSocket.instances[0]!
}

describe('ChatPage queued sends (REQ-90 / #447)', () => {
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
    resetConversationThreads()
  })

  it('queues a second send before assistant_start so only one WS frame is in flight (REQ-171A-3 / #603)', async () => {
    renderChat()
    const ws = await openSocket()

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'first turn' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'second turn' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(ws.send).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toMatchObject({
      message: 'first turn',
    })
    const row = screen.getByTestId('queued-row')
    expect(row).toHaveAttribute('data-status', 'queued')
    expect(row).toHaveTextContent('second turn')
  })

  it('queues composer send while streaming and does not start a second generation', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'queued while working' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(ws.send).not.toHaveBeenCalled()
    const row = screen.getByTestId('queued-row')
    expect(row).toHaveAttribute('data-status', 'queued')
    expect(row).toHaveTextContent('queued while working')
    expect(row).toHaveTextContent('Queued')
  })

  it('keeps the in-flight assistant above the queued block', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'below the assistant' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const log = screen.getByRole('log', { name: 'Conversation' })
    const assistant = log.querySelector('[data-message-role="assistant"]')
    const pane = screen.getByTestId('queued-send-pane')
    expect(assistant).toBeTruthy()
    expect(pane).toBeTruthy()
    const position = assistant!.compareDocumentPosition(pane)
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('drains the queued text after the stub generation completes', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'send me next' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(ws.send).not.toHaveBeenCalled()

    await act(async () => {
      finishStreaming(ws)
    })

    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toMatchObject({
      message: 'send me next',
    })
    expect(screen.queryByTestId('queued-row')).not.toBeInTheDocument()
  })

  it('applies the 1/3 max-height class when many rows are queued', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    for (let i = 0; i < 8; i += 1) {
      fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
        target: { value: `queued row ${i}` },
      })
      fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    }
    expect(ws.send).not.toHaveBeenCalled()
    const pane = screen.getByTestId('queued-send-pane')
    expect(pane).toHaveClass('os-queued-pane')
    expect(pane).toHaveClass(QUEUED_PANE_MAX_HEIGHT_CLASS)
    expect(pane.style.maxHeight).toMatch(/px|%/)
    expect(screen.getAllByTestId('queued-row')).toHaveLength(8)
  })

  it('does not drain a focused queued editor', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'hold while editing' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    fireEvent.click(screen.getByRole('button', { name: 'hold while editing' }))
    await waitFor(() => {
      expect(screen.getByRole('textbox', { name: 'Edit queued message' })).toHaveFocus()
    })

    await act(async () => {
      finishStreaming(ws)
    })

    expect(ws.send).not.toHaveBeenCalled()
    expect(screen.getByTestId('queued-row')).toHaveTextContent('hold while editing')
  })

  it('never sends a deleted queued row', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'delete me' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove queued message' }))
    expect(screen.queryByTestId('queued-row')).not.toBeInTheDocument()

    await act(async () => {
      finishStreaming(ws)
    })

    expect(ws.send).not.toHaveBeenCalled()
  })

  it('queues a suggestion chip click while a generation is in flight', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    await act(async () => {
      window.dispatchEvent(
        new CustomEvent(SUGGESTION_CHIP_EVENT, { detail: { text: 'from chip' } }),
      )
    })
    expect(ws.send).not.toHaveBeenCalled()
    expect(screen.getByTestId('queued-row')).toHaveTextContent('from chip')
  })

  it('restores queued rows after remount', async () => {
    const first = renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'survives refresh' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(screen.getByTestId('queued-row')).toHaveTextContent('survives refresh')
    first.unmount()

    MockWebSocket.instances = []
    renderChat()
    expect(screen.getByTestId('queued-row')).toHaveTextContent('survives refresh')
  })
})

// #198 — enter-to-interrupt on a queued send
describe('ChatPage queued sends (#198 enter-to-interrupt)', () => {
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
    resetConversationThreads()
  })

  it('shows the enter-to-interrupt hint while a send is queued mid-generation', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'queued item' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(screen.getByTestId('queued-interrupt-hint')).toBeInTheDocument()
    expect(screen.getByTestId('queued-interrupt-hint')).toHaveTextContent('interrupt')
  })

  it('interrupts the running turn and promotes the queued send on Enter over an empty input', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'jump the queue' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(ws.send).not.toHaveBeenCalled()

    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Chat message' }), {
      key: 'Enter',
      code: 'Enter',
    })

    expect(ws.send).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toEqual({
      type: 'cancel_turn',
    })

    // Server closes the interrupted turn with a final partial; the drain
    // effect then promotes the queued message.
    await act(async () => {
      finishStreaming(ws, 'message-response-abc123', 'Interrupted.')
    })
    await waitFor(() => {
      expect(ws.send).toHaveBeenCalledTimes(2)
    })
    expect(JSON.parse(String(ws.send.mock.calls[1][0]))).toMatchObject({
      message: 'jump the queue',
    })
  })
})

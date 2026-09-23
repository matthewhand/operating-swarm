import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, act, fireEvent } from '@testing-library/react'
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
    // #561: the gate is deliberately conservative — an unknown id (codey, with
    // this empty catalog) is NOT proven API, so it queues mid-generation. That
    // fallback is what the CLI queue assertions below ride on; the api_agent
    // concurrency test is proven by id alone and needs no catalog.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              rail: [{ id: 'codey', name: 'Codey', kind: 'cli', cli: 'qwen' }],
            }),
          } as Response
        }
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

  it('#885: the queued pane renders inside the bottom dock (no negative-margin occlusion)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'visible above dock' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    // Structural occlusion pin: the pane must live INSIDE the dock element
    // that carries the negative top margin, never as its previous sibling.
    const dock = screen.getByTestId('chat-bottom-dock')
    expect(within(dock).getByTestId('queued-send-pane')).toBeTruthy()
  })

  it('#885: queueing on a remote seat renders the pane (inside the dock) while the harness turn runs', async () => {
    renderChat('/chat?remote=letta')
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'queued on remote' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const row = screen.getByTestId('queued-row')
    expect(row).toHaveTextContent('queued on remote')
    const dock = screen.getByTestId('chat-bottom-dock')
    expect(within(dock).getByTestId('queued-send-pane')).toBeTruthy()
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
    // #561: the gate is deliberately conservative — an unknown id (codey, with
    // this empty catalog) is NOT proven API, so it queues mid-generation. That
    // fallback is what the CLI queue assertions below ride on; the api_agent
    // concurrency test is proven by id alone and needs no catalog.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              rail: [{ id: 'codey', name: 'Codey', kind: 'cli', cli: 'qwen' }],
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

describe('ChatPage stop button (#223)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    // #561: the gate is deliberately conservative — an unknown id (codey, with
    // this empty catalog) is NOT proven API, so it queues mid-generation. That
    // fallback is what the CLI queue assertions below ride on; the api_agent
    // concurrency test is proven by id alone and needs no catalog.
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.toString()
              : input.url
        if (url.includes('/v1/cli-agents/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              rail: [{ id: 'codey', name: 'Codey', kind: 'cli', cli: 'qwen' }],
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
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
  })

  // #1096: the stop affordance moved from the composer to the generating
  // agent's transcript row (agent-row-stop). The cancel frame is unchanged.
  it('shows a stop button on the working row while generating and sends cancel_turn on click', async () => {
    renderChat()
    const ws = await openSocket()

    // Idle: no stop affordance.
    expect(screen.queryByTestId('agent-row-stop')).toBeNull()

    await act(async () => {
      startStreaming(ws)
    })

    const stop = screen.getByTestId('agent-row-stop')
    fireEvent.click(stop)
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toEqual({
      type: 'cancel_turn',
    })
  })

  it('keeps the working-row stop until the generation finishes, then hides it', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    expect(screen.getByTestId('agent-row-stop')).toBeTruthy()

    await act(async () => {
      finishStreaming(ws)
    })
    await waitFor(() => {
      expect(screen.queryByTestId('agent-row-stop')).toBeNull()
    })
  })

  it('stop leaves queued sends intact (stop ≠ clear)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'still queued' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(screen.getByTestId('queued-row')).toBeTruthy()

    fireEvent.click(screen.getByTestId('agent-row-stop'))
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toEqual({
      type: 'cancel_turn',
    })
    expect(screen.getByTestId('queued-row')).toHaveTextContent('still queued')
  })

  // #1093 (4): the in-input ↵ badge is retired — the queued pill already
  // carries the enter-interrupt hint, and the badge spent composer width.
  it('renders no in-input send hint while a queued send waits (#1093)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()

    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'send me now' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()
    // The Esc hint appears only for a typed draft.
    expect(screen.queryByTestId('composer-clear-hint')).not.toBeInTheDocument()
  })

  it('keeps no send hint across the queue lifecycle (#1093)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'drain me' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()

    await act(async () => {
      finishStreaming(ws)
    })

    await waitFor(() => {
      expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()
    })
  })

  it('a fresh draft over a queued send shows only the Esc hint (#1072 superseded)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'hold this' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'a fresh draft' },
    })

    expect(screen.queryByTestId('composer-send-hint')).not.toBeInTheDocument()
    expect(screen.getByTestId('composer-clear-hint')).toBeInTheDocument()
  })

  // #561 ask 3: queueing mid-generation is a non-API affordance. API seats
  // take concurrent sends; only the closed-socket transport queue (#167)
  // applies to every kind.
  it('sends concurrently on an API seat mid-generation instead of queueing', async () => {
    renderChat('/chat?blueprint=api_agent')
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'concurrent api send' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(ws.send).toHaveBeenCalledTimes(1)
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toMatchObject({
      message: 'concurrent api send',
    })
    expect(screen.queryByTestId('queued-row')).not.toBeInTheDocument()
  })

  it('still queues mid-generation on a CLI seat', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'cli queue' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    expect(ws.send).not.toHaveBeenCalled()
    expect(screen.getByTestId('queued-row')).toHaveTextContent('cli queue')
  })

  describe('#925 queued sends inside composer', () => {
    it('renders queued sends inside .os-composer extending out of the input card', async () => {
      renderChat()
      const ws = await openSocket()
      await act(async () => {
        startStreaming(ws)
      })
      fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
        target: { value: 'queued inside composer' },
      })
      fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

      const composer = document.querySelector('.os-composer')!
      expect(composer).toBeTruthy()
      expect(within(composer as HTMLElement).getByTestId('queued-send-pane')).toBeTruthy()
      expect(composer).toHaveClass('os-composer--queued')
    })

    it('renders queued sends directly above the reply strip when both exist', async () => {
      renderChat()
      const ws = await openSocket()
      await act(async () => {
        startStreaming(ws, 'message-response-1')
      })
      await act(async () => {
        finishStreaming(ws, 'message-response-1', 'Hello there')
      })

      await act(async () => {
        startStreaming(ws, 'message-response-2')
      })

      // Queue a message while turn 2 is in flight
      fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
        target: { value: 'queued message' },
      })
      fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

      // Arm reply on the prior message
      const bubble = await screen.findByText('Hello there')
      fireEvent.contextMenu(bubble, { clientX: 100, clientY: 100 })
      const replyBtn = await screen.findByTestId('context-menu-reply')
      fireEvent.click(replyBtn)

      const composer = document.querySelector('.os-composer')!
      expect(composer).toBeTruthy()
      const queuedPane = within(composer as HTMLElement).getByTestId('queued-send-pane')
      const replyStrip = within(composer as HTMLElement).getByTestId('composer-reply-strip')
      expect(queuedPane).toBeInTheDocument()
      expect(replyStrip).toBeInTheDocument()

      // Queued pane must sit directly above the reply strip
      expect(queuedPane.compareDocumentPosition(replyStrip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    })
  })
})




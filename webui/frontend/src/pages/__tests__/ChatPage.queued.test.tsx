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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(1)
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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
    renderChat('/chat?remote=openwebui')
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
    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)

    await act(async () => {
      finishStreaming(ws)
    })

    await waitFor(() => {
      expect(ws.send).toHaveBeenCalled()
    })
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
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
    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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
    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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
    // PR-4: the mux singleton outlives the component; drop it so the
    // remount drives a fresh socket from the new stub instances.
    const spa = await import('../../lib/spaSocket')
    act(() => {
      spa.resetSpaSocketForTests()
    })
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
    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)

    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Chat message' }), {
      key: 'Enter',
      code: 'Enter',
    })

    // #1226: the interrupt is acknowledged locally — cancel_turn goes out AND
    // the queued row promotes immediately, instead of the old
    // remove→re-enqueue→remove bounce while the server's turn_finished was
    // still in flight.
    await waitFor(() => {
      expect(
        ws.send.mock.calls.filter((c) => !String(c[0]).includes('"kind":"subscribe"')),
      ).toHaveLength(2)
    })
    const chatFrames = ws.send.mock.calls
      .map((c) => String(c[0]))
      .filter((s) => !s.includes('"kind":"subscribe"'))
    expect(JSON.parse(chatFrames[0])).toMatchObject({ type: 'cancel_turn' })
    expect(JSON.parse(chatFrames[1])).toMatchObject({ message: 'jump the queue' })

    // The interrupted turn still closes server-side; no further sends.
    await act(async () => {
      finishStreaming(ws, 'message-response-abc123', 'Interrupted.')
    })
    expect(
      ws.send.mock.calls.filter((c) => !String(c[0]).includes('"kind":"subscribe"')),
    ).toHaveLength(2)
  })
})

describe('#1276 queue FIFO + optimistic promotion rendering', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
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

  it('a composer send joins the queue while ANY queued row exists (FIFO, no bypass)', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    // Row A enqueues mid-generation (serial seat).
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'first queued' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(screen.getByTestId('queued-row')).toHaveTextContent('first queued')

    // The turn closes — the drain promotes row A and its chat frame goes out.
    await act(async () => {
      finishStreaming(ws, 'message-response-abc123', 'turn one done')
    })
    await waitFor(() => {
      expect(
        ws.send.mock.calls.filter((c) => !String(c[0]).includes('"kind":"subscribe"')),
      ).toHaveLength(1)
    })

    // Row A is now mid-flight (assistant_start has not arrived). Defect 1:
    // a NEW send must join the BACK of the queue, never bypass it.
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'second queued' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const chatFrames = ws.send.mock.calls
      .map((c) => String(c[0]))
      .filter((s) => !s.includes('"kind":"subscribe"'))
    expect(chatFrames).toHaveLength(1)
    expect(JSON.parse(chatFrames[0])).toMatchObject({ message: 'first queued' })
    const row = screen.getByTestId('queued-row')
    expect(row).toHaveAttribute('data-status', 'queued')
    expect(row).toHaveTextContent('second queued')
  })

  it('interrupt-promotion renders the promoted message optimistically before any server frame', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'jump the queue' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(screen.getByTestId('queued-row')).toHaveTextContent('jump the queue')

    // Enter over an empty composer: cancel + promote.
    fireEvent.keyDown(screen.getByRole('textbox', { name: 'Chat message' }), {
      key: 'Enter',
      code: 'Enter',
    })

    // Defect 2: the promoted send must appear in the transcript IMMEDIATELY
    // (optimistic pending row), before the server's user_echo arrives.
    const transcript = document.querySelector('[data-testid="chat-messages-container"]')
    expect(transcript).not.toBeNull()
    expect(transcript!.textContent).toContain('jump the queue')

    // The server echo then upgrades the same row instead of duplicating it:
    // still exactly one occurrence of the promoted text after the echo.
    await act(async () => {
      ws.onmessage?.(
        new MessageEvent('message', {
          data: JSON.stringify({ kind: 'user_echo', text: 'jump the queue' }),
        }),
      )
    })
    expect(transcript!.textContent?.split('jump the queue').length - 1).toBe(1)
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

    // Idle: no stop affordance and no Running badge (#1371).
    expect(screen.queryByTestId('agent-row-stop')).toBeNull()
    expect(screen.queryByTestId('running-status-badge')).toBeNull()
    expect(screen.queryByTestId('composer-stop')).toBeNull()

    await act(async () => {
      startStreaming(ws)
    })

    // #1371: the badge slot is the standing chrome; the stop stays hidden
    // until it is hovered.
    const badge = screen.getByTestId('running-status-badge')
    expect(badge).toHaveAttribute('data-revealed', 'false')
    // #1684: this is a CLI seat (`kind: 'cli'`, qwen). The turn-phase
    // `tool_status` frames are produced only on the API path
    // (`kind_bases.py` attaches the hooks in `ApiKindBase.run`), so a CLI
    // turn emits no phase — and the badge must therefore stay hidden rather
    // than be faked from `streaming`. The badge *pill* is gone from this
    // assertion on purpose: it is the "a tool call is in flight" mark now,
    // not a second view of the flag that animates the eye-dots.
    expect(screen.queryByTestId('running-badge-pill')).toBeNull()
    expect(badge.querySelector('.loading-spinner')).toBeNull()
    // The eye-dots are the working mark for a plain streaming turn.
    expect(screen.getByTestId('composer-working-indicator')).toBeTruthy()
    const stop = screen.getByTestId('agent-row-stop')
    expect(stop).toHaveAttribute('data-visible', 'false')
    expect(screen.queryByTestId('composer-stop')).toBeNull()

    fireEvent.mouseEnter(badge)
    expect(badge).toHaveAttribute('data-revealed', 'true')
    expect(stop).toHaveAttribute('data-visible', 'true')

    fireEvent.click(stop)
    // #1096/#1097 ADR-017 PR-2: the stop is agent-scoped (no bookend seen
    // yet in this mock, so the registry fallback names the agent only).
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
      type: 'cancel_turn',
      agent: 'codey',
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

  // #1096 placement: the stop tracks the END of the streaming message, so it
  // must follow the assistant bubble in document order rather than sitting
  // before/beside the avatar at the start of the row.
  it('renders the stop affordance after the assistant bubble content', async () => {
    renderChat()
    const ws = await openSocket()
    await act(async () => {
      startStreaming(ws)
    })

    const bubble = screen.getByTestId('chat-bubble')
    const stop = screen.getByTestId('agent-row-stop')
    const position = bubble.compareDocumentPosition(stop)
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(bubble.contains(stop)).toBe(false)
    expect(screen.getByTestId('agent-row-stop-slot')).toBeInTheDocument()
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
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
      type: 'cancel_turn',
      agent: 'codey',
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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(1)
    expect(JSON.parse(String(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string))).toMatchObject({
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

    expect(ws.send.mock.calls.filter((c) => !String(c[0]).includes('\"kind\":\"subscribe\"'))).toHaveLength(0)
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




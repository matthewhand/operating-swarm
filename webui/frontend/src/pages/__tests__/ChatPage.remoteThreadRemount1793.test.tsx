/**
 * #1793 — a remote seat's thread survives navigating away and back.
 *
 * The regression this pins: the operator was chatting with `?remote=<name>`,
 * clicked away to another view and came back to an EMPTY transcript while the
 * rows sat in the database. The stub here is deliberately STRICT — it returns
 * rows only for the exact conversation id the rows are stored under, and an
 * empty array for anything else — so a remount that asks for a different id
 * fails loudly instead of silently "passing" against a permissive stub.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'

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

const SEAT = 'trueforge-2'
const CID = 'remote-trueforge-2'
const USER_TURN = 'trueforge user turn'
const AGENT_TURN = 'trueforge agent turn'

function okJson(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as Response
}

function renderChat(entry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

/** Rows exist for exactly one conversation id; every other id loads empty. */
function strictStub(requested: string[]) {
  return () =>
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/chat/thread/')) {
        const u = new URL(url, 'http://localhost')
        const cid = u.searchParams.get('conversation_id') || ''
        requested.push(cid)
        if (cid === CID) {
          return okJson({
            agent_id: 'remote_harness',
            conversation_id: CID,
            kind: 'remote',
            editable: false,
            messages: [
              { role: 'user', content: USER_TURN },
              { role: 'assistant', content: AGENT_TURN },
            ],
            turns: [
              { role: 'user', content: USER_TURN },
              { role: 'assistant', content: AGENT_TURN },
            ],
            ui_events: [],
          })
        }
        return okJson({
          agent_id: 'remote_harness',
          conversation_id: cid,
          kind: 'remote',
          editable: false,
          messages: [],
          turns: [],
          ui_events: [],
        })
      }
      if (url.includes('/v1/remotes')) {
        return okJson({
          object: 'list',
          kinds: [{ id: SEAT, label: 'TrueForge' }],
          configured: [
            {
              id: SEAT,
              kind: 'trueforge',
              label: 'TrueForge',
              title: 'TrueForge',
              host_label: '',
              base_url: 'http://127.0.0.1:1',
              source: 'config',
            },
          ],
        })
      }
      return okJson({ data: [] })
    })
}

async function openSockets() {
  await act(async () => {
    for (const ws of MockWebSocket.instances) ws.open()
  })
}

describe('#1793 remote seat thread survives a remount', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('re-renders the stored messages after navigating away and back', async () => {
    const requested: string[] = []
    vi.stubGlobal('fetch', strictStub(requested)())

    const first = renderChat(`/chat?remote=${SEAT}`)
    await openSockets()
    expect(await screen.findByText(USER_TURN)).toBeInTheDocument()
    expect(screen.getByText(AGENT_TURN)).toBeInTheDocument()
    // Unmount the page the way a route change does — in-memory `threads` state
    // is gone, so the only way these messages can come back is the thread
    // endpoint answering for the right conversation id.
    first.unmount()

    MockWebSocket.instances = []
    vi.stubGlobal('fetch', strictStub(requested)())
    renderChat(`/chat?remote=${SEAT}`)
    await openSockets()

    expect(await screen.findByText(USER_TURN, undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.getByText(AGENT_TURN)).toBeInTheDocument()
    expect(screen.queryByTestId('chat-thread-loading')).not.toBeInTheDocument()
    expect(screen.queryByTestId('chat-hydrate-error')).not.toBeInTheDocument()
  })

  it('derives the same conversation id on remount as on first mount', async () => {
    const requested: string[] = []
    vi.stubGlobal('fetch', strictStub(requested)())

    const first = renderChat(`/chat?remote=${SEAT}`)
    await openSockets()
    await screen.findByText(USER_TURN)
    const onFirstMount = requested.filter((cid) => cid === CID)
    expect(onFirstMount.length).toBeGreaterThan(0)
    first.unmount()

    MockWebSocket.instances = []
    requested.length = 0
    vi.stubGlobal('fetch', strictStub(requested)())
    renderChat(`/chat?remote=${SEAT}`)
    await openSockets()
    await screen.findByText(USER_TURN, undefined, { timeout: 3000 })

    // Pinned: the remount asks for the id the rows live under — and only it.
    // A mint-per-mount or a dropped remote prefix would show up here.
    expect(requested.length).toBeGreaterThan(0)
    expect([...new Set(requested)]).toEqual([CID])
  })

  it('never requests a conversation id the transcript is not rendered under', async () => {
    const requested: string[] = []
    vi.stubGlobal('fetch', strictStub(requested)())
    renderChat(`/chat?remote=${SEAT}`)
    await openSockets()
    await screen.findByText(USER_TURN, undefined, { timeout: 3000 })

    // The rendered thread is the one that was requested. This is the invariant
    // a "send writes under A, load reads under B" split would break.
    const container = screen.getByTestId('chat-messages-container')
    expect(container).toHaveAttribute('data-load-phase', 'ready')
    expect(requested.every((cid) => cid === CID)).toBe(true)
  })
})

describe('#1793 a whitespace-only ?session= cannot re-key a remote thread', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('loads the base thread instead of a trailing-space conversation', async () => {
    const requested: string[] = []
    vi.stubGlobal('fetch', strictStub(requested)())
    renderChat(`/chat?remote=${SEAT}&session=%20`)
    await openSockets()

    expect(await screen.findByText(USER_TURN, undefined, { timeout: 3000 })).toBeInTheDocument()
    // The untrimmed form minted `remote-trueforge-2- ` — a conversation with
    // no rows, which renders as an empty thread.
    expect([...new Set(requested)]).toEqual([CID])
  })
})

/**
 * REQ-127 (#517) — the composer's keyboard contract.
 *
 * This exists because a Python source-pin read
 * `assert "Shift+Enter" in page or "shiftKey" in page`. An `or` of two
 * spellings, satisfiable by the substring `shiftKey` appearing anywhere in six
 * thousand lines of the chat surface. It could not distinguish:
 *
 *   - Enter sends, Shift+Enter inserts a newline   (the contract)
 *   - Enter sends, Shift+Enter also sends          (loses the newline)
 *   - Enter inserts a newline, Shift+Enter sends   (inverted)
 *   - the handler swallows both, sending nothing   (broken, still green)
 *
 * The last one is why the two cases live in a single test: a test that only
 * asserts "Shift+Enter sent nothing" passes just as happily against a composer
 * that never sends at all. Each case is therefore proved against a page where
 * the *other* key is shown to work.
 *
 * `preventDefault()` is the browser's "do not insert a newline" signal, so a
 * composer that lets the browser insert the newline must not call it, and a
 * composer that sends must — otherwise the newline is inserted and the turn
 * starts, leaving a stray blank line at the top of the next draft.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { clearAllQueuedSends } from '../../lib/chatQueue'
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

function renderChat(initialEntry = '/chat?blueprint=codey') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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

async function openSocket(): Promise<MockWebSocket> {
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
  return MockWebSocket.instances[0]!
}

/** Chat-turn frames only — the transport's own subscribe ping is not a turn. */
function turnFrames(ws: MockWebSocket): Record<string, unknown>[] {
  return ws.send.mock.calls
    .map((call) => String(call[0]))
    .filter((raw) => !raw.includes('"kind":"subscribe"'))
    .map((raw) => JSON.parse(raw))
}

function composer(): HTMLTextAreaElement {
  return screen.getByRole('textbox', { name: 'Chat message' }) as HTMLTextAreaElement
}

function pressEnter(shiftKey: boolean): KeyboardEvent {
  const event = new KeyboardEvent('keydown', {
    key: 'Enter',
    shiftKey,
    bubbles: true,
    cancelable: true,
  })
  fireEvent(composer(), event)
  return event
}

describe('REQ-127 the composer is a newline-preserving textarea', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({ data: [{ id: 'codey', name: 'Codey', description: 'Code' }] }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
    localStorage.clear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    localStorage.clear()
  })

  it('exposes the composer as a textarea with a stable accessible name', async () => {
    // The old pin matched `aria-label="Chat message"` as a JSX *attribute*.
    // The composer now receives its props as an object, so the same string is
    // an object key — the pin went red on a pure prop-shape change. Querying
    // by role + accessible name is what a screen reader does, and it survives
    // the prop shape, the component boundary, and any class churn.
    renderChat()
    const box = await screen.findByRole('textbox', { name: 'Chat message' })
    expect(box.tagName).toBe('TEXTAREA')
    expect(box).toHaveAttribute('rows')
  })

  it('Enter sends and suppresses the newline; Shift+Enter does neither', async () => {
    renderChat()
    const ws = await openSocket()
    const box = composer()

    // --- Shift+Enter: a newline, not a turn --------------------------------
    fireEvent.change(box, { target: { value: 'first line' } })
    const shiftEnter = pressEnter(true)

    // No preventDefault → the browser inserts the newline. That is the whole
    // point of the modifier.
    expect(shiftEnter.defaultPrevented).toBe(false)
    // Nothing reached the wire, and the draft is untouched.
    expect(turnFrames(ws)).toHaveLength(0)
    expect(box.value).toContain('first line')

    // --- Enter: a turn, and no stray newline -------------------------------
    // Proved in the same mount, so "Shift+Enter sent nothing" above is not
    // vacuously true of a composer that never sends.
    fireEvent.change(box, { target: { value: 'ship it' } })
    const enter = pressEnter(false)

    // preventDefault is what stops the browser also inserting a newline, which
    // would leave a blank line at the top of the next draft.
    expect(enter.defaultPrevented).toBe(true)
    await waitFor(() => expect(turnFrames(ws)).toHaveLength(1))
    expect(turnFrames(ws)[0]).toMatchObject({ message: 'ship it' })
  })
})

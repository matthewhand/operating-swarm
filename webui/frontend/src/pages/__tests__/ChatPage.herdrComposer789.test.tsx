/**
 * #789 — a herdr seat's talk-to choice lives in the composer's two-stage
 * routing picker, not a dedicated navbar button (#543, retired here).
 *
 * Stage 1 lists the Herdr remote; descending lists the configured panes from
 * GET /v1/herdr-agents/; picking one lands in `?remote=herdr&session=<name>`
 * — the same URL contract the retired popup wrote. The retired surfaces
 * (`herdr-agent-picker` button, `herdr-agent-popup`) must be gone.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []
  readyState = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev?: Event) => void) | null = null
  onclose: ((ev?: Event) => void) | null = null
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

function remotesCatalog() {
  return {
    object: 'list',
    kinds: [{ id: 'herdr', label: 'Herdr' }],
    configured: [
      {
        id: 'herdr',
        kind: 'herdr',
        title: 'Herdr',
        source: 'config',
        base_url: 'http://127.0.0.1:8930',
      },
    ],
  }
}

function stubFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return { ok: true, status: 200, json: async () => remotesCatalog() } as Response
    }
    if (url.includes('/v1/herdr-agents/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'list',
          data: [
            { id: 3, object: 'herdr.agent', kind: 'herdr', name: 'w3:p1', remote: 'localhost', created_at: '', updated_at: '' },
            { id: 7, object: 'herdr.agent', kind: 'herdr', name: 'grok', remote: 'max', created_at: '', updated_at: '' },
          ],
        }),
      } as Response
    }
    return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
  })
}

/** MemoryRouter's location is internal — surface it for URL assertions. */
function LocationProbe() {
  const location = useLocation()
  return <span data-testid="router-location" data-search={location.search} />
}

function renderChat(initialEntry: string) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <LocationProbe />
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#789 — herdr routing through the composer picker', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    window.localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('fetch', stubFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    window.localStorage.clear()
  })

  it('lists configured herdr panes in stage 2 and lands a pick in ?session=', async () => {
    renderChat('/chat?remote=herdr')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    // #543 surfaces are retired — the composer picker owns the choice now.
    expect(screen.queryByTestId('herdr-agent-picker')).toBeNull()
    expect(screen.queryByTestId('herdr-agent-popup')).toBeNull()

    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    await screen.findByTestId('composer-picker')

    // Stage 1: the Herdr remote provider row.
    fireEvent.click(
      (await screen.findAllByTestId('composer-picker-row')).find((el) =>
        /Herdr/.test(el.textContent || ''),
      )!,
    )

    // Stage 2: the configured panes from GET /v1/herdr-agents/.
    await waitFor(async () => {
      const rows = await screen.findAllByTestId('composer-picker-row')
      expect(rows.some((el) => /grok/.test(el.textContent || ''))).toBe(true)
    })

    fireEvent.click(
      (await screen.findAllByTestId('composer-picker-row')).find((el) =>
        /grok/.test(el.textContent || ''),
      )!,
    )

    await waitFor(() => {
      expect(screen.getByTestId('router-location').getAttribute('data-search')).toBe(
        '?remote=herdr&session=grok',
      )
    })
  })

  it('keeps the warm herdr payload flowing for a herdr seat (no open-gated fetch)', async () => {
    const fetchMock = stubFetch()
    vi.stubGlobal('fetch', fetchMock)
    renderChat('/chat?remote=herdr')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((c) => String(c[0]).includes('/v1/herdr-agents/'))).toBe(true)
    })
  })
})

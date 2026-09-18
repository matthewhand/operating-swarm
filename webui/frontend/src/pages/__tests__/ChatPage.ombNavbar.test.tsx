import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
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
}

const FAT_MESSAGE = 'x'.repeat(4000)

function remotesCatalog() {
  return {
    object: 'list',
    kinds: [{ id: 'omb', label: 'OpenMousBot' }],
    configured: [
      {
        id: 'omb',
        kind: 'omb',
        label: 'OpenMousBot',
        title: 'OpenMousBot',
        host_label: '',
        base_url: 'http://127.0.0.1:8802',
        source: 'config',
      },
    ],
  }
}

function operateListBody() {
  return {
    remote: 'omb',
    op: 'list',
    ok: true,
    detail: 'OpenMousBot listed 2 bot(s) via GET /api/bots',
    data: {
      bots: [
        { id: 'desk-1', name: 'Desk', messages: [{ role: 'assistant', content: FAT_MESSAGE }] },
        { id: 'spec-9', name: 'Specialist', messages: [{ role: 'user', content: FAT_MESSAGE }] },
      ],
    },
  }
}

function stubFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/operate/')) {
      return {
        ok: true,
        status: 200,
        json: async () => operateListBody(),
      } as Response
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return {
        ok: true,
        status: 200,
        json: async () => remotesCatalog(),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ data: [] }),
    } as Response
  })
}

function renderChat(initialEntry: string) {
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
  return MockWebSocket.instances[0]!
}

describe('ChatPage OMB navbar agents (#102)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
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

  it('retrieves operate list and shows OpenMousBot agents next to Remote (omb)', async () => {
    renderChat('/chat?remote=omb')
    await openSocket()
    const fetchMock = vi.mocked(fetch)
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/v1/remotes/omb/operate/')),
      ).toBe(true)
    })
    expect(screen.getByTestId('navbar-routing-picker')).toHaveAttribute('data-seat-kind', 'remote')
    // #629: the combined pill shows the remote provider label.
    expect(screen.getByTestId('routing-pill-agent')).toHaveTextContent('OpenMousBot')
    // #504: nested remote agents are palette rows (labelled by name), not a
    // nested flyout menu.
    fireEvent.click(screen.getByTestId('routing-pill-agent'))
    const palette = await screen.findByTestId('os-model-search-palette')
    expect(await within(palette).findByTestId('os-model-row-desk-1', {}, { timeout: 4000 })).toBeInTheDocument()
    expect(within(palette).getByTestId('os-model-row-spec-9')).toBeInTheDocument()
    expect(within(palette).getByTestId('os-model-row-desk-1')).toHaveTextContent('Desk')
    expect(within(palette).getByTestId('os-model-row-spec-9')).toHaveTextContent('Specialist')
    expect(palette.textContent).not.toContain(FAT_MESSAGE)
    expect(screen.getByTestId('navbar-routing-picker').textContent).not.toMatch(/\bOMB\b/)
  })

  it('send frame params.target is the selected bot id', async () => {
    renderChat('/chat?remote=omb&session=desk-1')
    const ws = await openSocket()
    // #629: the combined pill carries the session target label.
    const pill = await screen.findByTestId('routing-pill-agent')
    await waitFor(() => {
      expect(pill).toHaveTextContent('Desk')
    })
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'hello desk' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(ws.send).toHaveBeenCalled()
    expect(JSON.parse(String(ws.send.mock.calls[0][0]))).toMatchObject({
      message: 'hello desk',
      blueprint: 'remote_harness',
      params: {
        remote: 'omb',
        name: 'omb',
        op: 'send',
        target: 'desk-1',
      },
    })
  })

  it('refuses send with omb_bot_required when no agent is selected', async () => {
    renderChat('/chat?remote=omb')
    const ws = await openSocket()
    await screen.findByTestId('routing-pill-agent')
    fireEvent.change(screen.getByRole('textbox', { name: 'Chat message' }), {
      target: { value: 'should not go' },
    })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))
    expect(ws.send).not.toHaveBeenCalled()
    expect(await screen.findByText(/omb_bot_required/)).toBeInTheDocument()
  })
})

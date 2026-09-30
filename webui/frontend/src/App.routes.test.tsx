import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App, { chatPathWithSearch } from './App'

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

  // The url is kept so a test can pick the socket it means to drive (#1729
  // added a second, dedicated Herdr status socket, so "instances[0]" is no
  // longer a reliable way to name the chat one).
  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

async function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const view = render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
  // #1629: chat routes suspend on the ChatPage chunk. /agents mounts
  // AgentRouterPage and has no chat composer — waiting for one rejects.
  if (!path.startsWith('/agents')) {
    await screen.findByRole('textbox', { name: 'Chat message' })
  }
  return view
}

describe('chatPathWithSearch', () => {
  it('keeps /chat and preserves the query string', () => {
    expect(chatPathWithSearch('')).toBe('/chat')
    expect(chatPathWithSearch('?blueprint=codey')).toBe('/chat?blueprint=codey')
    expect(chatPathWithSearch('blueprint=codey')).toBe('/chat?blueprint=codey')
  })
})

describe('SPA /chat stays Chat (not /agents)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response),
    )
    window.history.pushState({}, '', '/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders composer + silent healthy status at /chat', async () => {
    await renderAppAt('/chat')
    await act(async () => {
      // The app opens more than one socket: the chat multiplex plus #1729's
      // dedicated Herdr status feed. Open the CHAT one by URL — index 0 is
      // whichever mounted first, and this assertion is about chat health.
      MockWebSocket.instances.find((ws) => ws.url?.includes('/ws/spa/'))?.open()
    })
    expect(window.location.pathname).toBe('/chat')
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.getByLabelText('Connection status')).toHaveTextContent('')
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /^Chat$/ })).not.toBeInTheDocument()
  })

  it('keeps /agents as Agent Router (not an alias of /chat)', async () => {
    const pending = renderAppAt('/agents')
    expect(window.location.pathname).toBe('/agents')
    // #930: the diverged duplicate sidebar is gone — the page no longer mounts
    // its own rail (no search affordance, no 'Focused' section) and the App
    // shell is the single sidebar owner. Assert before the lazy Agent Router
    // chunk settles, then drain the helper so its promise cannot reject later.
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
    expect(screen.queryByText('Focused')).not.toBeInTheDocument()
    await pending
  })
})

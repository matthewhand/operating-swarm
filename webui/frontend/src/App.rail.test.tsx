import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { NARROW_RAIL_MAX_PX } from './lib/narrowViewport'
import { SWIPE_HINT_STORAGE_KEY } from './lib/swipeHint'
import { SWIPE_HINT_TEXT } from './components/RailChrome'
import { LEFT_EDGE_PX, MIN_SWIPE_DX } from './lib/leftEdgeSwipe'

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

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

const blueprints = [
  {
    id: 'codey',
    object: 'blueprint',
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  },
  {
    id: 'stewie',
    object: 'blueprint',
    name: 'Stewie',
    description: 'Helpful agent',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  },
]

type ChangeListener = EventListener

function installViewport(width: number) {
  let current = width
  const listeners = new Set<ChangeListener>()

  const matchesFor = (query: string) => {
    const max = /max-width:\s*(\d+)px/.exec(query)
    const min = /min-width:\s*(\d+)px/.exec(query)
    if (max) return current <= Number(max[1])
    if (min) return current >= Number(min[1])
    return false
  }

  Object.defineProperty(window, 'innerWidth', {
    configurable: true,
    get: () => current,
  })

  window.matchMedia = ((query: string) => ({
    get matches() {
      return matchesFor(query)
    },
    media: query,
    onchange: null,
    addEventListener: (_event: string, fn: ChangeListener) => {
      listeners.add(fn)
    },
    removeEventListener: (_event: string, fn: ChangeListener) => {
      listeners.delete(fn)
    },
    addListener: (fn: ChangeListener) => {
      listeners.add(fn)
    },
    removeListener: (fn: ChangeListener) => {
      listeners.delete(fn)
    },
    dispatchEvent: () => false,
  })) as typeof window.matchMedia

  return {
    setWidth(next: number) {
      current = next
      listeners.forEach((fn) => fn(new Event('change')))
    },
  }
}

function stubAgentApis() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return { ok: true, status: 200, json: async () => [] } as Response
      }
      if (url.includes('herdr')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [] }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: blueprints }),
      } as Response
    }),
  )
}

function renderApp(path = '/chat') {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

function rail() {
  return document.querySelector('[data-testid="os-agent-rail"]') as HTMLElement
}

function swipeFromLeft() {
  fireEvent.touchStart(window, {
    touches: [{ identifier: 1, clientX: 8, clientY: 240 }],
  })
  fireEvent.touchMove(window, {
    touches: [{ identifier: 1, clientX: 8 + MIN_SWIPE_DX + 4, clientY: 244 }],
  })
  fireEvent.touchEnd(window)
}

async function openRailAndPick(name: RegExp) {
  fireEvent.click(screen.getByRole('button', { name: /Open agent list/i }))
  expect(rail()).toHaveAttribute('data-rail-open', 'true')
  const list = await screen.findByRole('navigation', { name: 'Agent list' })
  fireEvent.click(await within(list).findByRole('link', { name }))
}

describe('REQ-54 mobile rail tuck', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    stubAgentApis()
    window.history.pushState({}, '', '/')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('hides the rail after an agent pick on a narrow viewport and keeps chat mounted', async () => {
    installViewport(390)
    renderApp('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(document.querySelector('[data-narrow-viewport="true"]')).toBeTruthy()
    expect(rail()).toHaveAttribute('data-rail-open', 'false')
    expect(screen.getByRole('button', { name: /Open agent list/i })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Support' })).toBeInTheDocument()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer).toBeInTheDocument()

    await openRailAndPick(/Codey/)

    expect(rail()).toHaveAttribute('data-rail-open', 'false')
    expect(screen.getByRole('heading', { name: 'Codey' })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(composer)
    expect(screen.getByTestId('os-swipe-hint')).toHaveTextContent(SWIPE_HINT_TEXT)
  })

  it('restores the tucked rail from the header control and a left-edge swipe', async () => {
    installViewport(390)
    renderApp('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    await openRailAndPick(/Codey/)
    expect(rail()).toHaveAttribute('data-rail-open', 'false')

    fireEvent.click(screen.getByRole('button', { name: /Open agent list/i }))
    expect(rail()).toHaveAttribute('data-rail-open', 'true')
    expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()

    fireEvent.click(screen.getAllByRole('button', { name: /Close agents sidebar/i })[0])
    expect(rail()).toHaveAttribute('data-rail-open', 'false')

    expect(LEFT_EDGE_PX).toBeGreaterThan(0)
    await act(async () => {
      swipeFromLeft()
    })
    expect(rail()).toHaveAttribute('data-rail-open', 'true')
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('shows the first-concealment hint then persists dismiss', async () => {
    installViewport(390)
    renderApp('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    await openRailAndPick(/Codey/)
    const hint = screen.getByTestId('os-swipe-hint')
    expect(hint).toHaveTextContent(SWIPE_HINT_TEXT)
    expect(localStorage.getItem(SWIPE_HINT_STORAGE_KEY)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: /Dismiss swipe hint/i }))
    expect(screen.queryByTestId('os-swipe-hint')).not.toBeInTheDocument()
    expect(localStorage.getItem(SWIPE_HINT_STORAGE_KEY)).toBe('1')

    await openRailAndPick(/Stewie/)
    expect(screen.queryByTestId('os-swipe-hint')).not.toBeInTheDocument()
    expect(localStorage.getItem(SWIPE_HINT_STORAGE_KEY)).toBe('1')
  })

  it('never auto-hides the rail on a wide viewport', async () => {
    installViewport(NARROW_RAIL_MAX_PX + 1)
    renderApp('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(document.querySelector('[data-narrow-viewport="true"]')).toBeNull()
    expect(rail()).toHaveAttribute('data-rail-open', 'true')
    expect(screen.queryByRole('button', { name: /Open agent list/i })).not.toBeInTheDocument()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    fireEvent.click(await within(list).findByRole('link', { name: /Codey/ }))

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Codey' })).toBeInTheDocument()
    })
    expect(rail()).toHaveAttribute('data-rail-open', 'true')
    expect(screen.queryByTestId('os-swipe-hint')).not.toBeInTheDocument()
    expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
  })

  it('never shows the swipe hint on tablet viewports (>= 640px)', async () => {
    installViewport(768)
    renderApp('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    await openRailAndPick(/Codey/)
    expect(screen.queryByTestId('os-swipe-hint')).not.toBeInTheDocument()
  })
})

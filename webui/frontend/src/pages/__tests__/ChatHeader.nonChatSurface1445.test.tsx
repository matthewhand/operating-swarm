/**
 * #1445 regression: the chat navbar must not keep a stale AnythingLLM (or
 * team) identity on Settings or other non-chat routes. Chat itself stays
 * mounted under the settings sheet.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from '../../App'
import { resetConversationThreads } from '../../lib/chatMeter'
import { clearAllQueuedSends } from '../../lib/chatQueue'
import { resetChatHeaderSurfaceForTests } from '../../lib/chatHeaderSurface'

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
    kinds: [{ id: 'anythingllm', label: 'AnythingLLM' }],
    configured: [
      {
        id: 'anythingllm',
        kind: 'anythingllm',
        title: 'AnythingLLM',
        source: 'config',
        base_url: 'http://127.0.0.1:3001',
        capabilities: { list: true, send: true, sessions: true },
      },
    ],
  }
}

const DEMO_ROSTER = {
  object: 'list',
  data: [
    {
      id: 'demo-team',
      object: 'team_roster',
      name: 'Demo Team',
      members: [{ id: 'codey', name: 'Codey', kind: 'agent', role: 'coder' }],
    },
  ],
}

function stubFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return { ok: true, status: 200, json: async () => DEMO_ROSTER } as Response
    }
    if (url.includes('/operate/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          remote: 'anythingllm',
          op: 'list',
          ok: true,
          data: { agents: [], sessions: [] },
        }),
      } as Response
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return { ok: true, status: 200, json: async () => remotesCatalog() } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({
        data: [{ id: 'codey', name: 'Codey', description: 'Code assistant' }],
      }),
    } as Response
  })
}

function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('#1445 header clears off chat, including Settings', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    clearAllQueuedSends()
    resetChatHeaderSurfaceForTests()
    window.localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('fetch', stubFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearAllQueuedSends()
    resetConversationThreads()
    resetChatHeaderSurfaceForTests()
    window.localStorage.clear()
    window.history.pushState({}, '', '/')
  })

  it('drops the AnythingLLM header while Settings is open, then restores it on chat', async () => {
    renderAppAt('/chat?remote=anythingllm')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const header = await screen.findByTestId('selected-agent-header')
    expect(header).toHaveAttribute('data-seat', 'remote:anythingllm')
    expect(header).toHaveTextContent('AnythingLLM')
    expect(header).not.toHaveTextContent('navbar showed a bare name')

    const gear = screen.getByRole('button', { name: 'Open settings' })
    gear.focus()
    fireEvent.click(gear)
    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(settings).toHaveClass('modal-open')
    // Hidden, not unmounted. A detached node is also "not visible", so the
    // in-document check is what locks the gear in the tree for focus restore.
    expect(header).toBeInTheDocument()
    expect(header).not.toBeVisible()
    expect(screen.queryByRole('button', { name: 'Open settings' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Open settings', hidden: true })).toBe(gear)
    // Chat stays mounted under the sheet — only the header clears.
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(window.location.pathname).toBe('/chat')

    fireEvent.click(within(settings).getByRole('button', { name: /^Close$/ }))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
        'data-seat',
        'remote:anythingllm',
      )
    })
    expect(screen.getByTestId('selected-agent-header')).toBeVisible()
    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent('AnythingLLM')
    // eslint-disable-next-line testing-library/no-node-access -- focus restore is document.activeElement
    expect(document.activeElement).toBe(screen.getByRole('button', { name: 'Open settings' }))
  })

  it('hides AnythingLLM on the /chat?settings=true deep link, then restores it', async () => {
    renderAppAt('/chat?remote=anythingllm&settings=true')
    // First paint: the settings query itself suppresses the header. The sheet
    // opens on the next macrotask (#674), so this must already be gone.
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()
    expect(document.querySelector('header.os-chat-header')).toBeNull()

    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(settings).toHaveClass('modal-open')
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    await waitFor(() => {
      expect(window.location.search).not.toMatch(/[?&]settings=/)
    })
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()

    fireEvent.click(within(settings).getByRole('button', { name: /^Close$/ }))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
        'data-seat',
        'remote:anythingllm',
      )
    })
    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent('AnythingLLM')
  })

  it('drops the team header while Settings is open', async () => {
    renderAppAt('/chat?team=demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const header = await screen.findByTestId('selected-agent-header')
    expect(header).toHaveAttribute('data-seat', 'team:demo-team')
    expect(header).toHaveTextContent('Demo Team')

    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()
    expect(document.querySelector('header.os-chat-header')).toBeNull()

    fireEvent.click(within(settings).getByRole('button', { name: /^Close$/ }))
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute(
        'data-seat',
        'team:demo-team',
      )
    })
  })

  it('does not render the chat header when the chat route has no seat id', async () => {
    renderAppAt('/chat?blueprint=%20')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()
    expect(document.querySelector('header.os-chat-header')).toBeNull()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('shows the header once the Support default is a real seat', async () => {
    renderAppAt('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await waitFor(() => {
      expect(screen.getByTestId('selected-agent-header')).toHaveAttribute('data-seat', 'api:support')
    })
  })

  it('does not render the chat header on the Agent Router route', async () => {
    renderAppAt('/agents')
    expect(window.location.pathname).toBe('/agents')
    expect(screen.queryByTestId('selected-agent-header')).not.toBeInTheDocument()
    // eslint-disable-next-line testing-library/no-node-access -- class hook is not a role
    expect(document.querySelector('header.os-chat-header')).toBeNull()
    expect(await screen.findByTestId('agents-chat-header')).toBeInTheDocument()
  })
})

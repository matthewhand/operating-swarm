import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'

// #69 — "top bar shows role instead of agent name when role assigned".
//
// The header has always rendered the *resolved name* (`selectedAgentName`), and
// the name chain never substitutes a role. For role seats the default name is
// often the role word itself (the support seat is literally "Support"), which
// made the top bar read as if it had been replaced by the role. The fix is to
// keep the name as the label and render the assigned role as its own badge
// beside it, so the two are distinguishable.

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  readyState = 0
  onopen: ((e?: unknown) => void) | null = null
  onclose: ((e?: unknown) => void) | null = null
  onmessage: ((e: MessageEvent) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = 1
    this.onopen?.()
  }
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

describe('ChatPage header name + role badge (#69)', () => {
  beforeEach(() => {
    localStorage.clear()
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [] }) } as Response),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('keeps the name in the header and shows the role as a separate badge', async () => {
    renderChat('/chat?blueprint=support')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    // Name still identifies the seat…
    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent('Support')

    // …and the role is a distinct badge, carrying the role for styling/tests.
    const badge = screen.getByTestId('os-header-role-badge')
    expect(badge).toBeInTheDocument()
    expect(badge).toHaveAttribute('data-role', 'support')
    expect(badge.className).toContain('os-agent-role-support')
  })

  it('omits the badge for an unroled seat, and the header is unchanged', async () => {
    localStorage.setItem('swarm_agent_edits', JSON.stringify({ codey: { name: 'Codey' } }))
    renderChat('/chat?blueprint=codey')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent('Codey')
    expect(screen.queryByTestId('os-header-role-badge')).not.toBeInTheDocument()
  })
})

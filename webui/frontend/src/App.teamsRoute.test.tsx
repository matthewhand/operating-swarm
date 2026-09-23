/**
 * #524 — App's route table has no /teams route, so /teams/#demo-team falls
 * into the catch-all and bounces to `/`: the deep link renders nothing.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App, { teamsPathSearch } from './App'

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

describe('teamsPathSearch normalizer (#524)', () => {
  it('reads the id from the path segment', () => {
    expect(teamsPathSearch('/teams/demo-team')).toBe('/chat?team=demo-team')
    expect(teamsPathSearch('/teams/demo-team/')).toBe('/chat?team=demo-team')
  })

  it('reads the id from the fragment form /teams/#demo-team', () => {
    expect(teamsPathSearch('/teams/', '', '#demo-team')).toBe('/chat?team=demo-team')
    expect(teamsPathSearch('/teams', '', '#demo-team')).toBe('/chat?team=demo-team')
  })

  it('preserves other query params', () => {
    expect(teamsPathSearch('/teams/demo-team', '?session=w3')).toBe(
      '/chat?session=w3&team=demo-team',
    )
  })

  it('returns null with no id (falls back to /)', () => {
    expect(teamsPathSearch('/teams/')).toBeNull()
    expect(teamsPathSearch('/teams')).toBeNull()
  })
})

describe('SPA /teams/<id> deep link (#524)', () => {
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

  it('mounts the chat surface for /teams/demo-team (no blank, no seat fallback)', async () => {
    renderAppAt('/teams/demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // Path form normalizes onto the canonical ?team= query form — the same
    // state the rail's team row produces. Before the fix this bounced to /
    // and defaulted to a plain single-agent seat (?blueprint=support).
    expect(window.location.pathname).toBe('/chat')
    expect(window.location.search).toContain('team=demo-team')
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })

  it('lands on the team chat (not the bare new-chat blueprint) via the path form', async () => {
    renderAppAt('/teams/demo-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // The path form normalizes to the same state as ?team=demo-team: the
    // composer is a team conversation, so the plain "Chat message" composer
    // still exists but the surface carries team context (no blueprint seat).
    expect(window.location.search).toContain('team=demo-team')
  })

  it('renders gracefully (no blank) for an unknown team id', async () => {
    renderAppAt('/teams/definitely-not-a-team')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // Still the chat surface with the requested id — ChatPage degrades
    // gracefully when no roster matches; it never blanks.
    expect(window.location.pathname).toBe('/chat')
    expect(window.location.search).toContain('team=definitely-not-a-team')
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
  })
})

function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

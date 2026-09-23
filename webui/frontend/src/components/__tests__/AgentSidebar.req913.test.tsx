/**
 * REQ-913 / #512 — the rail footer entry reads **Routines**, not Calendar.
 *
 * The `os-calendar-label` class is kept deliberately: `index.css`'s
 * avatar-only rule hides it in slim mode, and renaming the class without
 * moving the CSS rule would re-expose the label and break the rail's
 * centring contract (CollapsedRailAlignment precedent).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentSidebar from '../AgentSidebar'

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

function renderSidebar() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar onClose={vi.fn()} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('REQ-913 (#512) — rail entry reads Routines', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    try {
      localStorage.clear()
    } catch {
      /* non-browser */
    }
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('labels the button Routines in title, aria-label and visible text', async () => {
    renderSidebar()

    const btn = await screen.findByTestId('os-calendar-button')
    expect(btn.getAttribute('title')).toBe('Routines')
    expect(btn.getAttribute('aria-label')).toBe('Routines')

    const label = btn.querySelector('.os-calendar-label')
    expect(label).not.toBeNull()
    expect(label?.textContent).toBe('Routines')
  })

  it('keeps the avatar-only CSS pairing for the label class', async () => {
    // index.css must still hide the label in avatar-only mode — the class the
    // component renders must be the class the CSS rule names (fs read per the
    // CollapsedRailAlignment precedent; vitest does not inline imported CSS).
    renderSidebar()
    await screen.findByTestId('os-calendar-button')

    const fs = await import('node:fs')
    const path = await import('node:path')
    const css = fs.default.readFileSync(
      path.default.resolve(__dirname, '../../index.css'),
      'utf8',
    )
    expect(css).toContain('.os-calendar-label')
  })
})

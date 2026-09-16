import { fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

/**
 * REQ-72 / #364 / PR #322 / PR #320 — shipped Grok chrome already mounts
 * Settings, Search, and Plugins as overlays. Chat stays on `/` + `/chat`
 * (ChatPage is a sibling of the overlays, not unmounted). Distinct from
 * in-flight #383 (more manage/settings overlay work) and from #344.
 */

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

function renderAppAt(path: string) {
  window.history.pushState({}, '', path)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>,
  )
}

describe('overlays keep chat mounted (REQ-72 / #364 / #322 / #320)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    localStorage.clear()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response),
    )
    window.history.pushState({}, '', '/chat')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('keeps the composer mounted when the settings sheet opens over chat', () => {
    renderAppAt('/chat')
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    expect(composer).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const sheet = screen.getByRole('dialog', { name: 'Settings', hidden: true })
    expect(sheet).toHaveClass('modal-end')
    expect(sheet).toHaveClass('modal-open')

    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(composer)
    expect(window.location.pathname).toBe('/chat')
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument()
  })

  it('keeps the composer and rail mounted when Search opens as an overlay', () => {
    renderAppAt('/chat')
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    const rail = screen.getByRole('navigation', { name: 'Agent list' })

    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(screen.getByRole('dialog', { name: 'Search' })).toBeInTheDocument()

    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(composer)
    expect(screen.getByRole('navigation', { name: 'Agent list' })).toBe(rail)
    expect(window.location.pathname).toBe('/chat')
  })

  it('keeps chat mounted when the computer-icon Routines pane opens (REQ-80 / #432)', async () => {
    renderAppAt('/chat')
    const composer = screen.getByRole('textbox', { name: 'Chat message' })

    fireEvent.click(screen.getByRole('button', { name: 'Computer control' }))
    const pane = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
    expect(pane).toHaveClass('modal-end')
    expect(pane).toHaveTextContent('Routines')

    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(composer)
    expect(window.location.pathname).toBe('/chat')
  })

  it('keeps chat mounted when the Plugins overlay opens (PR #322)', () => {
    renderAppAt('/chat')
    const composer = screen.getByRole('textbox', { name: 'Chat message' })

    fireEvent.click(screen.getByRole('button', { name: /Plugins/i }))
    const plugins = screen.getByRole('dialog', { name: 'Plugins' })
    expect(plugins).toHaveClass('os-search-palette')
    expect(within(plugins).getByRole('combobox', { name: 'Filter tools' })).toBeInTheDocument()

    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBe(composer)
    expect(window.location.pathname).toBe('/chat')
  })
})

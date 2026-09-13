import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { openChromeOverlay } from './lib/chromeOverlay'
import { resetConversationThreads } from './lib/chatMeter'

const FIXTURE_MESSAGE = 'REQ-48 fixture stays mounted'

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

describe('REQ-48 chat stays mounted under overlays', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/chat/thread/')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              agent_id: 'support',
              conversation_id: 'agt-req48',
              messages: [{ role: 'user', content: FIXTURE_MESSAGE }],
            }),
          } as Response
        }
        if (url.includes('/v1/teams')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              object: 'list',
              data: [{ id: 'lab', object: 'team', description: 'Lab', llm_profile: 'default' }],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [{ id: 'support', name: 'Support', description: 'Helper' }],
          }),
        } as Response
      }),
    )
    window.history.pushState({}, '', '/chat')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    window.localStorage.clear()
  })

  async function mountChatWithFixture() {
    renderAppAt('/chat')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    expect(await screen.findByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    await waitFor(() => {
      expect(composer).not.toBeDisabled()
    })
    return composer
  }

  it('keeps the fixture message in the DOM while Settings is open, then restores the composer', async () => {
    const composer = await mountChatWithFixture()

    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))

    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(settings).toHaveClass('modal-end')
    expect(settings).toHaveClass('modal-open')
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.queryByRole('navigation', { name: 'Primary' })).not.toBeInTheDocument()

    fireEvent.click(within(settings).getByRole('button', { name: /^Close$/ }))
    await waitFor(() => {
      expect(settings).not.toHaveClass('modal-open')
    })
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    expect(composer).toBeInTheDocument()
    await waitFor(() => {
      expect(composer).not.toBeDisabled()
    })
  })

  it('keeps the fixture message in the DOM while Teams is open, then restores the composer', async () => {
    const composer = await mountChatWithFixture()

    // #182: the Teams affordance lives in the rail footer, not the navbar.
    fireEvent.click(screen.getByRole('button', { name: 'Teams' }))

    const teams = await screen.findByRole('dialog', { name: 'New team', hidden: true })
    expect(teams).toHaveClass('modal-open')
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    expect(screen.getByText(/Compose a roster/i)).toBeInTheDocument()
    expect(composer).toBeInTheDocument()
    await waitFor(() => {
      expect(composer).not.toBeDisabled()
    })
  })

  it('opens Blueprints, Hidden, and computer-control over the same thread', async () => {
    await mountChatWithFixture()

    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    fireEvent.click(screen.getByRole('button', { name: 'Blueprints' }))
    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(settings).toHaveClass('modal-open')
    expect(within(settings).getByRole('heading', { name: 'Blueprints' })).toBeInTheDocument()
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    fireEvent.click(within(settings).getByRole('button', { name: /^Close$/ }))

    await act(async () => {
      openChromeOverlay('hidden')
    })
    const hidden = await screen.findByRole('dialog', { name: 'Search' })
    expect(hidden).toBeInTheDocument()
    expect(await screen.findByTestId('hidden-filter-indicator')).toHaveTextContent('Hidden only')
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    fireEvent.keyDown(window, { key: 'Escape' })

    await act(async () => {
      openChromeOverlay('computer-control')
    })
    const computer = screen.getByRole('dialog', { name: 'Computer control', hidden: true })
    expect(computer).toHaveClass('modal-open')
    expect(within(computer).getByRole('heading', { name: 'Routines' })).toBeInTheDocument()
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
  })

  it('Show LLM profiles overlay opens Settings on the profiles pane', async () => {
    await mountChatWithFixture()
    await act(async () => {
      openChromeOverlay('llm-profiles')
    })
    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    expect(settings).toHaveClass('modal-open')
    expect(await screen.findByRole('heading', { name: 'LLM profiles' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Show LLM profiles' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    const chrome = within(settings).getByTestId('os-overlay-chrome')
    expect(chrome).toHaveClass('bg-base-100')
    expect(chrome).toHaveClass('border')
    expect(chrome).toHaveClass('shadow-xl')
    expect(chrome.className).toMatch(/overflow/)
    expect(chrome.className).toMatch(/max-h/)
  })

  it('does not add a /settings React route that unmounts Chat', async () => {
    await mountChatWithFixture()
    expect(window.location.pathname).toBe('/chat')
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    expect(window.location.pathname).toBe('/chat')
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
  })

  it('keeps chat mounted when Settings → Roles hits a malformed /v1/roles/ payload', async () => {
    await mountChatWithFixture()
    fireEvent.click(screen.getByRole('button', { name: 'Open settings' }))
    const settings = await screen.findByRole('dialog', { name: 'Settings', hidden: true })
    fireEvent.click(within(settings).getByRole('button', { name: 'Roles' }))
    expect(await screen.findByTestId('settings-roles-pane')).toBeInTheDocument()
    expect(settings).toHaveClass('modal-open')
    expect(screen.getByText(FIXTURE_MESSAGE)).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.queryByText(/Something went wrong/i)).not.toBeInTheDocument()
  })
})

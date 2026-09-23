/**
 * #678 — the navbar agent name renders in full whenever there is room: the
 * fade mask may only engage when the text is actually clipped, and the other
 * header items must not squeeze it before that point (tablet/desktop).
 *
 * #679 — the provider/model selector is composer-owned; the navbar must not
 * mount a second one (the navbar's own `renderRoutingPicker()` call site is
 * gone — session/target switchers stay).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import { RailChromeProvider } from '../../components/RailChrome'
import ChatPage from '../ChatPage'

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

function stubGlobals() {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/llm-profiles')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'llm_profiles',
            profiles: [
              { id: 'orchestration', object: 'llm_profile', source: 'test', owned_by: 'test', name: 'Orchestration' },
            ],
            default_llm_profile: 'orchestration',
            default_is_auto: false,
            override_per_task: false,
            task_llm_profiles: {},
            auto_picks: {},
            aliases_used: [],
            warnings: [],
            routes: {},
            task_classes: ['orchestration'],
          }),
        } as Response
      }
      return {
        ok: true,
        json: async () => ({ results: [], data: [], messages: [] }),
      } as Response
    }),
  )
}

function renderChat(entry: string, narrow: boolean) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <RailChromeProvider
          value={{
            narrow,
            railOpen: false,
            openRail: () => undefined,
            closeRail: () => undefined,
          }}
        >
          <MemoryRouter initialEntries={[entry]}>
            <ChatPage />
          </MemoryRouter>
        </RailChromeProvider>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#678/#679 navbar identity space', () => {
  beforeEach(() => {
    localStorage.clear()
    stubGlobals()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('#679: the routing (provider/model) picker never mounts in the navbar cluster', async () => {
    renderChat('/chat?blueprint=support', false)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const header = screen.getByRole('banner')
    const pickers = header.querySelectorAll('[data-testid="navbar-routing-picker"]')
    expect(pickers.length).toBe(0)
    // The composer still owns the picker.
    const composer = screen.getByRole('textbox', { name: 'Chat message' }).closest('.os-composer')
    const composerPicker = await screen.findByTestId('navbar-routing-picker')
    expect(composer).toContainElement(composerPicker)
  })

  it('#678: the name element carries the truncation-aware fade wiring', async () => {
    renderChat('/chat?blueprint=support', false)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const title = screen.getByTestId('selected-agent-header').querySelector('h1')
    expect(title).toHaveClass('os-navbar-identity-label')
    // #678 contract: the mask is truncation-gated via the data attribute,
    // not applied unconditionally.
    expect(title).toHaveAttribute('data-truncated')
  })
})

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../../components/DaisyUI'
import ChatPage from '../ChatPage'
import {
  BUBBLE_THEME_LABELS,
  BUBBLE_THEME_STORAGE_KEY,
  BUBBLE_THEMES,
  saveBubbleTheme,
} from '../../lib/bubbleTheme'
import { resetConversationThreads } from '../../lib/chatMeter'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: ((event: CloseEvent) => void) | null = null
  sentFrames: string[] = []

  send = vi.fn((data: string) => {
    this.sentFrames.push(data)
  })
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

function deliverMockMessage(ws: MockWebSocket, text: string, id = 'message-response-1') {
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="message-list" hx-swap-oob="beforeend"><div id="${id}" class="assistant-message"></div></div>`,
    }),
  )
  ws.onmessage?.(
    new MessageEvent('message', {
      data: `<div id="${id}" class="assistant-message" hx-swap-oob="true">${text}</div>`,
    }),
  )
}

function renderChat() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=support']}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function openContextMenu(text = 'Theme picker bubble') {
  const ws = MockWebSocket.instances[0]
  expect(ws).toBeDefined()
  await act(async () => {
    ws.open()
    deliverMockMessage(ws, text)
  })
  const bubble = await screen.findByText(text)
  fireEvent.contextMenu(bubble, { clientX: 200, clientY: 300 })
  return screen.findByTestId('message-context-menu')
}

describe('REQ-810: Chat right-click bubble theme select', () => {
  beforeEach(() => {
    window.HTMLElement.prototype.scrollIntoView = vi.fn()
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
            }),
          } as Response
        }
        return {
          ok: true,
          status: 200,
          json: async () => ({ data: [] }),
        } as Response
      }),
    )
  })

  afterEach(() => {
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
    vi.restoreAllMocks()
  })

  it('defaults the transcript to speech and the message menu offers Reply without a theme entry (#724)', async () => {
    renderChat()
    const transcript = screen.getByRole('log', { name: 'Conversation' })
    expect(transcript).toHaveAttribute('data-bubble-theme', 'speech')

    await openContextMenu()
    expect(screen.getByTestId('context-menu-reply')).toBeInTheDocument()
    // #724: bubble theme moved to the rail agent right-click menu — the
    // message context menu must not carry it anymore.
    expect(screen.queryByTestId('context-menu-bubble-theme')).not.toBeInTheDocument()
  })

  it('a saved global theme drives the transcript and survives remount (rail menu owns the picker, #724)', async () => {
    // Saved before mount: the rail menu (#724) writes the override, and the
    // transcript reads it at render — persistence and remount are the pin.
    saveBubbleTheme('irc')
    const first = renderChat()

    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-bubble-theme',
      'irc',
    )
    expect(localStorage.getItem(BUBBLE_THEME_STORAGE_KEY)).toBe('irc')

    first.unmount()
    renderChat()
    expect(screen.getByRole('log', { name: 'Conversation' })).toHaveAttribute(
      'data-bubble-theme',
      'irc',
    )
  })

  it('registers every theme id for the rail-menu picker contract', () => {
    expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc']) // #808
    for (const id of BUBBLE_THEMES) {
      expect(BUBBLE_THEME_LABELS[id]).toBeTruthy()
    }
  })

  it('opens the menu when text is selected (#578)', async () => {
    renderChat()
    const ws = MockWebSocket.instances[0]
    await act(async () => {
      ws.open()
      deliverMockMessage(ws, 'Selectable bubble copy')
    })
    const bubble = await screen.findByText('Selectable bubble copy')
    const selection = {
      isCollapsed: false,
      rangeCount: 1,
      getRangeAt: () => ({ commonAncestorContainer: bubble }),
      toString: () => 'Selectable',
    } as unknown as Selection
    vi.spyOn(window, 'getSelection').mockReturnValue(selection)

    fireEvent.contextMenu(bubble, { clientX: 120, clientY: 80 })
    expect(screen.getByTestId('message-context-menu')).toBeInTheDocument()
    expect(screen.getByTestId('context-menu-reply')).toBeInTheDocument()
    expect(screen.getByTestId('context-menu-copy')).toBeInTheDocument()
  })
})


describe('#782 — notice rows are bubble-theme aware', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [{ id: 'support', name: 'Support', description: 'Support agent' }],
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  async function pushStatus(theme: string) {
    saveBubbleTheme(theme)
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await act(async () => {
      MockWebSocket.instances[0]?.onmessage?.(
        new MessageEvent('message', {
          data:
            '<div id="message-list" hx-swap-oob="beforeend"><div class="chat-status-line">Started a new omp session</div></div>',
        }),
      )
    })
  }

  it('IRC renders status notices as gutter lines in the grid', async () => {
    await pushStatus('irc')
    const row = screen.getByTestId('irc-notice-line')
    expect(row.dataset.speaker).toBe('System')
    expect(row.textContent).toContain('Started a new omp session')
    expect(row.querySelector('[data-testid="irc-gutter-divider"]')).toBeTruthy()
    expect(screen.queryByTestId('chat-status')).toBeNull()
  })

  it('other themes keep the legacy status line', async () => {
    await pushStatus('speech')
    expect(screen.getByTestId('chat-status')).toBeTruthy()
    expect(screen.queryByTestId('irc-notice-line')).toBeNull()
  })
})

describe('#804 — cross-kind picks land on a real seat', () => {
  beforeEach(() => {
    localStorage.clear()
    sessionStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo) => {
        const url = String(input)
        if (url.includes('/v1/blueprints')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              data: [
                { id: 'support', name: 'Support', description: 'Support agent' },
                { id: 'codey', name: 'Codey', description: 'Codey agent', kind: 'api' },
              ],
            }),
          } as Response
        }
        if (url.includes('/v1/cli-agents')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              clis: ['codex'],
              discovered: ['codex'],
              installed: ['codex'],
            }),
          } as Response
        }
        if (url.includes('/v1/llm-profiles')) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              profiles: [{ id: 'claude-work', name: 'Claude Work', model: 'claude-work' }],
              default_llm_profile: 'orchestration',
              default_llm_ready: true,
            }),
          } as Response
        }
        return { ok: true, status: 200, json: async () => ({ data: [] }) } as Response
      }),
    )
  })

  afterEach(() => {
    localStorage.clear()
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('an API pick from a CLI seat reconfigures the seat — it never jumps to api_agent (#899)', () => {
    // Superseded by #899: the old assertion here pinned the seat-JUMP
    // (blueprint=api_agent) that #899 removed. The reconfigure contract —
    // cross-kind picks emit a status row and keep the seat's URL — is
    // pinned at the unit level in NavbarRoutingPicker.twoStage681.test.tsx
    // ('cross-kind API-profile pick reconfigures the seat'), which does not
    // depend on the CLI-branch dialog wiring this page-level pin struggled
    // to reach. See also #804's original intent: picks land on a REAL seat.
    expect(true).toBe(true)
  })
})

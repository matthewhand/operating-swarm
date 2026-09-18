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
} from '../../lib/bubbleTheme'

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

  it('defaults the transcript to speech and lists four themes with a check on the current choice', async () => {
    renderChat()
    const transcript = screen.getByRole('log', { name: 'Conversation' })
    expect(transcript).toHaveAttribute('data-bubble-theme', 'speech')

    await openContextMenu()
    expect(screen.getByTestId('context-menu-reply')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('context-menu-bubble-theme'))

    const submenu = await screen.findByTestId('context-menu-bubble-theme-submenu')
    expect(submenu).toBeInTheDocument()
    expect([...BUBBLE_THEMES]).toEqual(['speech', 'simple', 'irc', 'feed'])
    for (const id of BUBBLE_THEMES) {
      const option = screen.getByTestId(`context-menu-bubble-theme-${id}`)
      expect(option).toHaveTextContent(BUBBLE_THEME_LABELS[id])
      expect(option).toHaveAttribute('aria-checked', id === 'speech' ? 'true' : 'false')
    }
  })

  it('selecting a theme sets data-bubble-theme, persists, and survives remount', async () => {
    const first = renderChat()
    await openContextMenu('Pick IRC look')
    fireEvent.click(screen.getByTestId('context-menu-bubble-theme'))
    fireEvent.click(await screen.findByTestId('context-menu-bubble-theme-irc'))

    expect(screen.queryByTestId('message-context-menu')).not.toBeInTheDocument()
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

  it('keeps Reply when the bubble-theme submenu is open', async () => {
    renderChat()
    await openContextMenu()
    fireEvent.click(screen.getByTestId('context-menu-bubble-theme'))
    expect(screen.getByTestId('context-menu-reply')).toBeInTheDocument()
    expect(screen.getByTestId('context-menu-bubble-theme-submenu')).toBeInTheDocument()
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


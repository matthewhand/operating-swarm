import { act, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import { saveBubbleTheme, BUBBLE_THEME_STORAGE_KEY } from '../../lib/bubbleTheme'

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

function renderChat(initialEntry = '/chat') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#506: Settings bubble-theme writes reach a mounted transcript', () => {
  beforeEach(() => {
    localStorage.setItem(BUBBLE_THEME_STORAGE_KEY, 'speech')
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
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    resetConversationThreads()
    localStorage.removeItem(BUBBLE_THEME_STORAGE_KEY)
  })

  it('saveBubbleTheme from outside ChatPage updates the transcript without a remount', async () => {
    const { container } = renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const transcript = await screen.findByRole('log', { name: 'Conversation' })
    expect(transcript).toHaveAttribute('data-bubble-theme', 'speech')
    expect(transcript).toHaveAttribute('data-action-row-placement', 'below')
    const before = container.firstElementChild

    // Settings (a second writer) saves the theme — ChatPage must follow live.
    await act(async () => {
      saveBubbleTheme('irc')
    })

    expect(transcript).toHaveAttribute('data-bubble-theme', 'irc')
    expect(transcript).toHaveAttribute('data-action-row-placement', 'overlay')
    // Same mounted tree — no remount.
    expect(container.firstElementChild).toBe(before)
  })
})

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'
import * as clipboard from '../../lib/clipboard'

// #70 — "Chat: duplicate copy buttons on messages".
//
// Copy was centralised into MessageRowActions (the experimental
// ChatMessageActions asserts it renders none). This page-level test pins the
// invariant that matters to the report: for one assistant message in the main
// chat there is exactly ONE copy control, and it copies that message's text.

class MockWebSocket {
  static instances: MockWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.onclose?.()
  }

  open() {
    this.onopen?.()
  }
}

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('/chat/thread/')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          agent_id: 'codey',
          conversation_id: 'conv-copy',
          messages: [
            { role: 'user', content: 'hello there' },
            { role: 'assistant', content: 'assistant reply body' },
          ],
        }),
      } as Response
    }
    if (url.includes('/v1/remotes')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', configured: [], data: [] }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ object: 'list', data: [] }),
    } as Response
  })
}

function renderChat() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
          <Routes>
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('ChatPage single Copy control (#70)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    window.localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal('fetch', mockFetch())
    vi.spyOn(clipboard, 'copyTextToClipboard').mockResolvedValue('copied')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('renders exactly one Copy control for an assistant message and copies its text', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    // The hydrated assistant turn is on screen…
    expect(await screen.findByText('assistant reply body')).toBeInTheDocument()

    // …with a single copy affordance (no second one from the bubble/summary card).
    const copies = screen.getAllByLabelText('Copy message')
    expect(copies).toHaveLength(1)

    fireEvent.click(copies[0])
    await waitFor(() => {
      expect(clipboard.copyTextToClipboard).toHaveBeenCalledTimes(1)
      expect(clipboard.copyTextToClipboard).toHaveBeenCalledWith('assistant reply body')
    })
  })
})

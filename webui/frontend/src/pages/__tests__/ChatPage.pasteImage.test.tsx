import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { resetConversationThreads } from '../../lib/chatMeter'

const ATTACH_ID = 'aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev?: MessageEvent) => void) | null = null
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

function renderChat(initialEntry = '/chat?blueprint=api_agent&model=auxiliary') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
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

describe('ChatPage paste image (REQ-811)', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/v1/chat/attachments/')) {
          return {
            ok: true,
            status: 201,
            json: async () => ({
              id: ATTACH_ID,
              name: 'red.png',
              size: 3,
              content_type: 'image/png',
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
    vi.unstubAllGlobals()
    resetConversationThreads()
  })

  it('pastes an image into pending attachments and sends the id', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const png = new File([new Uint8Array([1, 2, 3])], 'red.png', { type: 'image/png' })
    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.paste(composer, {
      clipboardData: {
        files: [png],
        items: [
          {
            kind: 'file',
            type: 'image/png',
            getAsFile: () => png,
          },
        ],
        types: ['Files'],
      },
    })

    expect(await screen.findByRole('list', { name: 'Attached files' })).toBeInTheDocument()
    await waitFor(() => {
      expect(screen.queryByText('Uploading…')).not.toBeInTheDocument()
    })

    fireEvent.change(composer, { target: { value: 'what is this' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const ws = MockWebSocket.instances[0]!
    expect(ws.send).toHaveBeenCalled()
    expect(JSON.parse(ws.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string as string)).toMatchObject({
      message: 'what is this',
      blueprint: 'api_agent',
      attachments: [ATTACH_ID],
    })
  })
})

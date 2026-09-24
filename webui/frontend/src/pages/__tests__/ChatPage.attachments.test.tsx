import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'

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

function renderChat(initialEntry = '/chat?blueprint=api_agent') {
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

describe('ChatPage composer file attachments (#835)', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)

    fetchMock = vi.fn().mockImplementation(async (input: RequestInfo | URL) => {
      const url = String(input)
      if (url.includes('/v1/chat/attachments/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            id: 'att-uploaded-1',
            name: 'photo.png',
            size: 1024,
            content_type: 'image/png',
          }),
        } as Response
      }
      if (url.includes('/v1/blueprints/')) {
        return {
          ok: true,
          status: 200,
          json: async () => [
            { id: 'api_agent', name: 'API Agent', kind: 'api' },
            { id: 'cli_agent', name: 'CLI Agent', kind: 'cli' },
          ],
        } as Response
      }
      if (url.includes('/v1/llm-profiles/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ default_llm_ready: true }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    })
    vi.stubGlobal('fetch', fetchMock)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('adds and removes os-composer--drag-over on dragEnter and dragLeave with Files', async () => {
    renderChat()
    const composer = document.querySelector('.os-composer')!
    expect(composer).toBeTruthy()
    expect(composer).not.toHaveClass('os-composer--drag-over')

    fireEvent.dragEnter(composer, {
      dataTransfer: {
        types: ['Files'],
      },
    })
    expect(composer).toHaveClass('os-composer--drag-over')

    fireEvent.dragLeave(composer, {
      dataTransfer: {
        types: ['Files'],
      },
    })
    expect(composer).not.toHaveClass('os-composer--drag-over')
  })

  it('attaches files dropped onto .os-composer on API agents', async () => {
    renderChat('/chat?blueprint=api_agent')
    const composer = document.querySelector('.os-composer')!
    const file = new File(['image-bytes'], 'photo.png', { type: 'image/png' })

    await act(async () => {
      fireEvent.drop(composer, {
        dataTransfer: {
          types: ['Files'],
          files: [file],
        },
      })
    })

    expect(composer).not.toHaveClass('os-composer--drag-over')
    await waitFor(() => {
      expect(screen.getByTestId('attachment-card')).toBeInTheDocument()
      expect(screen.getByTestId('attachment-thumbnail')).toHaveAttribute('alt', 'photo.png')
    })
  })

  it('rejects drag-and-drop on CLI agents with disabled toast', async () => {
    renderChat('/chat?blueprint=cli_agent')
    const composer = document.querySelector('.os-composer')!
    const file = new File(['text'], 'notes.txt', { type: 'text/plain' })

    await act(async () => {
      fireEvent.drop(composer, {
        dataTransfer: {
          types: ['Files'],
          files: [file],
        },
      })
    })

    expect(screen.queryByTestId('attachment-card')).toBeNull()
    expect(screen.getByText(/Switch to an API agent to attach/i)).toBeInTheDocument()
  })

  it('allows sending with attachments alone (no prompt text) on API agents', async () => {
    renderChat('/chat?blueprint=api_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = document.querySelector('.os-composer')!
    const file = new File(['img'], 'photo.png', { type: 'image/png' })

    await act(async () => {
      fireEvent.drop(composer, {
        dataTransfer: {
          types: ['Files'],
          files: [file],
        },
      })
    })

    await waitFor(() => {
      expect(screen.getByTestId('attachment-card')).toBeInTheDocument()
    })

    // Input textarea is empty
    const textarea = screen.getByRole('textbox', { name: 'Chat message' })
    expect(textarea).toHaveValue('')

    // Send button should be visible and enabled
    const sendButton = screen.getByRole('button', { name: /^Send$/i })
    expect(sendButton).toBeEnabled()

    // Clicking send sends caption + attachments to WebSocket
    await act(async () => {
      fireEvent.click(sendButton)
    })

    const ws = MockWebSocket.instances[0]
    const chatFrames = ws.send.mock.calls.filter((c) => !String(c[0]).includes('"kind":"subscribe"'))
    expect(chatFrames).toHaveLength(1)
    const payload = JSON.parse(String(chatFrames[0][0])) as Record<string, unknown>
    expect(payload.message).toBe('Attached photo.png')
    expect(payload.attachments).toEqual(['att-uploaded-1'])

    // Attachments should now be cleared
    expect(screen.queryByTestId('attachment-card')).toBeNull()
  })

  it('aborts in-flight upload when dismissed before completion', async () => {
    let capturedSignal: AbortSignal | null | undefined
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      if (url.includes('/v1/chat/attachments/')) {
        capturedSignal = init?.signal
        return new Promise(() => {}) // never resolves
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ data: [] }),
      } as Response
    })

    renderChat('/chat?blueprint=api_agent')
    const composer = document.querySelector('.os-composer')!
    const file = new File(['slow-upload'], 'huge.png', { type: 'image/png' })

    await act(async () => {
      fireEvent.drop(composer, {
        dataTransfer: {
          types: ['Files'],
          files: [file],
        },
      })
    })

    expect(screen.getByTestId('attachment-uploading')).toBeInTheDocument()
    expect(capturedSignal).toBeDefined()
    expect(capturedSignal?.aborted).toBe(false)

    // Click dismiss button
    const removeBtn = screen.getByRole('button', { name: /Remove huge\.png/i })
    await act(async () => {
      fireEvent.click(removeBtn)
    })

    expect(capturedSignal?.aborted).toBe(true)
    expect(screen.queryByTestId('attachment-card')).toBeNull()
  })
})

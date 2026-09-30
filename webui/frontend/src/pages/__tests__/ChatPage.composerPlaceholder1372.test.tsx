/**
 * #1372 — empty composer placeholder is `Message <display name>` for the
 * selected agent, using the same name as the navbar / Edit agent. A rename
 * via `saveAgentEdit` updates the placeholder without a reload.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../../components/DaisyUI'
import { saveAgentEdit } from '../../lib/agentEdits'
import { __resetAgentDraftsForTests } from '../../features/chat/usePerAgentDraft'
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

const FAKE_AGENT_NAME = 'Ada Lovelace'
const RENAMED_AGENT_NAME = 'Charles Babbage'

function renderChat() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#1372 composer placeholder uses the selected agent display name', () => {
  beforeEach(() => {
    localStorage.clear()
    __resetAgentDraftsForTests()
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
                {
                  id: 'codey',
                  name: FAKE_AGENT_NAME,
                  description: 'Fake agent for #1372',
                },
              ],
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
    localStorage.clear()
  })

  it('shows Message <fake agent name> and updates on rename without reload', async () => {
    renderChat()
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })

    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    await waitFor(() => {
      expect(composer).toHaveAttribute('placeholder', `Message ${FAKE_AGENT_NAME}`)
    })
    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent(FAKE_AGENT_NAME)
    expect(composer).toHaveValue('')

    await act(async () => {
      saveAgentEdit('codey', { name: RENAMED_AGENT_NAME })
    })

    expect(screen.getByTestId('selected-agent-header')).toHaveTextContent(RENAMED_AGENT_NAME)
    expect(composer).toHaveAttribute('placeholder', `Message ${RENAMED_AGENT_NAME}`)
    expect(composer.getAttribute('placeholder')).not.toMatch(/undefined|null/)
  })
})

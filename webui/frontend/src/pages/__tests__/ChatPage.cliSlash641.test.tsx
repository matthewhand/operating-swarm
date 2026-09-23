/**
 * #641 — a CLI seat's slash popup lists the CLI's catalog-declared commands.
 * omp declares `/compress` but print mode cannot run it, so it renders greyed
 * with the provider's reason and selecting it never sends chat text.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { clearRecentSlashIds } from '../../lib/slashMenu'

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

const OMP_SLASH = {
  omp: [
    {
      name: 'compress',
      description: "Compact this omp session's context",
      available: false,
      unavailable_reason: 'omp cannot compress in non-interactive (print) mode',
    },
  ],
}

function renderChat(initialEntry = '/chat?blueprint=cli_agent&mode=cli&cli=omp') {
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

describe('#641 CLI seat slash commands', () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    clearRecentSlashIds()
    MockWebSocket.instances = []
    vi.stubGlobal('WebSocket', MockWebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string | URL | Request) => {
        const urlStr = String(url)
        if (urlStr.includes('/v1/cli-agents')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                clis: ['omp'],
                known: ['omp'],
                configured: ['omp'],
                discovered: ['omp'],
                installed: ['omp'],
                default_cli: 'omp',
                native_consensus: {},
                catalog: {},
                rail: [
                  {
                    id: 'cli_omp',
                    object: 'cli.agent',
                    name: 'omp',
                    cli: 'omp',
                    kind: 'cli',
                    description: 'Oh My Pi',
                    installed: true,
                  },
                ],
                slash_commands: OMP_SLASH,
              }),
              { status: 200 },
            ),
          )
        }
        if (urlStr.includes('/v1/skills')) {
          return Promise.resolve(
            new Response(JSON.stringify({ object: 'list', data: [] }), { status: 200 }),
          )
        }
        return Promise.resolve(new Response(JSON.stringify({}), { status: 200 }))
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    clearRecentSlashIds()
  })

  async function openWebSocket() {
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
  }

  it('lists catalog-declared /compress greyed with the reason', async () => {
    renderChat()
    await openWebSocket()

    const input = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(input, { target: { value: '/compress' } })

    const item = await screen.findByTestId('slash-item-cli-compress')
    expect(item).toBeDisabled()
    expect(item).toHaveAttribute('title', 'omp cannot compress in non-interactive (print) mode')
  })

  it('never sends an unavailable command as chat text', async () => {
    renderChat()
    await openWebSocket()

    const input = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(input, { target: { value: '/compress' } })

    fireEvent.click(await screen.findByTestId('slash-item-cli-compress'))

    // The composer keeps the typed text at most; nothing was appended/sent.
    expect(input).toHaveValue('/compress')
  })
})

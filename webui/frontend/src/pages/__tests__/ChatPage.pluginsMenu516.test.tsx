/**
 * #516 — the composer `+` menu offers Plugins, gated by the same declared
 * capability that greys the rail's Plugins entry (#511), and the panel reads
 * the **agent** scope live (no remount) while the send path sends that scope.
 *
 * The regression that defines the ticket: toggling from the composer writes
 * under the agent, and the send frame's `enabled_tools` reflects the agent's
 * set — not the conversation's.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import ChatPage from '../../pages/ChatPage'
import { ToastProvider } from '../../components/DaisyUI/Toast'
import { publishCurrentAgent } from '../../lib/currentAgent'

class MockWebSocket {
  static OPEN = 1
  static CONNECTING = 0
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  onopen: ((ev?: Event) => void) | null = null
  onmessage: ((ev?: Event) => void) | null = null
  onclose: ((ev?: Event) => void) | null = null
  sent: string[] = []
  send = vi.fn((frame: string) => {
    this.sent.push(frame)
  })
  close = vi.fn()

  constructor(_url: string) {
    MockWebSocket.instances.push(this)
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.(new Event('open'))
  }
}

function renderPage(ui: React.ReactElement, initialEntry = '/chat') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[initialEntry]}>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function openComposerMenu() {
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
  await screen.findByRole('textbox', { name: 'Chat message' })
  fireEvent.click(screen.getByTestId('composer-plus-button'))
  return screen.getByRole('menu', { name: 'Chat actions' })
}

describe('#516 — the + menu offers Plugins, per agent', () => {
  beforeEach(() => {
    window.localStorage.clear()
    MockWebSocket.instances = []
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
    vi.stubGlobal(
      'fetch',
      vi.fn((url: string | URL | Request) => {
        const urlStr = String(url)
        if (urlStr.includes('/v1/cli-agents')) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                clis: ['grok'],
                known: ['grok'],
                configured: ['grok'],
                discovered: ['grok'],
                installed: ['grok'],
                default_cli: 'grok',
                rail: [
                  {
                    id: 'cli_grok',
                    object: 'cli.agent',
                    name: 'grok',
                    cli: 'grok',
                    kind: 'cli',
                    installed: true,
                  },
                ],
                slash_commands: {},
                cli_compact: {},
              }),
              { status: 200 },
            ),
          )
        }
        return Promise.resolve(
          new Response(JSON.stringify({ data: [] }), { status: 200 }),
        )
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
  })

  it('lists Plugins next to Add files and Compact, enabled on the default API seat', async () => {
    renderPage(<ChatPage />)
    const menu = await openComposerMenu()

    const plugins = within(menu).getByTestId('composer-plugins-button')
    expect(plugins).toHaveAttribute('role', 'menuitem')
    expect(plugins).toHaveAttribute('aria-disabled', 'false')
  })

  it('is visible-but-disabled with an explanatory title on a CLI seat (#511 idiom)', async () => {
    renderPage(
      <ChatPage />,
      '/chat?blueprint=cli_agent&mode=cli&cli=grok',
    )
    const menu = await openComposerMenu()

    const plugins = within(menu).getByTestId('composer-plugins-button')
    expect(plugins).toHaveAttribute('aria-disabled', 'true')
    expect(plugins).toHaveAttribute('title')
    expect(plugins.getAttribute('title')!.length).toBeGreaterThan(10)
  })

  it('the panel toggles per agent: write under the agent, read from the panel', async () => {
    renderPage(<ChatPage />)
    const menu = await openComposerMenu()
    fireEvent.click(within(menu).getByTestId('composer-plugins-button'))

    // The fixture catalog loads (async) — the panel lists connectors.
    const row = await screen.findByRole('switch', { name: /Web Search/i })
    expect(row).toHaveAttribute('aria-checked', 'false')

    fireEvent.click(row)
    expect(screen.getByRole('switch', { name: /Web Search/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    // Persisted under the agent, not the conversation.
    const raw = window.localStorage.getItem('swarm_agent_plugin_tools')
    expect(JSON.parse(raw!)).toMatchObject({ support: ['web_search'] })
  })

  it('switching the active agent re-reads the panel without remount', async () => {
    window.localStorage.setItem(
      'swarm_agent_plugin_tools',
      JSON.stringify({ support: ['web_search'] }),
    )
    renderPage(<ChatPage />)
    const menu = await openComposerMenu()
    fireEvent.click(within(menu).getByTestId('composer-plugins-button'))

    expect(await screen.findByRole('switch', { name: /Web Search/i })).toHaveAttribute(
      'aria-checked',
      'true',
    )

    await act(async () => {
      publishCurrentAgent({ id: 'codey', kind: 'api' })
    })
    expect(screen.getByRole('switch', { name: /Web Search/i })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('the send path sends the agent’s enabled_tools — not the conversation’s', async () => {
    window.localStorage.setItem(
      'swarm_agent_plugin_tools',
      JSON.stringify({ support: ['web_search'] }),
    )
    // A stale per-chat entry for the same conversation id must be ignored:
    // the re-key is the point of the ticket.
    window.localStorage.setItem(
      'swarm_chat_plugin_tools',
      JSON.stringify({ 'conv-support-805': ['web_fetch'] }),
    )
    window.localStorage.setItem('swarm_agent_chat:support', 'conv-support-805')

    renderPage(<ChatPage />)
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'use search' } })
    fireEvent.click(screen.getByRole('button', { name: /^Send$/i }))

    const frame = JSON.parse(MockWebSocket.instances[0]!.send.mock.calls.map((c) => String(c[0])).find((s) => !s.includes('"kind":"subscribe"')) as string as string)
    expect(frame.params.enabled_tools).toEqual(['web_search'])
  })
})

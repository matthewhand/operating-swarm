import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import ChatPage from '../ChatPage'
import { ToastProvider } from '../../components/DaisyUI'
import { OPEN_SETTINGS_EVENT } from '../../components/settings/kernel'
import type { OpenSettingsDetail } from '../../components/settings/kernel'
import { resetConversationThreads } from '../../lib/chatMeter'
import { HOST_CLI_TIP_STORAGE_KEY } from '../../lib/hostCliTip'
import { __resetUserPrefsCacheForTests } from '../../lib/userPrefs'

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
  close = vi.fn()
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

const AGENTS = [{ id: 'codey', name: 'Codey' }]

function cliAgentsPayload(discovered: string[], configured: string[] = []) {
  return {
    clis: ['claude', 'codex', 'opencode'],
    known: ['claude', 'codex', 'opencode'],
    configured,
    discovered,
    installed: discovered,
    paths: Object.fromEntries(discovered.map((name) => [name, `/usr/local/bin/${name}`])),
    suggestions: Object.fromEntries(
      discovered
        .filter((name) => !configured.includes(name))
        .map((name) => [name, { cmd: [name] }]),
    ),
    native_consensus: {},
    catalog: {},
    rail: [],
  }
}

function stubFetch(cli: ReturnType<typeof cliAgentsPayload>) {
  const fetchMock = vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    const json = (body: unknown) =>
      ({ ok: true, status: 200, json: async () => body }) as Response
    if (url.includes('/v1/preferences')) {
      return json({
        object: 'user_preferences',
        principal: 'session:test',
        guest: true,
        empty: true,
        favourites: [],
        hidden_agents: [],
        hostname_override: '',
        values: {},
      })
    }
    if (url.includes('/v1/cli-agents')) return json(cli)
    if (url.includes('/suggestions/')) return json({ object: 'suggestions', suggestions: [] })
    if (url.includes('/settings/')) {
      return json({ agent_id: 'codey', new_chat_per_task: false, use_suggestions: false })
    }
    if (url.includes('/chat/thread/')) {
      return json({ agent_id: 'codey', conversation_id: 'conv-1703', messages: [] })
    }
    return json({ data: AGENTS })
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function renderChat(entry = '/chat?blueprint=codey') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={[entry]}>
          <ChatPage />
        </MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

async function openChat(cli = cliAgentsPayload(['opencode'])) {
  const fetchMock = stubFetch(cli)
  const view = renderChat()
  await act(async () => {
    MockWebSocket.instances[0]?.open()
  })
  return { fetchMock, view }
}

describe('ChatPage #1703 host CLI detected tip', () => {
  beforeEach(() => {
    MockWebSocket.instances = []
    window.localStorage.clear()
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
    __resetUserPrefsCacheForTests()
  })

  it('shows a tip naming the detected CLI without blocking chat (Success #1, #5)', async () => {
    await openChat(cliAgentsPayload(['opencode']))
    const tip = await screen.findByTestId('host-cli-tip')
    expect(screen.getByTestId('host-cli-tip-title')).toHaveTextContent('opencode detected')
    expect(tip).toHaveAttribute('data-cli', 'opencode')
    // Chat stays fully usable behind the tip.
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.getByTestId('chat-messages-container')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('picks the first unconfigured CLI from a mixed detected set', async () => {
    await openChat(cliAgentsPayload(['claude', 'opencode'], ['claude']))
    const tip = await screen.findByTestId('host-cli-tip')
    expect(tip).toHaveAttribute('data-cli', 'opencode')
  })

  it('shows no tip when no CLI is on PATH (Success #4)', async () => {
    await openChat(cliAgentsPayload([]))
    await screen.findByRole('textbox', { name: 'Chat message' })
    expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
  })

  it('shows no tip once every detected CLI is configured', async () => {
    await openChat(cliAgentsPayload(['opencode'], ['opencode']))
    await screen.findByRole('textbox', { name: 'Chat message' })
    expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
  })

  it('Add provider deep-links to Settings → CLI agents prefilled for that CLI (Success #2)', async () => {
    const opened: Array<OpenSettingsDetail | undefined> = []
    const listener = (e: Event) => opened.push((e as CustomEvent<OpenSettingsDetail>).detail)
    window.addEventListener(OPEN_SETTINGS_EVENT, listener)
    try {
      await openChat()
      fireEvent.click(await screen.findByTestId('host-cli-tip-add'))
      expect(opened).toEqual([{ section: 'cli-agents', addCliName: 'opencode' }])
    } finally {
      window.removeEventListener(OPEN_SETTINGS_EVENT, listener)
    }
  })

  it('"Don\'t show this again" persists locally and server-side, and sticks across reloads (Success #3)', async () => {
    const { fetchMock: first, view } = await openChat()
    fireEvent.click(await screen.findByTestId('host-cli-tip-never'))
    await waitFor(() => {
      expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
    })
    expect(localStorage.getItem(HOST_CLI_TIP_STORAGE_KEY)).toBe('1')
    const patch = first.mock.calls.find(
      (call) =>
        String(call[0]).includes('/v1/preferences/') &&
        (call[1] as RequestInit | undefined)?.method === 'PATCH',
    )
    expect(patch).toBeTruthy()

    view.unmount()
    __resetUserPrefsCacheForTests()
    await openChat()
    await screen.findByRole('textbox', { name: 'Chat message' })
    await waitFor(() => {
      expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
    })
  })

  it('the X dismisses for the session and re-offers after a reload', async () => {
    const { view } = await openChat()
    fireEvent.click(await screen.findByTestId('host-cli-tip-dismiss'))
    await waitFor(() => {
      expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
    })
    expect(localStorage.getItem(HOST_CLI_TIP_STORAGE_KEY)).toBeNull()
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()

    view.unmount()
    __resetUserPrefsCacheForTests()
    await openChat()
    expect(await screen.findByTestId('host-cli-tip')).toBeInTheDocument()
  })

  it('Esc dismisses the tip and leaves chat mounted (Success #5)', async () => {
    await openChat()
    const composer = await screen.findByRole('textbox', { name: 'Chat message' })
    expect(await screen.findByTestId('host-cli-tip')).toBeInTheDocument()
    fireEvent.keyDown(composer, { key: 'Escape' })
    await waitFor(() => {
      expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
    })
    expect(screen.getByRole('textbox', { name: 'Chat message' })).toBeInTheDocument()
    expect(screen.getByTestId('chat-messages-container')).toBeInTheDocument()
  })

  it('stays hidden when the server prefs bag already carries the opt-out', async () => {
    localStorage.setItem(HOST_CLI_TIP_STORAGE_KEY, '1')
    await openChat()
    await screen.findByRole('textbox', { name: 'Chat message' })
    await waitFor(() => {
      expect(screen.queryByTestId('host-cli-tip')).not.toBeInTheDocument()
    })
  })
})

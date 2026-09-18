import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/DaisyUI'
import { OPEN_SETTINGS_EVENT, type OpenSettingsDetail } from '../../components/SettingsSheet'
import { resetConversationThreads } from '../../lib/chatMeter'
import ChatPage from '../ChatPage'

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

const RAIL_ROWS = [
  {
    id: 'cli_agent',
    object: 'cli.agent',
    name: 'cli_agent',
    cli: 'grok',
    kind: 'cli',
    description: 'Host CLI',
    installed: true,
  },
  {
    id: 'api_agent',
    object: 'cli.agent',
    name: 'api_agent',
    cli: '',
    kind: 'api',
    description: 'LiteLLM',
    installed: true,
  },
]

const PROFILES = {
  object: 'llm_profiles',
  profiles: [
    { id: 'orchestration', object: 'llm_profile', source: 'test', owned_by: 'test', name: 'Orchestration' },
    { id: 'orchestration-mini', object: 'llm_profile', source: 'test', owned_by: 'test', name: 'Orchestration Mini' },
    { id: 'auxiliary', object: 'llm_profile', source: 'test', owned_by: 'test', name: 'Auxiliary' },
  ],
  default_llm_profile: 'orchestration',
  default_is_auto: false,
  override_per_task: false,
  task_llm_profiles: {},
  auto_picks: {},
  aliases_used: [],
  warnings: [],
  routes: {},
  task_classes: ['orchestration', 'auxiliary', 'delegation'],
}

function stubChat() {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/llm-profiles')) {
        return { ok: true, status: 200, json: async () => PROFILES } as Response
      }
      if (url.includes('/v1/cli-agents/')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            clis: ['grok'],
            known: ['grok'],
            configured: ['grok'],
            discovered: ['grok'],
            installed: ['grok'],
            suggestions: {},
            default_cli: 'grok',
            native_consensus: {},
            catalog: {},
            list_models: {},
            rail: RAIL_ROWS,
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'api_agent', name: 'API agent', description: 'LiteLLM' }],
          messages: [],
        }),
      } as Response
    }),
  )
}

function renderChat(initialEntry: string) {
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

describe('ChatPage api_agent navbar routing (#108)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('api_agent seat shows the API picker, not the CLI picker', { timeout: 10000 }, async () => {
    stubChat()
    renderChat('/chat?blueprint=api_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const apiPicker = await screen.findAllByLabelText('API')
    expect(apiPicker.length).toBeGreaterThan(0)
    expect(screen.queryAllByLabelText('CLI')).toHaveLength(0)
    expect(screen.queryByTestId('os-cli-session-switcher')).toBeNull()
  })

  it('leftover ?cli= does not force the CLI picker on an api_agent seat', { timeout: 10000 }, async () => {
    stubChat()
    renderChat('/chat?blueprint=api_agent&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    await screen.findAllByLabelText('API')
    expect(screen.queryAllByLabelText('CLI')).toHaveLength(0)
    expect(screen.queryByTestId('os-cli-session-switcher')).toBeNull()
  })

  it('cli_agent seat still gets the CLI picker', { timeout: 10000 }, async () => {
    stubChat()
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    const cliPicker = await screen.findAllByLabelText('CLI')
    expect(cliPicker.length).toBeGreaterThan(0)
  })

  it('API picker opens searchable palette with Manage API action', { timeout: 10000 }, async () => {
    stubChat()
    renderChat('/chat?blueprint=api_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    const manageBtn = await screen.findByTestId('os-model-manage-api')
    expect(manageBtn).toHaveTextContent('Manage API in Settings')
  })

  it('API model pick flows into the WS frame params.model', async () => {
    stubChat()
    renderChat('/chat?blueprint=api_agent')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByTestId('os-model-row-orchestration-mini'))
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'route this turn' } })
    fireEvent.submit(composer.closest('form')!)
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
    const frame = JSON.parse(ws.send.mock.calls[0][0] as string)
    expect(frame).toMatchObject({ message: 'route this turn', blueprint: 'api_agent' })
    expect(frame.params?.model).toBe('orchestration-mini')
  })
})

describe('ChatPage Manage CLI / API footers (#254)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  function listenSettings() {
    const opened: OpenSettingsDetail[] = []
    const onOpen = (event: Event) => {
      opened.push((event as CustomEvent<OpenSettingsDetail>).detail)
    }
    window.addEventListener(OPEN_SETTINGS_EVENT, onOpen)
    return {
      opened,
      stop() {
        window.removeEventListener(OPEN_SETTINGS_EVENT, onOpen)
      },
    }
  }

  it('Manage CLI opens the in-app CLI agents sheet without leaving Chat', { timeout: 10000 }, async () => {
    stubChat()
    const { opened, stop } = listenSettings()
    try {
      renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
      await act(async () => {
        MockWebSocket.instances[0]?.open()
      })
      fireEvent.click(await screen.findByTestId('routing-pill-agent'))
      fireEvent.click(await screen.findByRole('menuitem', { name: 'Manage CLI' }))
      expect(opened).toEqual([{ section: 'cli-agents' }])
      expect(screen.getByTestId('navbar-routing-picker')).toBeInTheDocument()
    } finally {
      stop()
    }
  })

  it('Manage API opens the in-app LLM profiles sheet', { timeout: 10000 }, async () => {
    stubChat()
    const { opened, stop } = listenSettings()
    try {
      renderChat('/chat?blueprint=api_agent')
      await act(async () => {
        MockWebSocket.instances[0]?.open()
      })
      fireEvent.click(await screen.findByTestId('routing-pill-agent'))
      fireEvent.click(await screen.findByTestId('os-model-manage-api'))
      expect(opened).toEqual([{ section: 'llm-profiles' }])
    } finally {
      stop()
    }
  })

  it('?settings=cli-agents opens the CLI agents sheet on Chat mount', { timeout: 10000 }, async () => {
    stubChat()
    const { opened, stop } = listenSettings()
    try {
      renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok&settings=cli-agents')
      await act(async () => {
        MockWebSocket.instances[0]?.open()
      })
      expect(opened).toEqual([{ section: 'cli-agents' }])
    } finally {
      stop()
    }
  })
})

import { act, fireEvent, render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../../components/DaisyUI'
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

const REAL_CLI_AGENTS = {
  clis: ['agy', 'claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
  known: ['agy', 'claude', 'codex', 'gemini', 'grok', 'opencode', 'pi'],
  configured: ['grok'],
  discovered: ['grok'],
  installed: ['grok'],
  suggestions: {},
  default_cli: 'grok',
  native_consensus: { grok: ['--best-of-n', '{n}'] },
  catalog: {},
  list_models: { grok: ['grok', 'models'] },
  rail: [
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
  ],
}

function stubChat(models: { models: string[]; warning?: string }, cli = 'grok') {
  MockWebSocket.instances = []
  Element.prototype.scrollIntoView = vi.fn()
  vi.stubGlobal('WebSocket', MockWebSocket as unknown as typeof WebSocket)
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/cli-agents/') && url.includes('/models')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ cli, ...models }),
        } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => REAL_CLI_AGENTS,
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          data: [{ id: 'cli_agent', name: 'CLI agent', description: 'CLI' }],
          messages: [],
        }),
      } as Response
    }),
  )
}

describe('ChatPage CLI model pin (REQ-171C-3)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    window.localStorage.clear()
    resetConversationThreads()
  })

  it('empty probe does not render option default without a warning', async () => {
    stubChat({
      models: [],
      warning: "grok: CLI not installed (no 'grok' on PATH)",
    })
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // #681: the combined pill opens the two-stage dialog; the warning rides
    // in it (same surface the flat palette used to provide).
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    expect(await screen.findByTestId('routing-model-warning')).toHaveTextContent(
      "grok: CLI not installed (no 'grok' on PATH)",
    )
    expect(screen.queryByRole('menuitem', { name: 'default' })).not.toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'default' })).not.toBeInTheDocument()
  })

  it('sends params.model from a live probe id, not list_models argv', async () => {
    stubChat({ models: ['grok-4.5', 'grok-4.6'] })
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=grok')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    // #681/#682: descend into the CLI provider; probed models are its rows.
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    fireEvent.click(await screen.findByText('grok'))
    fireEvent.click((await screen.findAllByText('grok-4.5')).at(-1)!)
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'pin the next run' } })
    fireEvent.submit(composer.closest('form')!)
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
    expect(JSON.parse(ws.send.mock.calls[0][0] as string)).toMatchObject({
      message: 'pin the next run',
      blueprint: 'cli_agent',
      params: { cli: 'grok', model: 'grok-4.5' },
    })
  })

  it('pi model pick pins provider/model on params.model (#103)', async () => {
    stubChat(
      { models: ['openai/gpt-4o', 'anthropic/claude-sonnet-4-6'] },
      'pi',
    )
    renderChat('/chat?blueprint=cli_agent&mode=cli&cli=pi')
    await act(async () => {
      MockWebSocket.instances[0]?.open()
    })
    fireEvent.click(await screen.findByTestId('routing-pill-agent'))
    expect(screen.queryByRole('menuitem', { name: 'openai' })).not.toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'default' })).not.toBeInTheDocument()
    // #504 + #103: the full provider/model id pins verbatim — no family split.
    // #681: descend into the pi provider first.
    fireEvent.click(await screen.findByText('pi'))
    // The dialog row and the pill's leaf label share the text (#757);
    // pick the dialog row (the last match rendered inside the dialog).
    fireEvent.click((await screen.findAllByText('openai/gpt-4o')).at(-1)!)
    const composer = screen.getByRole('textbox', { name: 'Chat message' })
    fireEvent.change(composer, { target: { value: 'pin pi' } })
    fireEvent.submit(composer.closest('form')!)
    const ws = MockWebSocket.instances[MockWebSocket.instances.length - 1]!
    expect(JSON.parse(ws.send.mock.calls[0][0] as string)).toMatchObject({
      message: 'pin pi',
      blueprint: 'cli_agent',
      params: { cli: 'pi', model: 'openai/gpt-4o' },
    })
  })
})

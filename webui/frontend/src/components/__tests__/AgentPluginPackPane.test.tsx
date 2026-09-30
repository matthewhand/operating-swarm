import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ToastProvider } from '../DaisyUI'
import AgentPluginPackPane from '../AgentPluginPackPane'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

const STATUS = {
  object: 'agent_plugins',
  agent_id: 'worker',
  plugins: [
    {
      pluginId: 'mcp:io.github.example/fetch',
      name: 'fetch',
      description: 'Fetch a URL as an MCP tool.',
      status: 'enabled',
      required_env: ['GITHUB_TOKEN'],
    },
    {
      pluginId: 'unknown-plugin-id',
      name: 'unknown-plugin-id',
      description: '',
      status: 'missing',
    },
  ],
  enabled: ['mcp:io.github.example/fetch'],
  missing: ['unknown-plugin-id'],
  pack: {
    object: 'agent_plugin_pack',
    schema: 1,
    kind: 'agent_plugin_pack',
    plugins: [
      { pluginId: 'mcp:io.github.example/fetch', name: 'fetch', description: 'Fetch a URL as an MCP tool.' },
      { pluginId: 'unknown-plugin-id', name: 'unknown-plugin-id', description: '' },
    ],
  },
}

function renderPane(agentId = 'worker') {
  return render(
    <ToastProvider>
      <AgentPluginPackPane agentId={agentId} />
    </ToastProvider>,
  )
}

describe('AgentPluginPackPane #1397', () => {
  beforeEach(() => {
    Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('shows enabled and missing status without tokens', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        expect(String(input)).toBe('/v1/agents/worker/plugins/')
        return jsonResponse({
          ...STATUS,
          plugins: [
            ...STATUS.plugins,
            {
              pluginId: 'leaky',
              name: 'leaky',
              status: 'enabled',
              token: 'sk-leakedSECRETVALUE',
              url: 'https://evil.example/mcp',
              command: 'uvx',
            },
          ],
        })
      }),
    )
    const { container } = renderPane()
    const list = await screen.findByRole('list', { name: 'Plugin pack status' })
    expect(list).toHaveTextContent('fetch')
    expect(list).toHaveTextContent('Enabled')
    expect(list).toHaveTextContent('unknown-plugin-id')
    expect(list).toHaveTextContent('Missing')
    expect(list).toHaveTextContent('GITHUB_TOKEN')
    expect(screen.getByTestId('os-plugin-pack-summary')).toHaveTextContent(/2 enabled/)
    expect(screen.getByTestId('os-plugin-pack-summary')).toHaveTextContent(/1 missing/)
    expect(container.textContent).not.toMatch(/sk-leakedSECRETVALUE/)
    expect(container.textContent).not.toMatch(/https:\/\/evil\.example/)
    expect(container.textContent).not.toContain('uvx')
  })

  it('copies a secret-free pack JSON', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined)
    Object.assign(navigator, { clipboard: { writeText } })
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(STATUS)),
    )
    renderPane()
    await screen.findByRole('list', { name: 'Plugin pack status' })
    fireEvent.click(screen.getByTestId('os-plugin-pack-copy'))
    await waitFor(() => {
      expect(writeText).toHaveBeenCalled()
    })
    const copied = String(writeText.mock.calls[0][0])
    expect(copied).toContain('mcp:io.github.example/fetch')
    expect(copied).not.toMatch(/\"token\"|\"url\"|\"command\"|sk-|bearer /i)
    expect(await screen.findByText('Pack copied')).toBeInTheDocument()
  })

  it('imports ids and reports enabled / missing without showing tokens', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input)
      const method = (init?.method || 'GET').toUpperCase()
      if (url.includes('/import/') && method === 'POST') {
        const body = JSON.parse(String(init?.body || '{}'))
        expect(JSON.stringify(body)).not.toMatch(/sk-|token|bearer |url|command/i)
        return jsonResponse({
          object: 'agent_plugin_pack_import',
          agent_id: 'worker',
          plugins: STATUS.plugins,
          enabled: STATUS.enabled,
          missing: STATUS.missing,
        })
      }
      return jsonResponse({
        object: 'agent_plugins',
        agent_id: 'worker',
        plugins: [],
        enabled: [],
        missing: [],
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    renderPane()
    expect(await screen.findByTestId('os-plugin-pack-empty')).toBeInTheDocument()
    fireEvent.change(screen.getByRole('textbox', { name: 'Import pack' }), {
      target: { value: 'mcp:io.github.example/fetch\nunknown-plugin-id' },
    })
    fireEvent.click(screen.getByTestId('os-plugin-pack-import-submit'))
    expect(await screen.findByRole('list', { name: 'Plugin pack status' })).toHaveTextContent('Missing')
    expect(screen.getByText(/Pack imported/i)).toBeInTheDocument()
  })

  it('refuses a token-shaped import in the client and never displays it', async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
      jsonResponse({ object: 'agent_plugins', agent_id: 'worker', plugins: [], enabled: [], missing: [] }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const { container } = renderPane()
    await screen.findByTestId('os-plugin-pack-empty')
    fireEvent.change(screen.getByRole('textbox', { name: 'Import pack' }), {
      target: {
        value: JSON.stringify({
          plugins: [
            {
              pluginId: 'leaky',
              headers: { Authorization: 'Bearer sk-notarealkeyABCDEFGH' },
            },
          ],
        }),
      },
    })
    fireEvent.click(screen.getByTestId('os-plugin-pack-import-submit'))
    expect(await screen.findByTestId('os-plugin-pack-error')).toHaveTextContent(/credential|plugin ids only/i)
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/import/'))).toBe(false)
    expect(container.textContent).not.toContain('sk-notarealkeyABCDEFGH')

    fireEvent.change(screen.getByRole('textbox', { name: 'Import pack' }), {
      target: {
        value: JSON.stringify({
          plugins: [{ pluginId: 'leaky', url: 'https://example.invalid/mcp', command: 'uvx' }],
        }),
      },
    })
    fireEvent.click(screen.getByTestId('os-plugin-pack-import-submit'))
    expect(await screen.findByTestId('os-plugin-pack-error')).toHaveTextContent(/plugin ids only/i)
    expect(container.textContent).not.toContain('https://example.invalid/mcp')
    expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('/import/'))).toBe(false)
  })

  it('asks the operator to pick an agent when none is selected', () => {
    renderPane('')
    expect(screen.getByTestId('os-plugin-pack-pane')).toHaveTextContent(/Select an agent/i)
  })

  it('does not claim the pack was copied when the clipboard is missing', async () => {
    Object.assign(navigator, { clipboard: undefined })
    vi.stubGlobal('fetch', vi.fn(async () => jsonResponse(STATUS)))
    renderPane()
    await screen.findByRole('list', { name: 'Plugin pack status' })
    fireEvent.click(screen.getByTestId('os-plugin-pack-copy'))
    expect(await screen.findByTestId('os-plugin-pack-error')).toHaveTextContent(/clipboard/i)
    expect(screen.queryByText('Pack copied')).not.toBeInTheDocument()
  })

  it('drops a status response that arrives after the agent changes or unmount', async () => {
    let resolveSlow: (value: Response) => void = () => {}
    const slow = new Promise<Response>((resolve) => {
      resolveSlow = resolve
    })
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input).includes('/agents/slow/')) return slow
        return jsonResponse({
          object: 'agent_plugins',
          agent_id: 'fast',
          plugins: [
            { pluginId: 'web_search', name: 'web_search', description: '', status: 'enabled' },
          ],
          enabled: ['web_search'],
          missing: [],
        })
      }),
    )
    const { rerender, unmount } = render(
      <ToastProvider>
        <AgentPluginPackPane agentId="slow" />
      </ToastProvider>,
    )
    rerender(
      <ToastProvider>
        <AgentPluginPackPane agentId="fast" />
      </ToastProvider>,
    )
    expect(await screen.findByTestId('os-plugin-pack-status')).toHaveTextContent('web_search')
    expect(screen.getByTestId('os-plugin-pack-pane')).toHaveAttribute('data-agent', 'fast')
    await act(async () => {
      resolveSlow(
        jsonResponse({
          object: 'agent_plugins',
          agent_id: 'slow',
          plugins: [
            { pluginId: 'stale-plugin', name: 'stale-plugin', description: '', status: 'missing' },
          ],
          enabled: [],
          missing: ['stale-plugin'],
        }),
      )
      await slow
    })
    expect(screen.getByTestId('os-plugin-pack-status')).toHaveTextContent('web_search')
    expect(screen.queryByText('stale-plugin')).not.toBeInTheDocument()
    expect(screen.getByTestId('os-plugin-pack-pane')).toHaveAttribute('data-agent', 'fast')
    unmount()
    expect(screen.queryByTestId('os-plugin-pack-pane')).not.toBeInTheDocument()
  })
})

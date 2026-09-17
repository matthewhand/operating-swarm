import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CliAgentsSettingsPane from '../CliAgentsSettingsPane'
import { ToastProvider } from '../DaisyUI'

const KNOWN = ['agy', 'claude', 'codex', 'gemini', 'grok', 'opencode', 'pi']

function renderPane(focusProviderId?: string | null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <CliAgentsSettingsPane focusProviderId={focusProviderId} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

function stubFetch(options: {
  config?: Record<string, { cmd?: string[] }>
  catalog?: Record<string, unknown>
  patches?: unknown[]
}) {
  const patches = options.patches ?? []
  const config = options.config ?? {}
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
      const url = String(input)
      const method = init?.method || 'GET'
      if (url.includes('/v1/config/sections/cli_agents') && method === 'PATCH') {
        patches.push(JSON.parse(String(init?.body || '{}')))
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'config_section', data: config }),
        } as Response
      }
      if (url.includes('/v1/config/sections/cli_agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'config_section', data: config }),
        } as Response
      }
      if (url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            clis: KNOWN,
            known: KNOWN,
            configured: Object.keys(config),
            discovered: [],
            installed: [],
            suggestions: {},
            native_consensus: {},
            catalog: {},
            ...(options.catalog || {}),
          }),
        } as Response
      }
      if (url.includes('/v1/rate-limits')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'provider_rate_limits', data: [] }),
        } as Response
      }
      return { ok: true, status: 200, json: async () => ({}) } as Response
    }),
  )
  return patches
}

function rateLimitInputs() {
  return [
    screen.queryByLabelText(/requests per minute/i),
    screen.queryByLabelText(/tokens per minute/i),
    screen.queryByTestId('rate-limits-cli-grok'),
  ]
}

describe('CliAgentsSettingsPane (REQ-157 / #117)', () => {
  beforeEach(() => {
    Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('starts empty and one-click adds a discovered suggestion', async () => {
    const patches: unknown[] = []
    stubFetch({
      patches,
      catalog: {
        configured: [],
        discovered: ['grok'],
        installed: ['grok'],
        suggestions: { grok: { cmd: ['grok', '-p', '{prompt}'] } },
      },
    })

    renderPane()
    expect(await screen.findByText(/No CLI agents configured yet/i)).toBeInTheDocument()
    expect(screen.getByRole('list', { name: 'CLI agents' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Add' }))
    await waitFor(() => {
      expect(patches).toEqual([{ upsert: { grok: { cmd: ['grok', '-p', '{prompt}'] } } }])
    })
  })

  it('removes a configured CLI without treating PATH discovery as configured', async () => {
    const patches: unknown[] = []
    stubFetch({
      patches,
      config: { grok: { cmd: ['grok', '-p', '{prompt}'] } },
      catalog: {
        configured: ['grok'],
        discovered: ['grok', 'claude'],
        suggestions: { claude: { cmd: ['claude'] } },
      },
    })

    renderPane()
    expect(await screen.findByRole('list', { name: 'CLI agents' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }))
    await waitFor(() => {
      expect(patches).toEqual([{ delete: ['grok'] }])
    })
  })

  it('keeps rpm/tpm inputs out of the document until settings open', async () => {
    stubFetch({
      config: { grok: { cmd: ['grok', '-p', '{prompt}'] } },
      catalog: {
        configured: ['grok'],
        discovered: ['grok'],
      },
    })

    renderPane()
    expect(await screen.findByTestId('cli-row-grok')).toBeInTheDocument()
    expect(rateLimitInputs().every((node) => node == null)).toBe(true)

    fireEvent.mouseEnter(screen.getByRole('button', { name: 'Settings for grok' }))
    expect(await screen.findByLabelText(/requests per minute/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/tokens per minute/i)).toBeInTheDocument()
    expect(screen.getByTestId('rate-limits-cli-grok')).toBeInTheDocument()
  })

  it('opens settings fields on keyboard focus of the icon', async () => {
    stubFetch({
      config: { grok: { cmd: ['grok'] } },
      catalog: { configured: ['grok'], discovered: ['grok'] },
    })

    renderPane()
    const settings = await screen.findByRole('button', { name: 'Settings for grok' })
    expect(rateLimitInputs().every((node) => node == null)).toBe(true)
    fireEvent.focus(settings)
    expect(await screen.findByLabelText(/requests per minute/i)).toBeInTheDocument()
  })

  it('hides the settings button on undetected rows', async () => {
    stubFetch({
      catalog: {
        configured: [],
        discovered: ['grok'],
        installed: ['grok'],
        suggestions: { grok: { cmd: ['grok'] } },
      },
    })

    renderPane()
    expect(await screen.findByTestId('cli-row-grok')).toBeInTheDocument()
    expect(screen.queryByTestId('cli-row-claude')).not.toBeInTheDocument()

    fireEvent.click(screen.getByLabelText('Show unavailable'))
    const claude = await screen.findByTestId('cli-row-claude')
    expect(claude).toHaveAttribute('data-status', 'not-detected')
    expect(within(claude).queryByRole('button', { name: /Settings/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Settings for grok' })).toBeInTheDocument()
  })

  it('auto-opens the focused CLI popup from the token meter', async () => {
    stubFetch({
      config: { grok: { cmd: ['grok', '-p', '{prompt}'] } },
      catalog: { configured: ['grok'], discovered: ['grok'] },
    })

    renderPane('cli:grok')
    expect(await screen.findByTestId('rate-limits-cli-grok')).toBeInTheDocument()
    expect(screen.getByLabelText(/requests per minute/i)).toBeInTheDocument()
    expect(screen.getByRole('dialog', { name: 'grok settings' })).toBeInTheDocument()
  })

  it('collapses hop prefs by default', async () => {
    stubFetch({
      catalog: { configured: [], discovered: [], suggestions: {} },
    })

    renderPane()
    expect(await screen.findByText(/No CLI agents configured yet/i)).toBeInTheDocument()
    const hop = document.querySelector('.os-cli-hop-prefs')
    expect(hop).toBeInstanceOf(HTMLDetailsElement)
    expect((hop as HTMLDetailsElement).open).toBe(false)
  })
})

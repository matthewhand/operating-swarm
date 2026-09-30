import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { RAIL_ORDER_STORAGE_KEY } from '../../lib/railOrder'

function seat(
  id: string,
  name: string,
  extra: Record<string, unknown> = {},
) {
  return {
    id,
    object: 'blueprint' as const,
    name,
    description: name,
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
    ...extra,
  }
}

function jsonOk(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

function mockRailFetch(catalog: ReturnType<typeof seat>[]) {
  return vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
    const url = String(input)
    const method = String(init?.method || 'GET').toUpperCase()
    if (url.includes('/v1/preferences')) {
      return jsonOk({
        object: 'user_preferences',
        principal: 'session:test',
        guest: true,
        empty: true,
        favourites: [],
        hidden_agents: [],
      })
    }
    if (url.includes('team-rosters') || url.includes('team_rosters')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/cli-agents')) {
      return jsonOk({
        clis: [],
        native_consensus: {},
        catalog: {},
        rail: [],
      })
    }
    if (url.includes('/v1/herdr-agents')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/companies')) {
      return jsonOk({
        object: 'list',
        data: [
          {
            object: 'company',
            id: 'acme-id',
            name: 'Acme',
            slug: 'acme',
            model_policy: {
              mode: 'allow_all',
              allowed_models: [],
              denied_models: [],
              default_model: '',
            },
            default_model: '',
          },
        ],
      })
    }
    if (url.includes('/v1/blueprints/custom/') && method === 'POST') {
      const body = JSON.parse(String(init?.body || '{}')) as {
        name?: string
        command?: string
      }
      return jsonOk(
        {
          id: 'my_cli_tool',
          name: body.name || 'My CLI Tool',
          description: `CLI: ${body.command || ''}`,
          category: 'cli',
          tags: ['cli'],
          requirements: '',
          code: '',
          required_mcp_servers: [],
          env_vars: [],
          kind: 'cli',
          command: body.command,
          rail: true,
          source: 'add-agent',
        },
        201,
      )
    }
    if (url.includes('/v1/blueprints/custom/')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/agents/') && url.includes('/settings')) {
      return jsonOk({ agent_id: 'my_cli_tool', folder: '' })
    }
    if (url.includes('/v1/blueprints')) {
      return jsonOk({ object: 'list', data: catalog })
    }
    return jsonOk({ object: 'list', data: [] })
  })
}

function renderSidebar() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function storedRailOrder(): string[] {
  return JSON.parse(localStorage.getItem(RAIL_ORDER_STORAGE_KEY) || '[]')
}

function railIds(list: HTMLElement): string[] {
  return [...list.querySelectorAll('[data-rail-id]')].map(
    (node) => node.getAttribute('data-rail-id') || '',
  )
}

describe('AgentSidebar REQ-171B add-agent rail seats', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('lists Add-agent CLI/API customs when GET /v1/blueprints/ sets rail true', async () => {
    vi.stubGlobal(
      'fetch',
      mockRailFetch([
        seat('support', 'Support', { role: 'support' }),
        seat('desk_cli', 'Desk CLI', { kind: 'cli', command: 'grok', cli: 'grok' }),
        seat('researcher', 'Researcher', { kind: 'api' }),
        seat('scratch', 'Scratch', { rail: false }),
      ]),
    )
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    expect(await within(list).findByRole('link', { name: /Desk CLI/ })).toBeInTheDocument()
    expect(within(list).getByRole('link', { name: /Researcher/ })).toBeInTheDocument()
    expect(within(list).queryByRole('link', { name: /Scratch/ })).not.toBeInTheDocument()
  })

  it('completing Add-agent CLI create shows the seat and bumps it to top of unpinned', async () => {
    const catalog = [seat('support', 'Support', { role: 'support' })]
    const created = seat('my_cli_tool', 'My CLI Tool', {
      kind: 'cli',
      command: 'custom-tool',
      cli: 'custom-tool',
    })
    let includeCreated = false
    const fetchMock = mockRailFetch(catalog)
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo, init?: RequestInit) => {
        const url = String(input)
        const method = String(init?.method || 'GET').toUpperCase()
        if (method === 'POST' && url.includes('/v1/blueprints/custom/')) {
          includeCreated = true
        }
        if (
          method === 'GET' &&
          url.includes('/v1/blueprints') &&
          !url.includes('custom') &&
          includeCreated
        ) {
          return jsonOk({ object: 'list', data: [...catalog, created] })
        }
        return fetchMock(input, init)
      }),
    )

    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    expect(within(list).queryByRole('link', { name: /My CLI Tool/ })).not.toBeInTheDocument()

    // #1674: `+` opens the Add-bot menu; the wizard is its "Create new agent"
    // action, so the same creation flow is still reachable from the rail.
    fireEvent.click(await screen.findByTestId('add-bot-menu-trigger'))
    const addMenu = await screen.findByTestId('os-add-bot-menu')
    fireEvent.click(within(addMenu).getByTestId('os-add-bot-menu-create-bot'))
    expect(await screen.findByTestId('add-agent-wizard')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('kind-option-cli'))
    await screen.findByTestId('input-cli-name')
    fireEvent.change(screen.getByTestId('input-cli-name'), {
      target: { value: 'My CLI Tool' },
    })
    fireEvent.change(screen.getByTestId('input-cli-command'), {
      target: { value: 'custom-tool' },
    })
    fireEvent.click(screen.getByTestId('submit-create-agent'))

    await waitFor(() => {
      expect(within(list).getByRole('link', { name: /My CLI Tool/ })).toBeInTheDocument()
    })
    expect(railIds(list)[0]).toBe('my_cli_tool')
    expect(storedRailOrder()[0]).toBe('my_cli_tool')
  })
})

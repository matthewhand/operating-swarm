/**
 * Dedicated "CLI" rail section: one derived row per discovered/configured CLI.
 *
 * The backend rail contract stays `{cli_agent, api_agent}` — these rows are
 * synthesised in the frontend from `discovered ∪ configured`, so the tests pin
 * the derivation, the `?blueprint=cli_agent&cli=<name>` href, the absence of a
 * block when no CLI is known, and the active state driven by `?cli=`.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

function jsonOk(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

const catalog = [
  {
    id: 'support',
    object: 'blueprint' as const,
    name: 'Support',
    description: 'Onboarding',
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
    role: 'support',
  },
]

const CLI_AGENT_RAIL = [
  {
    id: 'cli_agent',
    object: 'cli.agent',
    name: 'cli_agent',
    cli: 'agy',
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

function mockFetch(
  cliAgents: Record<string, unknown>,
  extra: { herdr?: unknown[]; remotes?: unknown[] } = {},
) {
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
      return jsonOk(cliAgents)
    }
    if (url.includes('/v1/cli-sessions')) {
      void method
      return jsonOk({
        object: 'cli_session_list',
        agent_id: 'cli_agent',
        cli: 'agy',
        can_list: false,
        sessions: [],
        recent: [],
        empty_reason: 'no sessions',
        activity_sot: 'swarm',
      })
    }
    if (url.includes('/v1/herdr-agents')) {
      return jsonOk({ object: 'list', data: extra.herdr ?? [] })
    }
    if (url.includes('/v1/remotes') || url.includes('remotes_catalog')) {
      return jsonOk({ object: 'list', data: extra.remotes ?? [] })
    }
    if (url.includes('/v1/agents/designs')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('api.github.com')) {
      return jsonOk({}, 404)
    }
    if (url.includes('/sessions')) {
      return jsonOk({ object: 'agent_session_list', agent_id: 'codey', sessions: [] })
    }
    if (url.includes('/v1/blueprints')) {
      return jsonOk({ object: 'list', data: catalog })
    }
    return jsonOk({ object: 'list', data: [] })
  })
}

function renderSidebar(initialEntry = '/chat') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <AgentSidebar open onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

function cliSection(): HTMLElement | null {
  return sectionById('cli')
}

function sectionById(id: string): HTMLElement | null {
  return document.querySelector(
    `[data-testid="rail-section"][data-section-id="${id}"]`,
  ) as HTMLElement | null
}

function sectionRailIds(id: string): string[] {
  const section = sectionById(id)
  if (!section) return []
  return [...section.querySelectorAll('[data-rail-id]')].map(
    (node) => node.getAttribute('data-rail-id') || '',
  )
}

function sectionOrder(): string[] {
  return [...document.querySelectorAll('[data-testid="rail-section"]')].map(
    (node) => node.getAttribute('data-section-id') || '',
  )
}

function rowById(id: string): HTMLElement | null {
  return document.querySelector(`[data-rail-id="${id}"]`) as HTMLElement | null
}

function isRowActive(id: string): boolean {
  const node = rowById(id)
  if (!node) return false
  if (node.classList.contains('os-agent-row--active')) return true
  return Boolean(node.querySelector('.os-agent-row--active'))
}

describe('AgentSidebar CLI rail section', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders a CLI block with one row per discovered ∪ configured CLI', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        clis: ['agy', 'opencode', 'claude'],
        discovered: ['agy', 'opencode'],
        configured: ['claude'],
        native_consensus: {},
        catalog: {},
        rail: CLI_AGENT_RAIL,
      }),
    )
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })

    const section = cliSection()
    expect(section).not.toBeNull()
    expect(within(section as HTMLElement).getByText('CLI')).toBeInTheDocument()

    const agy = within(section as HTMLElement).getByRole('link', { name: /agy/ })
    expect(agy).toHaveAttribute('href', '/chat?blueprint=cli_agent&cli=agy')
    const opencode = within(section as HTMLElement).getByRole('link', { name: /opencode/ })
    expect(opencode).toHaveAttribute('href', '/chat?blueprint=cli_agent&cli=opencode')
    const claude = within(section as HTMLElement).getByRole('link', { name: /claude/ })
    expect(claude).toHaveAttribute('href', '/chat?blueprint=cli_agent&cli=claude')

    expect(rowById('agy_agent')).not.toBeNull()
    expect(rowById('opencode_agent')).not.toBeNull()
    expect(rowById('claude_agent')).not.toBeNull()

    // The generic `cli_agent` seat is a cli-kind row, so it belongs in CLI.
    const generic = within(list).getByRole('link', { name: /cli_agent/ })
    expect(generic).toHaveAttribute('href', '/chat?blueprint=cli_agent&cli=agy')
    expect(within(section as HTMLElement).getByRole('link', { name: /cli_agent/ })).toBe(generic)
  })

  it('renders Remote, CLI and API kind blocks in order with exact membership', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(
        {
          clis: [],
          discovered: [],
          configured: [],
          native_consensus: {},
          catalog: {},
          rail: CLI_AGENT_RAIL,
        },
        {
          herdr: [{ id: 1, object: 'herdr.agent', kind: 'herdr', name: 'w3:p1', remote: '' }],
          remotes: [{ id: 'omb', title: 'OpenMousBot', configured: true, agents: [] }],
        },
      ),
    )
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })

    // Remote holds the remote entry AND the remote-impl herdr agent.
    expect(sectionRailIds('remote')).toEqual(
      expect.arrayContaining(['remote:omb', 'herdr:w3:p1']),
    )
    // CLI holds cli-kind seats; api_agent must not leak into CLI.
    expect(sectionRailIds('cli')).toContain('cli_agent')
    expect(sectionRailIds('cli')).not.toContain('api_agent')
    expect(sectionRailIds('api')).toEqual(['api_agent'])

    const order = sectionOrder()
    expect(order.indexOf('remote')).toBeLessThan(order.indexOf('cli'))
    expect(order.indexOf('cli')).toBeLessThan(order.indexOf('api'))
    expect(order.indexOf('api')).toBeLessThan(order.indexOf('unassigned'))
  })

  it('emits no derived CLI rows when no CLI is discovered or configured', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        clis: [],
        discovered: [],
        configured: [],
        native_consensus: {},
        catalog: {},
        rail: CLI_AGENT_RAIL,
      }),
    )
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })
    // The generic cli_agent row still renders in CLI; nothing is derived.
    const section = cliSection() as HTMLElement
    expect(section).not.toBeNull()
    expect(rowById('cli_agent')).not.toBeNull()
    expect(section.querySelectorAll('[data-rail-id]')).toHaveLength(1)
    expect(rowById('agy_agent')).toBeNull()
  })

  it('dedupes a CLI the rail already names', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        clis: ['agy', 'opencode'],
        discovered: ['agy', 'opencode'],
        configured: [],
        native_consensus: {},
        catalog: {},
        rail: [
          ...CLI_AGENT_RAIL,
          {
            id: 'agy_agent',
            object: 'cli.agent',
            name: 'agy',
            cli: 'agy',
            kind: 'cli',
            description: 'Agy',
            installed: true,
          },
        ],
      }),
    )
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })
    expect(document.querySelectorAll('[data-rail-id="agy_agent"]').length).toBe(1)
    // opencode is not named by the rail, so it is still derived.
    expect(rowById('opencode_agent')).not.toBeNull()
  })

  it('highlights the ?cli= row (and not the generic cli_agent row)', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        clis: ['agy', 'opencode'],
        discovered: ['agy', 'opencode'],
        configured: [],
        native_consensus: {},
        catalog: {},
        rail: CLI_AGENT_RAIL,
      }),
    )
    renderSidebar('/chat?blueprint=cli_agent&cli=agy')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /agy/ })

    expect(isRowActive('agy_agent')).toBe(true)
    expect(isRowActive('opencode_agent')).toBe(false)
    expect(isRowActive('cli_agent')).toBe(false)
  })

  it('collapses the CLI block from its header', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        clis: ['agy'],
        discovered: ['agy'],
        configured: [],
        native_consensus: {},
        catalog: {},
        rail: CLI_AGENT_RAIL,
      }),
    )
    renderSidebar('/chat')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /agy/ })
    const section = cliSection() as HTMLElement
    expect(section.getAttribute('data-collapsed')).toBe('false')
    fireEvent.click(within(section).getByRole('button', { name: /CLI/ }))
    expect(cliSection()?.getAttribute('data-collapsed')).toBe('true')
    expect(rowById('agy_agent')).toBeNull()
  })

  it('collapses Remote and API independently of CLI', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch(
        {
          clis: [],
          discovered: [],
          configured: [],
          native_consensus: {},
          catalog: {},
          rail: CLI_AGENT_RAIL,
        },
        {
          herdr: [{ id: 1, object: 'herdr.agent', kind: 'herdr', name: 'w3:p1', remote: '' }],
          remotes: [{ id: 'omb', title: 'OpenMousBot', configured: true, agents: [] }],
        },
      ),
    )
    renderSidebar('/chat')

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /api_agent/ })

    const api = sectionById('api') as HTMLElement
    expect(api.getAttribute('data-collapsed')).toBe('false')
    fireEvent.click(within(api).getByRole('button', { name: /API/ }))
    expect(sectionById('api')?.getAttribute('data-collapsed')).toBe('true')
    expect(rowById('api_agent')).toBeNull()
    // Independent state: CLI and Remote stay open.
    expect(sectionById('cli')?.getAttribute('data-collapsed')).toBe('false')
    expect(rowById('cli_agent')).not.toBeNull()

    const remote = sectionById('remote') as HTMLElement
    fireEvent.click(within(remote).getByRole('button', { name: /Remote/ }))
    expect(sectionById('remote')?.getAttribute('data-collapsed')).toBe('true')
    expect(rowById('remote:omb')).toBeNull()
    expect(rowById('herdr:w3:p1')).toBeNull()
  })
})

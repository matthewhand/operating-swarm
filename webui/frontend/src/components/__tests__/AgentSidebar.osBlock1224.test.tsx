/**
 * #1224 — the rail's dedicated "OS" section.
 *
 * Remote rows whose kind resolves to `swarm` are Open Swarm instances and are
 * bucketed into their own OS block, ahead of Remote/CLI/API. Every other remote
 * kind (hermes, omb, …) stays in Remote, and the OS block is not emitted at all
 * when no swarm remote is present.
 *
 * `remoteKindOf` reads `kind || impl || id`; jsdom cannot compute layout, so the
 * assertions are DOM/attribute based (`[data-section-id]`, `[data-rail-id]`)
 * exactly like the existing section harness.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
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

// cli_agent (kind: cli) and api_agent (kind: api) guarantee the CLI and API
// blocks render so their order relative to OS can be pinned.
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

const SWARM_REMOTE = {
  id: 'swarm-box',
  kind: 'swarm',
  title: 'Swarm Box',
  configured: true,
  agents: [],
}
const HERMES_REMOTE = {
  id: 'hermes',
  kind: 'hermes',
  title: 'Hermes',
  configured: true,
  agents: [],
}
const OMB_REMOTE = { id: 'omb', title: 'OpenMousBot', configured: true, agents: [] }

function mockFetch(extra: { herdr?: unknown[]; remotes?: unknown[] } = {}) {
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
        discovered: [],
        configured: [],
        native_consensus: {},
        catalog: {},
        rail: CLI_AGENT_RAIL,
      })
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

function renderSidebar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
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

describe('#1224 OS rail section membership and order', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders a kind:swarm remote inside the OS block, not Remote', async () => {
    vi.stubGlobal('fetch', mockFetch({ remotes: [SWARM_REMOTE, HERMES_REMOTE] }))
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Swarm Box/ })

    const os = sectionById('os')
    expect(os).not.toBeNull()
    expect(within(os as HTMLElement).getByText('OS')).toBeInTheDocument()

    expect(sectionRailIds('os')).toEqual(['remote:swarm-box'])
    expect(sectionRailIds('remote')).not.toContain('remote:swarm-box')
  })

  it('orders OS before Remote, CLI and API', async () => {
    vi.stubGlobal('fetch', mockFetch({ remotes: [SWARM_REMOTE, HERMES_REMOTE] }))
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /cli_agent/ })

    const order = sectionOrder()
    expect(order).toEqual(expect.arrayContaining(['os', 'remote', 'cli', 'api']))
    expect(order.indexOf('os')).toBeLessThan(order.indexOf('remote'))
    expect(order.indexOf('remote')).toBeLessThan(order.indexOf('cli'))
    expect(order.indexOf('cli')).toBeLessThan(order.indexOf('api'))
  })

  it('emits no OS block when no swarm remote is present', async () => {
    vi.stubGlobal('fetch', mockFetch({ remotes: [HERMES_REMOTE, OMB_REMOTE] }))
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Hermes/ })

    expect(sectionById('os')).toBeNull()
  })

  it('keeps non-swarm remotes (hermes, omb) in Remote', async () => {
    vi.stubGlobal('fetch', mockFetch({ remotes: [HERMES_REMOTE, OMB_REMOTE] }))
    renderSidebar()

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    await within(list).findByRole('link', { name: /Hermes/ })

    expect(sectionRailIds('remote')).toEqual(
      expect.arrayContaining(['remote:hermes', 'remote:omb']),
    )
    expect(sectionById('os')).toBeNull()
  })
})

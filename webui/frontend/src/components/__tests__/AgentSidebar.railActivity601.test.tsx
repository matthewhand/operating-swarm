/**
 * #601 — remote and team rail rows render an activity timestamp when the
 * payload carries `last_message_at`, and render nothing (no placeholder, no
 * "Invalid Date") when it does not. The server now stamps the instant from
 * the chat store; the parsers normalise it onto the entries the rows read.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

function seat(id: string, name: string, extra: Record<string, unknown> = {}) {
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

function mockFetch(opts: { remotes?: unknown[]; rosters?: unknown[] }) {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
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
      return jsonOk({ object: 'list', data: opts.rosters ?? [] })
    }
    if (url.includes('/v1/remotes')) {
      return jsonOk({
        object: 'list',
        data: opts.remotes ?? [],
        configured: opts.remotes ?? [],
        kinds: [],
        team_members: [],
      })
    }
    if (url.includes('/v1/cli-agents')) {
      return jsonOk({ clis: [], native_consensus: {}, catalog: {}, rail: [] })
    }
    if (url.includes('/v1/herdr-agents')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/blueprints')) {
      return jsonOk({ object: 'list', data: [seat('support', 'Support', { role: 'support' })] })
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

/** ISO instant a touch over `m` minutes old so formatRailTimestamp floors to `m`. */
const minutesAgoIso = (m: number) => new Date(Date.now() - m * 60_000 - 1_000).toISOString()

const TIME_TEXT = /min ago|Just now|Invalid Date/

describe('#601 rail rows show the activity instant the server sends', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('remote row renders the stamped instant', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        remotes: [
          {
            id: 'trueforge',
            kind: 'trueforge',
            title: 'TrueForge box',
            configured: true,
            source: 'config',
            agents: [],
            last_message_at: minutesAgoIso(5),
          },
        ],
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /TrueForge box/ })
    expect(within(row).getByText('5 min ago')).toBeInTheDocument()
  })

  it('remote row without an instant shows no time and no Invalid Date', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        remotes: [
          {
            id: 'quiet',
            kind: 'trueforge',
            title: 'Quiet box',
            configured: true,
            source: 'config',
            agents: [],
          },
        ],
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Quiet box/ })
    expect(within(row).queryByText(TIME_TEXT)).not.toBeInTheDocument()
  })

  it('team row renders the stamped instant', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        rosters: [
          {
            object: 'team_roster',
            id: 'demo-team',
            name: 'Demo Team',
            last_message_at: minutesAgoIso(2),
            members: [{ id: 'codey', kind: 'agent', name: 'Codey', role: 'coder' }],
          },
        ],
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Demo Team/ })
    expect(within(row).getByText('2 min ago')).toBeInTheDocument()
  })

  it('team row without an instant shows no time and no Invalid Date', async () => {
    vi.stubGlobal(
      'fetch',
      mockFetch({
        rosters: [
          {
            object: 'team_roster',
            id: 'idle-team',
            name: 'Idle Team',
            members: [{ id: 'codey', kind: 'agent', name: 'Codey', role: 'coder' }],
          },
        ],
      }),
    )
    renderSidebar()
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Idle Team/ })
    expect(within(row).queryByText(TIME_TEXT)).not.toBeInTheDocument()
  })
})

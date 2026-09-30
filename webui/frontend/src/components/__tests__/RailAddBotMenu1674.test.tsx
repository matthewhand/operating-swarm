/**
 * #1674 — the rail `+` is wired to the Add-bot menu, and picking an agent
 * starts a NEW chat session with it.
 *
 * The component contract lives in `AddBotMenu1674.test.tsx`; this suite pins
 * the *wiring*: the menu lists the rail's own agent rows (one registry), the
 * create actions reach the rail's existing entry points, and an agent pick
 * POSTs a fresh session and navigates to it — never a focus of the open thread.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import AddBotMenu from '../AddBotMenu'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { RAIL_ORDER_STORAGE_KEY } from '../../lib/railOrder'
import { OPEN_TEAM_COMPOSER_EVENT } from '../teamComposerKernel'

function seat(id: string, name: string) {
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
  }
}

const CATALOG = [seat('codey', 'Codey'), seat('stewie', 'Stewie'), seat('ada', 'Ada')]

function jsonOk(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
}

interface RailFetchState {
  sessionPosts: string[]
}

function mockRailFetch(state: RailFetchState) {
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
      return jsonOk({ clis: [], native_consensus: {}, catalog: {}, rail: [] })
    }
    if (url.includes('/v1/herdr-agents')) return jsonOk({ object: 'list', data: [] })
    if (url.includes('/v1/companies')) return jsonOk({ object: 'list', data: [] })
    if (url.includes('/v1/agents/') && url.includes('/sessions') && method === 'POST') {
      state.sessionPosts.push(url)
      const agentId = decodeURIComponent(url.split('/v1/agents/')[1].split('/')[0])
      return jsonOk({
        object: 'agent_session',
        id: `fresh-${agentId}`,
        conversation_id: `fresh-${agentId}`,
        agent_id: agentId,
        title: 'New session',
        snippet: '',
        created_at: '2026-09-29T00:00:00Z',
        updated_at: '2026-09-29T00:00:00Z',
        labels: [],
        cli_session_id: null,
        empty: true,
      })
    }
    if (url.includes('/sessions')) return jsonOk({ object: 'agent_session_list', sessions: [] })
    if (url.includes('/v1/blueprints')) return jsonOk({ object: 'list', data: CATALOG })
    return jsonOk({ object: 'list', data: [] })
  })
}

function LocationProbe({ onChange }: { onChange: (href: string) => void }) {
  const location = useLocation()
  onChange(`${location.pathname}${location.search}`)
  return null
}

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let href = ''
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
        <AgentSidebar open onClose={() => undefined} />
        <LocationProbe onChange={(next) => { href = next }} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, href: () => href }
}

async function openAddMenu() {
  fireEvent.click(await screen.findByTestId('add-bot-menu-trigger'))
  return screen.findByTestId('os-add-bot-menu')
}

describe('#1674 rail Add-bot menu', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('the + opens the menu beside Search, listing the rail’s own agents', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    renderRail()

    const trigger = await screen.findByTestId('add-bot-menu-trigger')
    expect(trigger.closest('.os-rail-search-row')).toBeInTheDocument()
    expect(screen.queryByTestId('os-add-bot-menu')).toBeNull()

    const menu = await openAddMenu()
    const list = within(menu).getByTestId('os-add-bot-menu-agents')
    for (const agent of CATALOG) {
      expect(within(list).getByTestId(`os-add-bot-menu-agent-${agent.id}`)).toHaveTextContent(
        agent.name,
      )
    }
  })

  it('picking an existing agent starts a new session and navigates to it', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    const rail = renderRail()
    await screen.findByTestId('os-agent-rail')

    const menu = await openAddMenu()
    fireEvent.click(within(menu).getByTestId('os-add-bot-menu-agent-stewie'))

    // A brand new session row is created for the picked agent…
    await waitFor(() => expect(state.sessionPosts).toHaveLength(1))
    expect(state.sessionPosts[0]).toContain('/v1/agents/stewie/sessions/')
    // …and the URL carries that new session, not the thread already open.
    await waitFor(() =>
      expect(rail.href()).toBe('/chat?blueprint=stewie&session=fresh-stewie'),
    )
  })

  it('Create new agent opens the rail’s existing Add agent wizard', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    renderRail()

    const menu = await openAddMenu()
    expect(screen.queryByTestId('add-agent-wizard')).toBeNull()
    fireEvent.click(within(menu).getByTestId('os-add-bot-menu-create-bot'))

    expect(await screen.findByTestId('add-agent-wizard')).toBeInTheDocument()
    expect(screen.getByTestId('kind-option-cli')).toBeInTheDocument()
    expect(state.sessionPosts).toHaveLength(0)
  })

  it('Create group chat reaches the existing group-chat composer entry point', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    renderRail()

    const onComposer = vi.fn()
    window.addEventListener(OPEN_TEAM_COMPOSER_EVENT, onComposer)

    const menu = await openAddMenu()
    fireEvent.click(within(menu).getByTestId('os-add-bot-menu-create-group'))

    expect(onComposer).toHaveBeenCalledTimes(1)
    // Same event the rail footer's "Group chats" button dispatches.
    expect(OPEN_TEAM_COMPOSER_EVENT).toBe('swarm:open-team-composer')
    window.removeEventListener(OPEN_TEAM_COMPOSER_EVENT, onComposer)
  })

  it('lists a pin-renamed agent under the name the rail shows', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'ada', name: 'Ada Lovelace' }]),
    )
    localStorage.setItem(RAIL_ORDER_STORAGE_KEY, JSON.stringify([]))
    renderRail()

    const menu = await openAddMenu()
    expect(
      within(menu).getByTestId('os-add-bot-menu-agent-ada'),
    ).toHaveTextContent('Ada Lovelace')
  })

  it('the menu is one component the rail owns — no second agent registry', async () => {
    const state: RailFetchState = { sessionPosts: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    renderRail()
    await screen.findByTestId('os-agent-rail')
    // The rail mounts the shared component rather than a private copy.
    expect(screen.getByTestId('add-bot-menu-trigger').closest('.os-add-bot-menu')).toBeTruthy()
    expect(typeof AddBotMenu).toBe('function')
  })
})

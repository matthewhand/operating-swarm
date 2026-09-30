/**
 * #1709 — adding a chat with an EXISTING agent must reveal + select it.
 *
 * The rail carries one row per seat (`lib/scaleOutSessions.ts`), so the "new
 * chat row" the reporter expects is that seat's row lighting up as the active
 * item. Three things had to be true for the user to see the switch happen:
 *
 *  1. the section holding the seat was expanded (a collapsed section renders
 *     no rows at all, so the active highlight was invisible),
 *  2. the row was scrolled into view inside the rail scroller,
 *  3. the rail knew the seat had a new session at all.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, within, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { RAIL_SECTIONS_STORAGE_KEY } from '../../lib/railSections'
import { listAgentSessions } from '../../lib/scaleOutSessions'

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

function sessionPayload(agentId: string, id: string) {
  return {
    object: 'agent_session',
    id,
    conversation_id: id,
    agent_id: agentId,
    title: 'New session',
    snippet: '',
    created_at: '2026-09-29T00:00:00Z',
    updated_at: '2026-09-29T00:00:00Z',
    labels: [],
    cli_session_id: null,
    empty: true,
  }
}

interface RailFetchState {
  sessionPosts: string[]
  sessionGets: string[]
}

function mockRailFetch(state: RailFetchState) {
  // Each POST mints a distinct id, so "add a second chat" is a second row
  // rather than the same session upserted twice.
  const seq = new Map<string, number>()
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
      const n = (seq.get(agentId) ?? 0) + 1
      seq.set(agentId, n)
      return jsonOk(sessionPayload(agentId, n === 1 ? `fresh-${agentId}` : `fresh-${agentId}-${n}`))
    }
    if (url.includes('/sessions') && method === 'GET') {
      state.sessionGets.push(url)
      return jsonOk({ object: 'agent_session_list', sessions: [] })
    }
    if (url.includes('/v1/blueprints')) return jsonOk({ object: 'list', data: CATALOG })
    return jsonOk({ object: 'list', data: [] })
  })
}

function LocationProbe({ onChange }: { onChange: (href: string) => void }) {
  const location = useLocation()
  onChange(`${location.pathname}${location.search}`)
  return null
}

function renderRail(entry = '/chat?blueprint=codey') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  let href = ''
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[entry]}>
        <AgentSidebar open onClose={() => undefined} />
        <LocationProbe onChange={(next) => { href = next }} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, href: () => href }
}

function collapseSectionFor(agentId: string, sectionId: string) {
  localStorage.setItem(
    RAIL_SECTIONS_STORAGE_KEY,
    JSON.stringify({
      sections: [{ id: sectionId, name: 'Work', collapsed: true }],
      membership: { [agentId]: sectionId },
      unassignedCollapsed: false,
    }),
  )
}

async function addChatWith(agentId: string) {
  fireEvent.click(await screen.findByTestId('add-bot-menu-trigger'))
  const menu = await screen.findByTestId('os-add-bot-menu')
  fireEvent.click(within(menu).getByTestId(`os-add-bot-menu-agent-${agentId}`))
}

function sectionEl(sectionId: string) {
  return document.querySelector(
    `[data-testid="rail-section"][data-section-id="${sectionId}"]`,
  ) as HTMLElement | null
}

function rowEl(agentId: string) {
  return document.querySelector(`.os-agent-row[data-agent-id="${agentId}"]`)
}

describe('#1709 add-chat with an existing agent reveals and selects the new chat', () => {
  const scrolledNodes: Element[] = []
  let scrollIntoView: ReturnType<typeof vi.fn>

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    scrolledNodes.length = 0
    scrollIntoView = vi.fn(function (this: Element) {
      scrolledNodes.push(this)
    })
    Object.defineProperty(Element.prototype, 'scrollIntoView', {
      configurable: true,
      writable: true,
      value: scrollIntoView,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('expands the section holding the agent and marks its row active', async () => {
    const state: RailFetchState = { sessionPosts: [], sessionGets: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    collapseSectionFor('stewie', 'sec_work')

    const rail = renderRail()
    await screen.findByTestId('os-agent-rail')

    // Before: the seat's section is collapsed, so there is no Stewie row at all.
    await waitFor(() => expect(sectionEl('sec_work')).not.toBeNull())
    expect(sectionEl('sec_work')?.dataset.collapsed).toBe('true')
    expect(rowEl('stewie')).toBeNull()

    await addChatWith('stewie')

    await waitFor(() => expect(rail.href()).toBe('/chat?blueprint=stewie&session=fresh-stewie'))
    await waitFor(() => expect(sectionEl('sec_work')?.dataset.collapsed).toBe('false'))
    const row = rowEl('stewie')
    expect(row).not.toBeNull()
    expect(row?.className).toContain('os-agent-row--active')
    expect(row).toHaveAttribute('aria-current', 'page')

    // The highlight MOVED. A row that is lit while the previous seat is still
    // lit too is exactly the "selection unclear" the report called out.
    expect(rowEl('codey')?.className).not.toContain('os-agent-row--active')
    expect(rowEl('codey')).not.toHaveAttribute('aria-current', 'page')
  })

  it('adds the new chat to the seat, so a second one stacks on its row', async () => {
    const state: RailFetchState = { sessionPosts: [], sessionGets: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))

    renderRail()
    await screen.findByTestId('os-agent-rail')

    await addChatWith('stewie')
    await addChatWith('stewie')

    // One row per seat: the rail's own "these chats" signal is the stacked
    // avatar faces, and it only appears once the seat carries 2+ sessions.
    await waitFor(() =>
      expect(rowEl('stewie')?.querySelector('[data-face-count="2"]')).not.toBeNull(),
    )
    expect(
      Array.from(rowEl('stewie')?.querySelectorAll('[data-face-id]') ?? []).map((node) =>
        node.getAttribute('data-face-id'),
      ),
    ).toEqual(expect.arrayContaining(['fresh-stewie', 'fresh-stewie-2']))
  })

  it('scrolls the newly active row into view', async () => {
    const state: RailFetchState = { sessionPosts: [], sessionGets: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))

    renderRail()
    await screen.findByTestId('os-agent-rail')
    scrolledNodes.length = 0

    await addChatWith('stewie')

    await waitFor(() => expect(scrolledNodes).toContain(rowEl('stewie')))
    expect(scrolledNodes[scrolledNodes.length - 1]).toBe(rowEl('stewie'))
  })

  it('records the created chat on the seat, so the row knows one was added', async () => {
    const state: RailFetchState = { sessionPosts: [], sessionGets: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))

    renderRail()
    await screen.findByTestId('os-agent-rail')

    await addChatWith('stewie')

    // The rail row reads the scale-out cache, so the created Django session
    // has to land there or the sidepane shows nothing new.
    await waitFor(() =>
      expect(listAgentSessions('stewie').map((row) => row.id)).toEqual(['fresh-stewie']),
    )
  })

  it('reveals only the new seat — a collapse the operator made sticks', async () => {
    const state: RailFetchState = { sessionPosts: [], sessionGets: [] }
    vi.stubGlobal('fetch', mockRailFetch(state))
    localStorage.setItem(
      RAIL_SECTIONS_STORAGE_KEY,
      JSON.stringify({
        sections: [{ id: 'sec_work', name: 'Work', collapsed: false }],
        membership: { codey: 'sec_work', stewie: 'sec_work' },
        unassignedCollapsed: false,
      }),
    )

    // Already on Codey, inside "Work".
    const rail = renderRail('/chat?blueprint=codey')
    await screen.findByTestId('os-agent-rail')
    await waitFor(() => expect(sectionEl('sec_work')).not.toBeNull())

    fireEvent.click(
      within(sectionEl('sec_work') as HTMLElement).getByLabelText('Collapse Work (2)'),
    )
    expect(sectionEl('sec_work')?.dataset.collapsed).toBe('true')

    // Ada is not in "Work", so revealing her seat must not stomp it open.
    await addChatWith('ada')
    await waitFor(() => expect(rail.href()).toBe('/chat?blueprint=ada&session=fresh-ada'))
    expect(sectionEl('sec_work')?.dataset.collapsed).toBe('true')
  })
})

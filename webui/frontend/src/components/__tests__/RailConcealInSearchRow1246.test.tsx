/**
 * #1246 — the collapse toggle lives in the rail's search/header row, not on
 * the mid-divider.
 *
 * What rotted here, and why this file now renders instead of grepping
 * ---------------------------------------------------------------------
 * The old assertion was a *character window* over the component's source text:
 *
 *     expect(sidebar).toMatch(
 *       /os-rail-search-row[\s\S]{0,1600}?<SidebarConcealButton onClick=\{concealSidebar\}/,
 *     )
 *
 * Three independent defects in one line:
 *
 *  1. It measured source, not structure. `[\s\S]{0,1600}?` says "these two
 *     tokens appear within 1600 characters of each other in the file". It
 *     cannot tell a sibling from a cousin: the toggle could be lifted out of
 *     the search row into a different subtree, or reordered after the row
 *     closed, and the needle would still match as long as the file stayed
 *     under 1600 characters wide. It went red the moment #1674 and the
 *     `sidebar/` package split widened the row — a correct refactor, an intact
 *     behaviour, and a fixed-number failure. A window is not a contract: it
 *     encodes "how big the file may get" and calls that a placement rule.
 *  2. It matched the call *spelling*. `onClick={concealSidebar}` breaks on
 *     `onClick={hideRail}`, on an extracted handler, or on a wrapper.
 *  3. It asserted nothing about the rendered control. It could not catch the
 *     toggle rendering with no accessible name, or the `data-testid` that
 *     other suites (and the Playwright rail-geometry specs) actually drive
 *     being dropped.
 *
 * The replacement renders the real rail and asserts DOM containment, which is
 * the property the old window was approximating. It is strictly stronger on
 * every axis above: it fails if the control leaves the row, and it also fails
 * if the control stops being findable by its accessible name.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

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

const CATALOG = [seat('codey', 'Codey'), seat('stewie', 'Stewie')]

function jsonOk(data: unknown) {
  return { ok: true, status: 200, json: async () => data } as Response
}

function mockRailFetch() {
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
        pinned: [],
      })
    }
    if (url.includes('/v1/blueprints')) {
      return jsonOk({ object: 'list', data: CATALOG })
    }
    if (url.includes('/v1/cli-agents') || url.includes('/v1/remotes')) {
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/team-rosters')) {
      return jsonOk({ object: 'list', data: [] })
    }
    return jsonOk({ object: 'list', data: [] })
  })
}

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat?blueprint=codey']}>
        <AgentSidebar open onClose={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('#1246: the collapse toggle is a child of the rail search row', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('renders the conceal control inside .os-rail-search-row', async () => {
    vi.stubGlobal('fetch', mockRailFetch())
    renderRail()

    const toggle = await screen.findByTestId('sidebar-conceal')

    // THE property. Real DOM containment, not a character window: the control
    // must be a descendant of the search row, which is what puts it at the
    // pane's top-right. Lifting it into any other subtree fails here even
    // though the old 1600-char window would still have matched.
    const searchRow = document.querySelector('.os-rail-search-row')
    expect(searchRow).not.toBeNull()
    expect(searchRow!.contains(toggle)).toBe(true)

    // It is reachable by its accessible name, not only by testid — the
    // Playwright rail specs and the a11y suite both use this name.
    expect(screen.getByRole('button', { name: /collapse sidebar/i })).toBe(toggle)
  })

  it('is the last control in the row, so it renders at the pane top-right', async () => {
    vi.stubGlobal('fetch', mockRailFetch())
    renderRail()

    const toggle = await screen.findByTestId('sidebar-conceal')
    const searchRow = document.querySelector('.os-rail-search-row')!

    // Trailing placement is the actual design claim ("top-right of the search
    // row"). A character window cannot express order at all; index comparison
    // on rendered children can.
    const buttons = Array.from(searchRow.querySelectorAll('button'))
    expect(buttons.length).toBeGreaterThan(1)
    expect(buttons[buttons.length - 1]).toBe(toggle)
  })
})

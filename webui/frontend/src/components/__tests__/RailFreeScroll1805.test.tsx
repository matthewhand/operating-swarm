/**
 * #1805 — free-scrolling the sidepane must never snap back to the selection.
 *
 * Dogfood report: scroll the agent rail away from the selected seat and
 * something dragged the view straight back. The cause was
 * `features/sidebar/useRailReveal`: its `scrollIntoView` effect listed
 * `visibleRowIds` in its dependency array, and that is a FRESH array on every
 * catalog rebuild — a health tick, a remotes refresh, a react-query refocus
 * refetch, a reorder. So the rail re-scrolled the selected row on every tick
 * while the operator was reading/scrolling something else.
 *
 * This is the whole-rail version of the contract, driven through the real
 * component:
 *   1. free scroll + catalog churn  -> no scroll at all,
 *   2. click-select                 -> exactly one scroll, on that seat,
 *   3. Alt+Arrow browse             -> exactly one scroll, on the new seat,
 * and the churn that follows each of those still moves nothing.
 *
 * The hook-level half (the latch itself) lives in
 * `features/sidebar/__tests__/useRailReveal.1709.test.ts`.
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { act, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
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

const CATALOG = [seat('codey', 'Codey'), seat('stewie', 'Stewie'), seat('ada', 'Ada')]

function jsonOk(data: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => data,
  } as Response
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
      })
    }
    if (url.includes('/v1/cli-agents')) {
      return jsonOk({ clis: [], native_consensus: {}, catalog: {}, rail: [] })
    }
    if (url.includes('/v1/blueprints')) return jsonOk({ object: 'list', data: CATALOG })
    if (url.includes('/sessions') && url.includes('/v1/agents/')) {
      return jsonOk({ object: 'agent_session_list', sessions: [] })
    }
    return jsonOk({ object: 'list', data: [] })
  })
}

function LocationProbe({ onChange }: { onChange: (href: string) => void }) {
  const location = useLocation()
  onChange(`${location.pathname}${location.search}`)
  return null
}

function renderRail(entry: string) {
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
  return {
    ...utils,
    href: () => href,
    /** A catalog rebuild: exactly what a health tick / refocus refetch does. */
    async churnCatalog() {
      await act(async () => {
        await client.invalidateQueries()
      })
    },
  }
}

function rowEl(agentId: string) {
  // eslint-disable-next-line testing-library/no-node-access -- the rail row's data-agent-id is the assertion
  return document.querySelector(`.os-agent-row[data-agent-id="${agentId}"]`) as HTMLElement | null
}

function activeRowEl() {
  // eslint-disable-next-line testing-library/no-node-access -- .os-agent-row--active is a class hook, not a role
  return document.querySelector('.os-agent-row--active') as HTMLElement | null
}

function railScroller() {
  // eslint-disable-next-line testing-library/no-node-access -- the scroller is the element under test
  return document.querySelector('.os-rail-scroller') as HTMLElement | null
}

/** The operator free-scrolling: the scroller moves, and the rail hears it. */
function freeScroll(px: number) {
  const nav = railScroller()
  if (!nav) throw new Error('no rail scroller')
  nav.scrollTop = px
  fireEvent.scroll(nav)
}

describe('#1805 the sidepane does not snap back to the selection on free scroll', () => {
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

  it('free scroll plus catalog churn never re-reveals the selected seat', async () => {
    vi.stubGlobal('fetch', mockRailFetch())
    const view = renderRail('/chat?blueprint=codey')
    await screen.findByTestId('os-agent-rail')
    await waitFor(() => expect(rowEl('codey')).not.toBeNull())

    // The rail revealed the deep-linked seat on open (that is #1709 and it is
    // the one reveal this test starts from).
    expect(scrolledNodes).toContain(rowEl('codey'))
    scrolledNodes.length = 0

    // The operator scrolls away, and the catalog keeps rebuilding under them.
    freeScroll(240)
    await view.churnCatalog()
    freeScroll(480)
    await view.churnCatalog()
    await waitFor(() => expect(rowEl('ada')).not.toBeNull())

    expect(scrolledNodes).toEqual([])
  })

  it('click-selects the seat once, and later churn still does not re-reveal it', async () => {
    vi.stubGlobal('fetch', mockRailFetch())
    const view = renderRail('/chat?blueprint=codey')
    await screen.findByTestId('os-agent-rail')
    await waitFor(() => expect(rowEl('stewie')).not.toBeNull())
    scrolledNodes.length = 0

    fireEvent.click(rowEl('stewie') as HTMLElement)
    await waitFor(() => expect(view.href()).toBe('/chat?blueprint=stewie'))
    await waitFor(() => expect(scrolledNodes).toEqual([rowEl('stewie')]))

    // Free scroll away, then the list rebuilds twice: the reveal is spent.
    freeScroll(300)
    await view.churnCatalog()
    freeScroll(600)
    await view.churnCatalog()

    expect(scrolledNodes).toEqual([rowEl('stewie')])
  })

  it('Alt+Arrow browse reveals the newly selected seat once per key', async () => {
    vi.stubGlobal('fetch', mockRailFetch())
    // Opened on Ada, so the browse step has somewhere to go.
    const view = renderRail('/chat?blueprint=ada')
    await screen.findByTestId('os-agent-rail')
    await waitFor(() => expect(rowEl('ada')).not.toBeNull())
    scrolledNodes.length = 0

    fireEvent.keyDown(window, { key: 'ArrowDown', altKey: true })

    // The step moved the selection (the sequence's first entry, whichever seat
    // that is) and revealed that seat — once.
    await waitFor(() => expect(view.href()).not.toBe('/chat?blueprint=ada'))
    const active = activeRowEl()
    expect(active).not.toBeNull()
    await waitFor(() => expect(scrolledNodes).toEqual([active]))

    // The same churn that used to fight the operator's scroll.
    freeScroll(200)
    await view.churnCatalog()

    expect(scrolledNodes).toEqual([active])
  })
})

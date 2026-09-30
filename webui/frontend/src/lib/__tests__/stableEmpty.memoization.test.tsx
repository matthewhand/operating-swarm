/**
 * The `?? []` memoization break, measured on identity rather than on source.
 *
 * `const rows = query.data?.data ?? []` allocates a new array on every render
 * while the query is empty, and anything listing `rows` in a `useMemo` /
 * `useEffect` / `useCallback` dep list then misses its cache on every render.
 * When that hook talks to the network it is a request flood; the seat-health
 * and remote-health polls were both downstream of this.
 *
 * The fix is `lib/stableEmpty`. This file pins the two things it promises:
 * one shared identity, and the call sites actually using it. The call-site
 * assertions run the real components, so a regression shows up as a request
 * count rather than as a string in a source file.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { emptyArray, emptyObject } from '../stableEmpty'
import { __setSeatHealthProber, resetSeatHealth, type SeatRef } from '../seatHealth'
import type { SeatHealthRow } from '../api/seatHealth'

describe('stableEmpty', () => {
  it('hands back the SAME array on every call', () => {
    // Identity, not equality: a value-equal fresh array is the whole defect.
    expect(emptyArray<string>()).toBe(emptyArray<string>())
    expect(emptyObject<Record<string, number>>()).toBe(
      emptyObject<Record<string, number>>(),
    )
  })

  it('is empty, so a caller reading it gets the same answer as before', () => {
    expect(emptyArray()).toHaveLength(0)
    expect(Object.keys(emptyObject())).toHaveLength(0)
  })
})

/**
 * The component-level proof. `AgentSidebar` builds its seat list from `remotes`
 * — which is `remotesQuery.data ?? []` — and the seat poll's lifetime hangs off
 * that list. While the remotes query is pending the list is empty, and the
 * component re-renders for every unrelated state change; an unstable empty
 * would re-fire the publish effect each time. With the fix, a re-render storm
 * during the pending window must add zero requests.
 */
const BLUEPRINTS = ['codey', 'stewie', 'gate'].map((id) => ({
  id,
  object: 'blueprint' as const,
  name: id[0].toUpperCase() + id.slice(1),
  description: 'Mock agent',
  abbreviation: null,
  required_mcp_servers: [] as string[],
  tags: [] as string[],
  installed: true,
  compiled: true,
  rail: true,
}))

const probeMock = vi.fn(async (batch: SeatRef[]): Promise<SeatHealthRow[]> =>
  batch.map((s) => ({
    seat_id: s.seatId,
    kind: s.kind,
    state: 'ok' as const,
    reason: '',
    latency_ms: 1,
    checked_at: 1_700_000_000_000,
    broken: false,
  })),
)

/** The remotes query hangs for the whole test — see `mockFetch`. */
function mockFetch() {
  return vi.fn(async (input: RequestInfo) => {
    const url = String(input)
    const list = (data: unknown) =>
      ({ ok: true, status: 200, json: async () => ({ object: 'list', data }) }) as Response
    if (url.includes('remotes_catalog.json') || url.includes('/v1/remotes/')) {
      // Deliberately hang: this test is about the EMPTY-query window. It never
      // resolves, so the rail spends the whole test in the `?? []` state.
      await new Promise<void>(() => {})
      return list([])
    }
    if (url.includes('team-rosters') || url.includes('team_rosters')) return list([])
    if (url.includes('herdr-agents')) return list([])
    if (url.includes('agents/designs')) return list([])
    if (url.includes('/v1/cli-agents')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ clis: [], native_consensus: {}, catalog: {}, rail: [] }),
      } as Response
    }
    if (url.includes('/v1/preferences')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        }),
      } as Response
    }
    if (url.includes('api.github.com')) {
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }
    return list(BLUEPRINTS)
  })
}

beforeEach(() => {
  localStorage.clear()
  resetSeatHealth()
  probeMock.mockClear()
  __setSeatHealthProber((batch) => probeMock(batch))
  vi.stubGlobal('fetch', mockFetch())
})

afterEach(() => {
  resetSeatHealth()
  __setSeatHealthProber(null)
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('an empty query result is not a traffic event', () => {
  it('re-rendering the rail with the query still pending sends nothing new', async () => {
    const AgentSidebar = (await import('../../components/AgentSidebar')).default
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
    })
    // Let every query that CAN resolve, resolve. The remotes query hangs, so
    // the rail spends the whole test in the `?? []` window.
    await new Promise((resolve) => setTimeout(resolve, 200))

    const afterFirstPass = probeMock.mock.calls.length

    // Now churn: the poll interval and the store both re-render the rail many
    // times over. An unstable empty would re-fire the publish effect on every
    // one of them, and the count would climb with each.
    for (let i = 0; i < 25; i += 1) {
      client.invalidateQueries({ queryKey: ['blueprints'] })
      await new Promise((resolve) => setTimeout(resolve, 4))
    }

    expect(probeMock.mock.calls.length).toBe(afterFirstPass)
    // And every call that WAS made was batch-shaped: the whole rail in one
    // request, never one request per seat. A single-element call is the defect.
    expect(afterFirstPass).toBeGreaterThan(0)
    for (const call of probeMock.mock.calls) expect(call[0].length).toBeGreaterThan(1)
  })
})

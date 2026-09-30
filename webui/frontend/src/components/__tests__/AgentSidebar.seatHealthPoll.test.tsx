/**
 * #1658 follow-up — the rail owns the health poll's lifetime.
 *
 * The effect that publishes the seat set had no cleanup, so `stopTrackingSeatHealth`
 * was dead code outside the store and the 60s interval outlived the rail. It
 * also re-ran on every `remotes` / `visibleAgents` / `hiddenAgents` identity
 * change, and because it re-probed on every call that turned a rail rebuild
 * into a burst of one request per seat.
 *
 * Counting `prober` invocations (the store's transport seam) is counting HTTP
 * requests, so these assertions are the traffic. Hiding and unhiding an agent
 * is used as the identity churn on purpose: it moves a row between the visible
 * and hidden lists, so `visibleAgents` and `hiddenAgents` are both new arrays
 * carrying the *same* set of seats in a *different order*.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import {
  HIDDEN_AGENTS_CHANGED_EVENT,
  HIDDEN_AGENTS_STORAGE_KEY,
} from '../../lib/hiddenAgents'
import {
  __setSeatHealthProber,
  resetSeatHealth,
  type SeatRef,
} from '../../lib/seatHealth'
import type { SeatHealthRow } from '../../lib/api/seatHealth'

const BLUEPRINTS = ['codey', 'stewie', 'gate', 'skeptic', 'cos'].map((id) => ({
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

/** Four operator-added remotes, so the tracked set is api + remote. */
const REMOTES = ['r1', 'r2', 'r3', 'r4'].map((id) => ({
  id,
  object: 'remote' as const,
  kind: 'remote',
  title: id,
  source: 'operator',
  configured: true,
  usable: true,
  agents: [],
}))

function mockFetch() {
  return vi.fn(async (input: RequestInfo) => {
    const url = String(input)
    const list = (data: unknown) =>
      ({ ok: true, status: 200, json: async () => ({ object: 'list', data }) }) as Response
    if (url.includes('/v1/remotes/') || url.includes('remotes_catalog.json')) {
      return list(REMOTES)
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

const TICK = 60_000

function renderRail() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/chat']}>
        <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, client }
}

/** Move a seat between the visible and hidden lists without changing the set. */
async function churnHiddenIds(hidden: string[]) {
  localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, JSON.stringify(hidden))
  await act(async () => {
    window.dispatchEvent(new Event(HIDDEN_AGENTS_CHANGED_EVENT))
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
  vi.useRealTimers()
  vi.unstubAllGlobals()
  localStorage.clear()
})

describe('AgentSidebar owns the seat health poll lifetime', () => {
  it('probes the whole rail in one call per change, never one call per seat', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderRail()

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    expect(probeMock.mock.calls.length).toBeGreaterThan(0)
    // The rail loads in a couple of passes, so a handful of batches is right.
    // One request per seat per pass was 33 batches for this 10-seat rail.
    expect(probeMock.mock.calls.length).toBeLessThanOrEqual(3)
    // The batch endpoint takes a `seats` array. A single-element call is the
    // defect: one HTTP request per seat per tick.
    for (const call of probeMock.mock.calls) {
      expect(call[0].length).toBeGreaterThan(1)
    }
    // Once loaded: 5 api seats + support + 4 remotes, all in one call.
    const last = probeMock.mock.calls[probeMock.mock.calls.length - 1]
    expect(last[0]).toHaveLength(10)
  })

  it('hiding and unhiding a seat — same seats, new array identities — sends nothing', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    renderRail()

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    const afterMount = probeMock.mock.calls.length
    expect(afterMount).toBeGreaterThan(0)

    await churnHiddenIds(['codey'])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    await churnHiddenIds(['codey', 'stewie'])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    await churnHiddenIds([])
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })

    // The seat set never changed, so no rebuild may reach the network.
    expect(probeMock).toHaveBeenCalledTimes(afterMount)
  })

  it('stops polling when the rail unmounts', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    const clearSpy = vi.spyOn(window, 'clearInterval')
    const { unmount } = renderRail()

    await waitFor(() => {
      expect(screen.getByRole('navigation', { name: 'Agent list' })).toBeInTheDocument()
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(50)
    })
    const afterMount = probeMock.mock.calls.length

    unmount()
    await act(async () => {
      await vi.advanceTimersByTimeAsync(TICK * 3)
    })

    expect(probeMock).toHaveBeenCalledTimes(afterMount)
    expect(clearSpy).toHaveBeenCalled()
  })
})

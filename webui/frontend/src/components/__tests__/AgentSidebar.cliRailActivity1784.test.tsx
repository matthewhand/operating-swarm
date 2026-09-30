/**
 * #1784 — the rail-activity fan-out is capped.
 *
 * `cliActivityQuery` asked for one `fetchCliSessions` per CLI seat, all at once,
 * on every change of its query key. `fetchCliSessions` goes through `apiGet`, so
 * the burst inherited `pacedApiGet`'s `MAX_CONCURRENT_GETS = 4` gate — but that
 * gate PACES a burst, it does not reduce the request COUNT. With 20 CLI seats, 20
 * requests saturate the shared 4-slot gate that every other cold-mount read
 * queues behind, so first paint stalls.
 *
 * This measures the thing itself: a high-water mark of concurrent
 * `fetchCliSessions` invocations, recorded by the stub. It does not inspect the
 * source, count `fetch` calls, or assume a pacing constant.
 *
 * The second half matters as much as the first. "It stopped bursting" is also
 * what a broken fan-out looks like — if the worker dropped seats, capped at one
 * GET per key change and never completed, or swallowed the results, a
 * concurrency assertion alone would pass while the rail silently showed no
 * timestamps at all. So the test also asserts every id lands in the returned
 * map, carrying the instant its own seat reported.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import * as cliSessions from '../../lib/cliSessions'
import type { CliSessionList } from '../../lib/cliSessions'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

/** Five host CLIs, so five derived CLI seats land on the rail. */
const CLI_NAMES = ['alpha', 'bravo', 'charlie', 'delta', 'echo']
const CLI_IDS = CLI_NAMES.map((name) => `${name}_agent`)
/** #1784 caps the fan-out at this width. */
const MAX_CONCURRENT_ACTIVITY_READS = 2
/** `formatRailTimestamp` treats this as "5 min ago"; only the ms value is asserted. */
const ACTIVITY_ISO = new Date(Date.now() - 5 * 60_000).toISOString()
const ACTIVITY_MS = Date.parse(ACTIVITY_ISO)

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
    json: async () => data,
  } as Response
}

/**
 * The map the fan-out resolved to, read back off the cache.
 *
 * `findAll` is used instead of `getQueryData` so the test never hardcodes the
 * query key's join format, and it cannot simply be `[0]`: on the first render
 * `cliAgentsForActivity` is still empty, so the cache also holds a
 * `['cli-rail-activity', '']` entry that `enabled: length > 0` leaves pending
 * forever. Only the entry that actually resolved carries the fan-out result.
 */
function activityMap(client: QueryClient): Record<string, number> | undefined {
  const resolved = client
    .getQueryCache()
    .findAll({ queryKey: ['cli-rail-activity'], exact: false })
    .filter((query) => query.state.status === 'success')
  return resolved[0]?.state.data as Record<string, number> | undefined
}

function mockFetch() {
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
      return jsonOk({ object: 'list', data: [] })
    }
    if (url.includes('/v1/remotes')) {
      return jsonOk({
        object: 'list',
        data: [],
        configured: [],
        kinds: [],
        team_members: [],
      })
    }
    if (url.includes('/v1/cli-agents')) {
      return jsonOk({
        clis: CLI_NAMES,
        known: CLI_NAMES,
        // `rail: []` keeps the generic `cli_agent` seat off the rail, so the
        // five derived seats are the ONLY thing the activity query has to read.
        rail: [],
        configured: [],
        discovered: CLI_NAMES,
        installed: CLI_NAMES,
        suggestions: {},
        native_consensus: {},
        catalog: {},
      })
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

describe('#1784 the CLI rail-activity fan-out is capped', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
  })

  afterEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('reads at most 2 CLI session lists at a time and still reports every seat', async () => {
    vi.stubGlobal('fetch', mockFetch())

    /* A gate the test opens and closes itself. Each invocation registers a
       release; `inFlight` is sampled on entry, so the recorded maximum is the
       true simultaneous-invocation count, not a count of resolved calls. */
    const releases: Array<() => void> = []
    let inFlight = 0
    let maxConcurrent = 0
    let completed = 0

    const fetchSpy = vi
      .spyOn(cliSessions, 'fetchCliSessions')
      .mockImplementation((agentId: string, cli: string) => {
        inFlight += 1
        if (inFlight > maxConcurrent) maxConcurrent = inFlight
        return new Promise<CliSessionList>((resolve) => {
          releases.push(() => {
            inFlight -= 1
            completed += 1
            resolve({
              object: 'cli_session_list',
              agent_id: agentId,
              cli,
              can_list: true,
              sessions: [
                {
                  id: `sid-${agentId}`,
                  title: `Thread for ${cli}`,
                  snippet: 'work',
                  updated_at: ACTIVITY_ISO,
                  source: 'provider',
                },
              ],
              recent: [],
              empty_reason: null,
              activity_sot: 'provider',
            })
          })
        })
      })

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    /* Release whatever is in flight, repeatedly, until all five have settled.
       Reading the gate is the measurement; the retry is what lets a width-limited
       worker take its next pair. */
    await waitFor(() => {
      const wave = releases.splice(0)
      wave.forEach((release) => release())
      expect(completed).toBe(CLI_NAMES.length)
    })

    // Non-vacuity on the fixture: all five seats really did reach the fan-out.
    expect(fetchSpy.mock.calls.map(([id, cli]) => `${id}:${cli}`).sort()).toEqual(
      CLI_NAMES.map((name) => `${name}_agent:${name}`).sort(),
    )

    /* The fix. On the unfixed `Promise.all` fan-out every seat is invoked in the
       same synchronous tick, so this reads 5. */
    expect(
      maxConcurrent,
      `cli-rail-activity issued ${maxConcurrent} concurrent session reads; ` +
        `a cold mount must not hand ${maxConcurrent} requests to the shared ` +
        `${4}-slot GET pacer that every other first-paint read queues behind`,
    ).toBeLessThanOrEqual(MAX_CONCURRENT_ACTIVITY_READS)

    // And the cap must not have quietly dropped seats on the way through.
    const activity = activityMap(client)
    expect(activity, 'cli-rail-activity resolved to no map').toBeDefined()
    expect(Object.keys(activity ?? {}).sort()).toEqual([...CLI_IDS].sort())
    for (const id of CLI_IDS) {
      expect(activity?.[id], `${id} has no activity stamp`).toBe(ACTIVITY_MS)
    }
  })

  it('leaves an honest gap: one seat failing still yields the other four', async () => {
    vi.stubGlobal('fetch', mockFetch())

    const failing = CLI_NAMES[0]
    let concurrent = 0
    let maxConcurrent = 0
    const fetchSpy = vi
      .spyOn(cliSessions, 'fetchCliSessions')
      .mockImplementation(async (agentId: string, cli: string) => {
        concurrent += 1
        if (concurrent > maxConcurrent) maxConcurrent = concurrent
        try {
          await new Promise((resolve) => setTimeout(resolve, 0))
          if (agentId === `${failing}_agent`) throw new Error('429 rate limited')
          return {
            object: 'cli_session_list',
            agent_id: agentId,
            cli,
            can_list: true,
            sessions: [
              {
                id: `sid-${agentId}`,
                title: 'Thread',
                snippet: 'work',
                updated_at: ACTIVITY_ISO,
                source: 'provider',
              },
            ],
            recent: [],
            empty_reason: null,
            activity_sot: 'provider',
          } as CliSessionList
        } finally {
          concurrent -= 1
        }
      })

    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    })
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    await waitFor(
      () => {
        expect(fetchSpy).toHaveBeenCalledTimes(CLI_NAMES.length)
        expect(Object.keys(activityMap(client) ?? {}).length).toBe(CLI_NAMES.length - 1)
      },
      { timeout: 4000 },
    )

    expect(fetchSpy).toHaveBeenCalledTimes(CLI_NAMES.length)
    expect(maxConcurrent).toBeLessThanOrEqual(MAX_CONCURRENT_ACTIVITY_READS)

    // The per-seat try/catch survives the worker: a rejected seat is ABSENT, not
    // a zero, and it does not take the rest of the fan-out down with it.
    const activity = activityMap(client)
    expect(activity).not.toHaveProperty(`${failing}_agent`)
    expect(Object.keys(activity ?? {}).sort()).toEqual(
      CLI_IDS.filter((id) => id !== `${failing}_agent`).sort(),
    )
  })
})

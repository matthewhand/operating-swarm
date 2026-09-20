/**
 * #594 — the rail painted every product-mode-gated surface on load and then
 * dropped the gated groups once `GET /v1/cli-agents/` settled, because a fetch
 * still in flight was read as "a legacy server that advertises nothing".
 *
 * The invariant asserted here is **monotonicity**: a row that has been painted is
 * never removed. Strict set-equality across settling is unreachable by design —
 * the CLI and API seats *are* the `/v1/cli-agents/` payload, so they cannot exist
 * before it resolves — but a rail that only ever gains rows is legible, which is
 * what the ticket asked for. The specific defect is the opposite direction, and
 * the first test fails on the unfixed tree because `codey` (a blueprint seat) is
 * painted while the modes are unknown and then taken away.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'

/** A catalog seat. `kind` picks which product mode owns it. */
function blueprint(id: string, name: string, kind?: string) {
  return {
    id,
    object: 'blueprint',
    name,
    description: name,
    abbreviation: null,
    required_mcp_servers: [] as string[],
    tags: [] as string[],
    installed: true,
    compiled: true,
    rail: true,
    ...(kind ? { kind } : {}),
  }
}

/**
 * `codey` is a blueprint seat (gated). `localc` is a CLI seat, and the `cli`
 * mode is on in both the pending defaults and the settled payload — so it is the
 * marker that proves the *catalog* feed (not the modes payload) has landed.
 */
const BLUEPRINTS = [blueprint('codey', 'Codey'), blueprint('localc', 'Local C', 'cli')]

/** Kind rows come from `/v1/cli-agents/`, alongside the modes themselves. */
const CLI_RAIL = [
  {
    id: 'cli_agent',
    object: 'cli.agent',
    name: 'cli_agent',
    cli: 'grok',
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

const SHIPPED_MODES = { cli: true, api: false, blueprint: false, team: false, remote: false }

function ok(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload } as Response
}

describe('#594 product modes settle before they paint the rail', () => {
  let resolveCli: (value: Response) => void

  /** `/v1/cli-agents/` is held open so "in flight" is a real, observed state. */
  function mockFetch() {
    return vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/cli-agents')) {
        return new Promise<Response>((resolve) => {
          resolveCli = resolve
        })
      }
      if (url.includes('/v1/herdr-agents')) return ok({ object: 'list', data: [] })
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return ok({ object: 'list', data: [] })
      }
      if (url.includes('/v1/agents/designs')) return ok({ object: 'list', data: [] })
      if (url.includes('remotes')) return ok({ object: 'list', data: [] })
      if (url.includes('/v1/preferences')) {
        return ok({
          object: 'user_preferences',
          principal: 'session:test',
          guest: true,
          empty: true,
          favourites: [],
          hidden_agents: [],
        })
      }
      if (url.includes('sessions')) return ok({ object: 'list', data: [] })
      if (url.includes('api.github.com')) return { ok: false, status: 404 } as Response
      return ok({ object: 'list', data: BLUEPRINTS })
    })
  }

  function renderRail() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    return render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open onClose={() => undefined} onOpenSearch={() => undefined} />
        </MemoryRouter>
      </QueryClientProvider>,
    )
  }

  function rowIds() {
    return Array.from(document.querySelectorAll('[data-rail-id]')).map((node) =>
      node.getAttribute('data-rail-id'),
    )
  }

  /** Let the immediately-resolving feeds (blueprints, teams, remotes, herdr) land. */
  async function flush() {
    await act(async () => {
      await Promise.resolve()
      await Promise.resolve()
    })
  }

  /**
   * Resolve the modes payload and wait until it has actually been applied — the
   * caller names the row (or notice) that only exists once it has.
   */
  async function settle(payload: unknown, applied: () => void) {
    await act(async () => {
      resolveCli(ok(payload))
    })
    await waitFor(applied)
  }

  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('paints gated rows during flight (all-on workaround), and settles an explicit off by removing them', async () => {
    renderRail()
    // 2026-09-20: shipped in-flight defaults are all-on (mode-toggle workaround),
    // so the first paint shows every feed row — including gated `codey`.
    await flush()
    await waitFor(() => expect(rowIds()).toContain('localc'))
    const before = rowIds()
    expect(before).toContain('codey')

    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: SHIPPED_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    // Rows whose modes stay on are never removed; an *advertised* off is.
    expect(rowIds()).toContain('cli_agent')
    expect(rowIds()).not.toContain('codey')
    expect(rowIds()).not.toContain('api_agent')
  })

  it('an all-on settled payload keeps every painted row (superset guarantee)', async () => {
    renderRail()
    await flush()
    await waitFor(() => expect(rowIds()).toContain('localc'))
    const before = rowIds()

    await settle(
      { clis: ['grok'], rail: CLI_RAIL, modes: { cli: true, api: true, blueprint: true, team: true, remote: true } },
      () => expect(rowIds()).toContain('api_agent'),
    )

    const after = rowIds()
    expect(after).toContain('api_agent')
    for (const id of before) expect(after).toContain(id)
  })

  it('#685: a disabled kind is completely absent — no notice, no enable-in-Settings copy', async () => {
    renderRail()
    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: SHIPPED_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    expect(rowIds()).not.toContain('codey')
    expect(rowIds()).not.toContain('api_agent')
    // The informative-noise pattern #685 bans, gone from every rail surface.
    expect(screen.queryByTestId('rail-mode-notice')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('hidden by product modes')
    expect(document.body.textContent).not.toContain('enable in Settings')
  })

  it('never counts a mode-gated row as Hidden — Hide and a surface switch are different axes', async () => {
    renderRail()
    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: SHIPPED_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    // `codey` and `api_agent` are gated out of the rows above, yet Hidden stays
    // empty and offers no Unhide — the two reasons a row can be absent stay apart.
    expect(screen.getByTestId('hidden-bots-row').getAttribute('data-empty')).toBe('true')
    expect(screen.queryByTestId('os-hidden-bots-count')).not.toBeInTheDocument()
  })

  it('keeps the #149 legacy contract: a payload with no modes key shows every surface', async () => {
    renderRail()
    await flush()
    await waitFor(() => expect(rowIds()).toContain('localc'))

    await settle({ clis: ['grok'], rail: CLI_RAIL }, () =>
      expect(rowIds()).toContain('api_agent'),
    )

    // A settled payload that advertises no `modes` key is the legacy case and
    // keeps every surface, exactly as #149 defined it.
    await waitFor(() => expect(rowIds()).toContain('codey'))
    expect(rowIds()).toContain('api_agent')
  })
})

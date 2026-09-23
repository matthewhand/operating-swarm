/**
 * #736 — product-modes gating is RETIRED: rail surfaces are **always-on if
 * configured**. The former behavior (a settled `settings.product_modes`
 * payload removing painted rows, #594/#151) is gone — a rail that paints a
 * row never loses it to a modes advertisement, no matter what the payload
 * says. The #685 invariant survives unchanged: a disabled kind is absent
 * with no notice and no "enable in Settings" copy, because nothing is
 * ever disabled.
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
 * `codey` is a blueprint seat. `localc` is a CLI seat — the marker that
 * proves the catalog feed has landed.
 */
const BLUEPRINTS = [blueprint('codey', 'Codey'), blueprint('localc', 'Local C', 'cli')]

/** Kind rows come from `/v1/cli-agents/`, alongside the (now advisory) modes. */
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

/** A legacy payload advertising every mode OFF — now ignored (#736). */
const ALL_OFF_MODES = { cli: false, api: false, blueprint: false, team: false, remote: false }

function ok(payload: unknown) {
  return { ok: true, status: 200, json: async () => payload } as Response
}

describe('#736 the rail is always-on if configured', () => {
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

  /** Resolve the modes payload and wait until it has actually been applied. */
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

  it('a painted row is never removed by a modes advertisement (monotonic, always-on)', async () => {
    renderRail()
    await flush()
    await waitFor(() => expect(rowIds()).toContain('localc'))
    const before = rowIds()
    expect(before).toContain('codey')

    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: ALL_OFF_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    // #736: every row painted before the settle survives it — the off
    // advertisement is advisory, never a gate.
    for (const id of before) expect(rowIds()).toContain(id)
    expect(rowIds()).toContain('cli_agent')
    expect(rowIds()).toContain('api_agent')
    expect(rowIds()).toContain('codey')
  })

  it('#685: no notice, no enable-in-Settings copy — nothing is ever disabled', async () => {
    renderRail()
    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: ALL_OFF_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    // The informative-noise pattern #685 bans, gone from every rail surface.
    expect(screen.queryByTestId('rail-mode-notice')).not.toBeInTheDocument()
    expect(document.body.textContent).not.toContain('hidden by product modes')
    expect(document.body.textContent).not.toContain('enable in Settings')
  })

  it('Hide stays its own axis — absence by hide is never confused with a mode', async () => {
    renderRail()
    await settle({ clis: ['grok'], rail: CLI_RAIL, modes: ALL_OFF_MODES }, () =>
      expect(rowIds()).toContain('cli_agent'),
    )

    // No row is hidden by the (ignored) modes payload, so Hidden stays empty
    // and offers no Unhide.
    expect(screen.getByTestId('hidden-bots-row').getAttribute('data-empty')).toBe('true')
    expect(screen.queryByTestId('os-hidden-bots-count')).not.toBeInTheDocument()
  })
})

/**
 * #639 (REQ-909) — width-adaptive team avatars in the rail.
 *
 * Collapsed (avatar-width) rail: exactly ONE face — the team's most recently
 * active member. Wide rail: the large chat-target face plus up to 3 recency
 * minis at graduated sizes. Single-agent seats are untouched.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import AgentSidebar from '../AgentSidebar'
import { RAIL_WIDTH_STORAGE_KEY } from '../../lib/railResize'

const blueprints = [
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    abbreviation: null,
    required_mcp_servers: [],
    tags: [],
    installed: true,
    compiled: true,
    rail: true,
  },
]

const roster = {
  data: [
    {
      id: 'demo',
      name: 'Demo',
      description: 'Demo team',
      members: [
        { id: 'codey', name: 'Codey', kind: 'blueprint', started_at: 1000 },
        { id: 'stewie', name: 'Stewie', kind: 'blueprint', started_at: 9000 },
        { id: 'ada', name: 'Ada', kind: 'blueprint', started_at: 4000 },
        { id: 'geo', name: 'Geo', kind: 'blueprint', started_at: 3000 },
      ],
    },
  ],
}

function stubFetch() {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
      if (url.includes('/v1/preferences')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'user_preferences',
            empty: true,
            favourites: [],
            hidden_agents: [],
          }),
        } as Response
      }
      if (url.includes('/v1/herdr-agents') || url.includes('/v1/cli-agents')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({ object: 'list', data: [], rail: [] }),
        } as Response
      }
      if (url.includes('/v1/team-rosters') || url.includes('/team_rosters.json')) {
        return { ok: true, status: 200, json: async () => roster } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: blueprints }),
      } as Response
    }),
  )
}

function renderRail(railWidth: number) {
  localStorage.setItem(RAIL_WIDTH_STORAGE_KEY, String(railWidth))
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/']}>
        <AgentSidebar open onClose={() => undefined} />
        <Routes>
          <Route path="/" element={<p>Home</p>} />
          <Route path="/chat" element={<p>Chat</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('rail team avatar stack (#639 / REQ-909)', () => {
  beforeEach(() => {
    localStorage.clear()
    stubFetch()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('collapsed rail renders one recency face with the +N sticker (#817)', async () => {
    renderRail(72) // <= AVATAR_ONLY_THRESHOLD (96)
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Demo/ })
    await waitFor(() => {
      expect(row.querySelector('[data-testid="team-chat-face"]')).not.toBeNull()
    })
    const face = row.querySelector('[data-testid="team-chat-face"]')!
    expect(face.getAttribute('data-rail-collapsed')).toBe('true')
    expect(face.getAttribute('data-stack-count')).toBe('1')
    // #817: the +N remainder rides along in every rail state (4 members → +3).
    expect(face.getAttribute('data-remainder')).toBe('3')
    expect(face.querySelector('[data-testid="team-remainder"]')).not.toBeNull()
  })

  it('wide rail renders a single face — the mini row is retired (#817)', async () => {
    renderRail(280)
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const row = await within(list).findByRole('link', { name: /Demo/ })
    await waitFor(() => {
      expect(row.querySelector('[data-testid="team-chat-face"]')).not.toBeNull()
    })
    const face = row.querySelector('[data-testid="team-chat-face"]')!
    expect(face.getAttribute('data-rail-collapsed')).toBe('false')
    // #817 (supersedes #639's multi-face ruling): exactly one face + the +N.
    expect(face.getAttribute('data-stack-count')).toBe('1')
    expect(face.querySelectorAll('.os-team-face__mini').length).toBe(0)
    expect(face.getAttribute('data-remainder')).toBe('3')
  })

  it('single-agent rows are untouched (no team stack semantics)', async () => {
    renderRail(280)
    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const codey = await within(list).findByRole('link', { name: /Codey/ })
    expect(codey.querySelector('[data-testid="team-chat-face"]')).toBeNull()
  })
})

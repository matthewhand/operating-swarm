import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import AgentSidebar from '../AgentSidebar'

describe('REQ-216: Remote/team stack — normal avatar if 1 member; mini stack only for 2+', () => {
  let queryClient: QueryClient

  beforeEach(() => {
    localStorage.clear()
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })
    global.fetch = vi.fn().mockImplementation(async (input: RequestInfo) => {
      const url = String(input)
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
      if (url.includes('team_rosters') || url.includes('team-rosters')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            object: 'list',
            data: [
              {
                id: 'solo-team',
                name: 'Solo Team',
                description: 'Team with 1 member',
                members: [{ id: 'solo-bot', name: 'Solo Bot', role: 'lead' }],
              },
              {
                id: 'duo-team',
                name: 'Duo Team',
                description: 'Team with 2 members',
                members: [
                  { id: 'bot-1', name: 'Bot 1', role: 'lead' },
                  { id: 'bot-2', name: 'Bot 2', role: 'worker' },
                ],
              },
              {
                id: 'quad-team',
                name: 'Quad Team',
                description: 'Team with 4 members',
                members: [
                  { id: 'q1', name: 'Q1', role: 'lead', started_at: '2026-09-03T00:00:01Z' },
                  { id: 'q2', name: 'Q2', role: 'worker', started_at: '2026-09-03T00:00:02Z' },
                  { id: 'q3', name: 'Q3', role: 'worker', started_at: '2026-09-03T00:00:03Z' },
                  { id: 'q4', name: 'Q4', role: 'worker', started_at: '2026-09-03T00:00:04Z', working: true },
                ],
              },
            ],
          }),
        } as Response
      }
      if (url.includes('remotes')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            data: [
              {
                id: 'hermes',
                title: 'Hermes',
                configured: true,
                agents: [{ id: 'hermes-1', name: 'Hermes', started_at: '2026-09-03T00:00:00Z' }],
              },
              {
                id: 'duo-remote',
                title: 'Duo Remote',
                configured: true,
                agents: [
                  { id: 'r1', name: 'R1', started_at: '2026-09-03T00:00:00Z' },
                  { id: 'r2', name: 'R2', started_at: '2026-09-03T00:00:01Z' },
                ],
              },
              {
                id: 'quad-remote',
                title: 'Quad Remote',
                configured: true,
                agents: [
                  { id: 'qr1', name: 'QR1', started_at: '2026-09-03T00:00:01Z' },
                  { id: 'qr2', name: 'QR2', started_at: '2026-09-03T00:00:02Z' },
                  { id: 'qr3', name: 'QR3', started_at: '2026-09-03T00:00:03Z' },
                  { id: 'qr4', name: 'QR4', started_at: '2026-09-03T00:00:04Z' },
                ],
              },
            ],
          }),
        } as Response
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [] }),
      } as Response
    })
  })

  afterEach(() => {
    localStorage.clear()
    vi.restoreAllMocks()
  })

  it('renders single normal-size avatar (no mini stack) when team has only 1 member', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const solo = await within(list).findByRole('link', { name: /Solo Team \(team\)/ })

    // Solo team has 1 member -> single normal-size avatar, no AvatarStack
    expect(solo).toHaveAttribute('data-stack-count', '1')
    expect(within(solo).queryByLabelText('Solo Team members')).not.toBeInTheDocument()
    expect(solo.querySelector('[data-agent-avatar]')).toBeInTheDocument()
    expect(solo.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
    expect(within(solo).queryByText(/^\+\d+$/)).not.toBeInTheDocument()
  })

  it('#438: a 2-member team row is one chat face plus a +1, not a mini stack', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const duo = await within(list).findByRole('link', { name: /Duo Team \(team\)/ })

    // REQ-216 asked for "mini stacked avatars only for 2+"; #438 supersedes that
    // for the sidepane — one face + a remainder on every roster size, so the row
    // beside a single-member team is the same shape.
    expect(duo).toHaveAttribute('data-stack-count', '1')
    expect(duo).toHaveAttribute('data-remainder', '1')
    expect(duo.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
    expect(within(duo).getByTestId('team-chat-face')).toBeInTheDocument()
    expect(within(duo).getByTestId('team-remainder')).toHaveTextContent('+1')
  })

  it('renders single normal-size avatar (no mini stack) when remote has only 1 member', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const hermes = await within(list).findByRole('link', { name: /Hermes \(remote\)/ })

    // Hermes has 1 member -> single normal-size avatar
    expect(hermes).toHaveAttribute('data-stack-count', '1')
    expect(within(hermes).queryByLabelText('Hermes members')).not.toBeInTheDocument()
    expect(hermes.querySelector('[data-agent-avatar]')).toBeInTheDocument()
    expect(hermes.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
  })

  it('#438: a 2-member remote row is one chat face plus a +1', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const duoRemote = await within(list).findByRole('link', { name: /Duo Remote \(remote\)/ })

    // #438 applies to remotes identically — one implementation for both rows.
    expect(duoRemote).toHaveAttribute('data-stack-count', '1')
    expect(duoRemote).toHaveAttribute('data-remainder', '1')
    expect(duoRemote.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
    expect(within(duoRemote).getByTestId('team-remainder')).toHaveTextContent('+1')
  })

  it('#438: a 4-member team row is one face + a remainder of 3, and the face follows run state', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const quadTeam = await within(list).findByRole('link', { name: /Quad Team \(team\)/ })

    // #438 replaces REQ-891's capped fan. The remainder is the roster minus the
    // one shown face — a 4-member team is +3, and `teamSidepaneStack`'s cap of 3
    // must not be allowed to under-report it as +2.
    expect(quadTeam).toHaveAttribute('data-stack-count', '1')
    expect(quadTeam).toHaveAttribute('data-remainder', '3')
    expect(quadTeam.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
    expect(within(quadTeam).getByTestId('team-remainder')).toHaveTextContent('+3')
    // Q4 is working, so newest-active-first ordering puts it at the front — the
    // ordering rule is unchanged, it now selects the single shown face.
    expect(within(quadTeam).getByTestId('team-chat-face').getAttribute('data-remainder')).toBe('3')
  })

  it('#438: a 4-member remote row is one face + a remainder of 3', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const quadRemote = await within(list).findByRole('link', { name: /Quad Remote \(remote\)/ })

    expect(quadRemote).toHaveAttribute('data-stack-count', '1')
    expect(quadRemote).toHaveAttribute('data-remainder', '3')
    expect(quadRemote.querySelectorAll('.os-avatar-stack__face')).toHaveLength(0)
    expect(within(quadRemote).getByTestId('team-remainder')).toHaveTextContent('+3')
  })
})

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

  it('renders mini stacked avatars when team has 2 or more members', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const duo = await within(list).findByRole('link', { name: /Duo Team \(team\)/ })

    // Duo team has 2 members -> mini stacked avatars
    expect(duo).toHaveAttribute('data-stack-count', '2')
    const stack = within(duo).getByLabelText('Duo Team members')
    expect(stack).toHaveAttribute('data-avatar-stack', 'true')
    expect(duo.querySelectorAll('.os-avatar-stack__face')).toHaveLength(2)
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

  it('renders mini stacked avatars when remote has 2 or more members', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const duoRemote = await within(list).findByRole('link', { name: /Duo Remote \(remote\)/ })

    // Duo remote has 2 members -> mini stacked avatars
    expect(duoRemote).toHaveAttribute('data-stack-count', '2')
    const stack = within(duoRemote).getByLabelText('Duo Remote members')
    expect(stack).toHaveAttribute('data-avatar-stack', 'true')
    expect(duoRemote.querySelectorAll('.os-avatar-stack__face')).toHaveLength(2)
  })

  it('REQ-891: renders at most 3 faces with no +N remainder chip for 4-member team, newest-active first when working', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const quadTeam = await within(list).findByRole('link', { name: /Quad Team \(team\)/ })

    // 4 members -> capped at 3 faces with NO remainder chip
    expect(quadTeam).toHaveAttribute('data-stack-count', '3')
    expect(quadTeam).toHaveAttribute('data-remainder', '0')
    expect(within(quadTeam).queryByText(/^\+\d+$/)).not.toBeInTheDocument()
    const faces = quadTeam.querySelectorAll('.os-avatar-stack__face')
    expect(faces).toHaveLength(3)

    // Q4 is working, so newest-active first: Q4 (00:04), Q3 (00:03), Q2 (00:02)
    expect(faces[0]!.getAttribute('data-face-id')).toBe('q4')
    expect(faces[1]!.getAttribute('data-face-id')).toBe('q3')
    expect(faces[2]!.getAttribute('data-face-id')).toBe('q2')
  })

  it('REQ-891: renders at most 3 faces with no +N remainder chip for 4-member remote', async () => {
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const quadRemote = await within(list).findByRole('link', { name: /Quad Remote \(remote\)/ })

    // 4 members -> capped at 3 faces with NO remainder chip, stable roster order when idle
    expect(quadRemote).toHaveAttribute('data-stack-count', '3')
    expect(quadRemote).toHaveAttribute('data-remainder', '0')
    expect(within(quadRemote).queryByText(/^\+\d+$/)).not.toBeInTheDocument()
    const faces = quadRemote.querySelectorAll('.os-avatar-stack__face')
    expect(faces).toHaveLength(3)
    expect(faces[0]!.getAttribute('data-face-id')).toBe('qr1')
    expect(faces[1]!.getAttribute('data-face-id')).toBe('qr2')
    expect(faces[2]!.getAttribute('data-face-id')).toBe('qr3')
  })
})

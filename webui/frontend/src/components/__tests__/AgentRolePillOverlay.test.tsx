import { describe, it, expect, beforeEach, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import AgentSidebar from '../AgentSidebar'
import { PINNED_AGENTS_STORAGE_KEY } from '../../lib/pinnedAgents'
import { HIDDEN_AGENTS_STORAGE_KEY } from '../../lib/hiddenAgents'

const blueprints = [
  {
    id: 'cos_agent',
    object: 'blueprint' as const,
    name: 'Pat Chief',
    description: 'Oversees operations and strategic goals',
    role: 'chief_of_staff',
    installed: true,
    compiled: true,
    rail: true,
  },
  {
    id: 'codey',
    object: 'blueprint' as const,
    name: 'Codey',
    description: 'Code assistant',
    role: 'default',
    installed: true,
    compiled: true,
    rail: true,
  },
]

const rosters = [
  {
    id: 'dev_squad',
    object: 'team_roster' as const,
    name: 'Dev Squad',
    description: 'Full stack development unit',
    members: [{ id: 'codey', kind: 'api', role: 'default', source: 'blueprint:codey' }],
    wires: { handoff: true, as_tool: true },
  },
]

function mockFetch() {
  return vi.fn().mockImplementation(async (input: RequestInfo) => {
    const url = String(input)
    if (url.includes('team_rosters') || url.includes('team-rosters')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: rosters }),
      } as Response
    }
    if (url.includes('/v1/cli-agents') || url.includes('/v1/herdr-agents')) {
      return {
        ok: true,
        status: 200,
        json: async () => ({ object: 'list', data: [], clis: [], rail: [] }),
      } as Response
    }
    return {
      ok: true,
      status: 200,
      json: async () => ({ object: 'list', data: blueprints }),
    } as Response
  })
}

describe('AgentSidebar Role Badges Overlay Avatar (REQ-175)', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem(PINNED_AGENTS_STORAGE_KEY, '[]')
    localStorage.setItem(HIDDEN_AGENTS_STORAGE_KEY, '[]')
    vi.stubGlobal('fetch', mockFetch())
  })

  it('renders role badge right-aligned on the agent name row instead of the timestamp', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const cosRow = await within(list).findByRole('link', { name: /Pat Chief/i })

    // Find the role badge
    const badge = cosRow.querySelector('.os-agent-role-badge')
    expect(badge).not.toBeNull()
    expect(badge).not.toHaveAttribute('data-avatar-overlay')
    expect(badge).toHaveAttribute('data-role', 'chief_of_staff')
    expect(badge).toHaveTextContent('CoS')

    // Badge sits on the name row (right-aligned, timestamp slot), not on the avatar
    const avatarSlot = cosRow.querySelector('.os-agent-row__avatar-slot')
    expect(avatarSlot?.querySelector('.os-agent-role-badge')).toBeNull()

    // Badge takes the timestamp position on the name row
    const textColumn = cosRow.querySelector('.min-w-0.flex-1')
    expect(textColumn).not.toBeNull()
    expect(textColumn?.querySelector('.os-agent-role-badge')).not.toBeNull()
    expect(cosRow.querySelector('[data-testid="rail-row-timestamp"]')).toBeNull()
    expect(within(textColumn as HTMLElement).getByText('Oversees operations and strategic goals')).toBeInTheDocument()

    // Plain agent without special role has no badge
    const codeyRow = within(list).getByRole('link', { name: /Codey/i })
    expect(codeyRow.querySelector('.os-agent-role-badge')).toBeNull()
  })

  it('#525: a team row carries no role badge — neither on the avatar nor the name row', async () => {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    const list = await screen.findByRole('navigation', { name: 'Agent list' })
    const teamRow = await within(list).findByRole('link', { name: /Dev Squad/i })

    // Team membership is not a role, so nothing role-styled may render for it.
    expect(teamRow.querySelector('.os-agent-role-badge')).toBeNull()
    expect(within(teamRow).queryByText('Team')).not.toBeInTheDocument()

    // The row still declares its kind for CSS/tests and screen readers.
    expect(teamRow).toHaveAttribute('data-kind', 'team')
    expect(teamRow).toHaveAttribute('aria-label', 'Dev Squad (team)')

    // Second row still contains the team snippet.
    const textColumn = teamRow.querySelector('.min-w-0.flex-1')
    expect(textColumn?.querySelector('.block.truncate')).not.toBeNull()
  })

  it('#579: a pinned role badge renders in the tile corner, not as an avatar overlay', async () => {
    localStorage.setItem(
      PINNED_AGENTS_STORAGE_KEY,
      JSON.stringify([{ id: 'support', name: 'Support' }]),
    )
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    })

    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/chat']}>
          <AgentSidebar open />
        </MemoryRouter>
      </QueryClientProvider>,
    )

    // Pinned section tile badge is present with .os-fav-tile__badge
    const grid = screen.getByTestId('agent-fav-grid')
    const pinnedSupport = await within(grid).findByRole('link', { name: /Support/i })
    const pinnedBadge = pinnedSupport.querySelector('.os-fav-tile__badge')
    expect(pinnedBadge).not.toBeNull()
    expect(pinnedBadge).toHaveClass('os-agent-role-badge')
    expect(pinnedBadge).toHaveAttribute('data-role', 'support')
    // #579: corner placement is a CSS contract (top/right, no centre translate).
    expect(pinnedBadge).not.toHaveAttribute('data-avatar-overlay')
  })
})

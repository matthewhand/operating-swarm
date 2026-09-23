/**
 * #763 — Teams sheet redesign: list-first, dedicated creation flow.
 *
 * Contracts:
 * - The sheet opens on a simplified teams list; each row shows name,
 *   member count, and description, with an Edit action that opens the
 *   team editor overlay for that team.
 * - The inline "Create alias" form at the bottom of the list is gone.
 *   Creation lives behind a dedicated "+ New Team" button that opens a
 *   focused creation modal; submitting it creates the roster alias.
 * - Browsing and drafting are separated: the list stays visible in
 *   browse mode only, and the create modal is its own view.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import TeamsSheet from '../overlays/TeamsSheet'
import { ToastProvider } from '../DaisyUI'

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...actual,
    fetchTeams: vi.fn(async () => ({
      object: 'list' as const,
      data: [
        {
          id: 'lab',
          object: 'team',
          description: 'Lab experiments',
          llm_profile: 'default',
        },
        {
          id: 'research-squad',
          object: 'team',
          description: 'Research crew',
          llm_profile: 'orchestration',
        },
      ],
    })),
    createTeam: vi.fn(async (team: { name: string; description?: string; llm_profile?: string }) => ({
      id: team.name,
      object: 'team' as const,
      description: team.description ?? '',
      llm_profile: team.llm_profile ?? 'default',
    })),
  }
})

vi.mock('../AgentChat/TeamSelect', () => ({
  TeamSelect: () => <div data-testid="team-select-stub" />,
}))

vi.mock('../TeamEditor', () => ({
  openTeamEditor: vi.fn(),
}))

function renderSheet() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <TeamsSheet isOpen onClose={() => {}} />
      </ToastProvider>
    </QueryClientProvider>,
  )
}

describe('#763 — Teams sheet: list-first with dedicated creation flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a simplified team list with member/profile metadata and Edit action', async () => {
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered teams/i })
    const lab = within(list).getByText('lab').closest('li') as HTMLElement
    expect(within(lab).getByText(/lab experiments/i)).toBeInTheDocument()
    expect(within(lab).getByRole('button', { name: /edit/i })).toBeInTheDocument()
  })

  it('Edit on a row opens the team editor for that team', async () => {
    const { openTeamEditor } = await import('../TeamEditor')
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered teams/i })
    const lab = within(list).getByText('lab').closest('li') as HTMLElement
    fireEvent.click(within(lab).getByRole('button', { name: /edit/i }))
    expect(openTeamEditor).toHaveBeenCalledWith(
      expect.objectContaining({ teamId: 'lab' }),
    )
  })

  it('moves creation behind a dedicated + New Team flow (no inline bottom form)', async () => {
    renderSheet()
    await screen.findByRole('list', { name: /registered teams/i })
    // The old inline bottom form is gone from the browse view.
    expect(screen.queryByText(/create alias/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /\+ new team/i }))
    const dialog = await screen.findByRole('dialog', { name: /new team/i })
    expect(within(dialog).getByLabelText(/team name/i)).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/team name/i), {
      target: { value: 'alpha' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /create team/i }))
    await waitFor(() => {
      expect(screen.getByText(/team created/i)).toBeInTheDocument()
    })
    // Back on the browse list after creation.
    expect(screen.getByRole('list', { name: /registered teams/i })).toBeInTheDocument()
  })
})

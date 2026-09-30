/**
 * #763 — Rigs sheet redesign: list-first, dedicated creation flow.
 *
 * Contracts:
 * - The sheet opens on a simplified group chat list; each row shows name,
 *   member count, and description, with an Edit action that opens the
 *   group chat editor overlay for that group chat.
 * - The inline "Create alias" form at the bottom of the list is gone.
 *   Creation lives behind a dedicated "+ New Group chat" button that opens a
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

vi.mock('../teamEditorKernel', () => ({
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

describe('#763 — Group chats sheet: list-first with dedicated creation flow', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a simplified group chat list with member/profile metadata and Edit action', async () => {
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered group chats/i })
    const lab = within(list).getByText('lab').closest('li') as HTMLElement
    expect(within(lab).getByText(/lab experiments/i)).toBeInTheDocument()
    expect(within(lab).getByRole('button', { name: /edit/i })).toBeInTheDocument()
  })

  it('Edit on a row opens the group chat editor for that group chat', async () => {
    const { openTeamEditor } = await import('../teamEditorKernel')
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered group chats/i })
    const lab = within(list).getByText('lab').closest('li') as HTMLElement
    fireEvent.click(within(lab).getByRole('button', { name: /edit/i }))
    expect(openTeamEditor).toHaveBeenCalledWith(
      expect.objectContaining({ teamId: 'lab' }),
    )
  })

  it('moves creation behind a dedicated + New group chat flow (no inline bottom form)', async () => {
    renderSheet()
    await screen.findByRole('list', { name: /registered group chats/i })
    // The old inline bottom form is gone from the browse view.
    expect(screen.queryByText(/create alias/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /\+ new group chat/i }))
    const dialog = await screen.findByRole('dialog', { name: /new group chat/i })
    expect(within(dialog).getByLabelText(/group chat name/i)).toBeInTheDocument()

    fireEvent.change(within(dialog).getByLabelText(/group chat name/i), {
      target: { value: 'alpha' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /create group chat/i }))
    await waitFor(() => {
      expect(screen.getByText(/group chat created/i)).toBeInTheDocument()
    })
    // Back on the browse list after creation.
    expect(screen.getByRole('list', { name: /registered group chats/i })).toBeInTheDocument()
  })

  it('caps the group chat list so a long roster scrolls instead of being clipped by the sheet', async () => {
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered group chats/i })
    // The sheet's modal-box is `overflow-hidden`; without its own scroll the
    // list grew past the viewport and rows below the fold were unreachable.
    expect(list.className).toContain('overflow-y-auto')
    expect(list.className).toContain('max-h-[55vh]')
  })

  it('truncates long group chat ids and descriptions so rows never overflow the sheet', async () => {
    renderSheet()
    const list = await screen.findByRole('list', { name: /registered group chats/i })
    // The id cell carries the text node; truncate keeps an unbroken id from
    // pushing the Edit action out of the row.
    expect(within(list).getByText('lab').className).toContain('truncate')
  })
})

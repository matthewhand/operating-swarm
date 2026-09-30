import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LibraryScopeBar } from '../LibraryScopeBar'
import { fetchScopedLibrary, fetchTeamRosters, publishLibraryItem } from '../../lib/api'

vi.mock('../../lib/api', () => ({
  createPresetBot: vi.fn(),
  fetchRosterPacks: vi.fn(),
  fetchScopedLibrary: vi.fn(),
  fetchTeamRosters: vi.fn(),
  importLibraryItem: vi.fn(),
  importRosterPack: vi.fn(),
  publishLibraryItem: vi.fn(),
  publishRosterPack: vi.fn(),
}))

function renderBar() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LibraryScopeBar surface="library" itemKey="chatbot" itemTitle="Chatbot" />
    </QueryClientProvider>,
  )
}

describe('LibraryScopeBar team scope (#1311)', () => {
  beforeEach(() => {
    vi.mocked(fetchScopedLibrary).mockReset()
    vi.mocked(publishLibraryItem).mockReset()
    vi.mocked(fetchTeamRosters).mockReset()
    vi.mocked(fetchTeamRosters).mockResolvedValue({
      object: 'list',
      data: [
        {
          id: 'eng',
          object: 'team_roster',
          name: 'Engineering',
          members: [],
          wires: { handoff: false, as_tool: false },
        },
        {
          id: 'sales',
          object: 'team_roster',
          name: 'Sales',
          members: [],
          wires: { handoff: false, as_tool: false },
        },
      ],
    })
  })

  it('does not list or publish Team until a roster is chosen', async () => {
    renderBar()
    fireEvent.click(screen.getByRole('button', { name: 'Team' }))
    expect(screen.getByRole('combobox', { name: 'Team' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Publish' })).toBeDisabled()
    expect(screen.queryByText(/Team scope needs a team id on this pane/i)).toBeNull()
    await screen.findByRole('option', { name: 'Engineering' })
    expect(fetchTeamRosters).toHaveBeenCalled()
    expect(fetchScopedLibrary).not.toHaveBeenCalled()
    expect(publishLibraryItem).not.toHaveBeenCalled()
  })
})

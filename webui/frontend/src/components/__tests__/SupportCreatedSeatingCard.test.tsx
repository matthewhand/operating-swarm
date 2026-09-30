import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import SupportCreatedSeatingCard from '../SupportCreatedSeatingCard'
import { SEAT_ON_TEAM_LABEL, type SupportNlSeatingCard } from '../../lib/supportNlSeating'
import { createTeamRoster, fetchTeamRosters, updateTeamRoster } from '../../lib/api'

vi.mock('../../lib/api', () => ({
  createTeamRoster: vi.fn(),
  fetchTeamRosters: vi.fn(),
  updateTeamRoster: vi.fn(),
}))

const CARD: SupportNlSeatingCard = {
  id: 'office',
  kind: 'seating',
  title: 'office',
  mode: 'seat',
  members: [{ id: 'ada', name: 'Ada', kind: 'api', role: 'default' }],
  memberLabel: 'Ada',
  persisted: false,
  usable: false,
  chatHref: '/chat?team=office',
}

function renderCard(card: SupportNlSeatingCard = CARD) {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <Routes>
        <Route path="/chat" element={<SupportCreatedSeatingCard card={card} />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SupportCreatedSeatingCard (#1373)', () => {
  beforeEach(() => {
    vi.mocked(createTeamRoster).mockReset()
    vi.mocked(fetchTeamRosters).mockReset()
    vi.mocked(updateTeamRoster).mockReset()
    vi.mocked(createTeamRoster).mockResolvedValue({
      id: 'office',
      object: 'team_roster',
      name: 'office',
      members: [{ id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' }],
      wires: { handoff: true, as_tool: true },
    })
    vi.mocked(updateTeamRoster).mockResolvedValue({
      id: 'office',
      object: 'team_roster',
      name: 'Office',
      members: [
        { id: 'pat', kind: 'api', role: 'default', source: 'blueprint:pat' },
        { id: 'ada', kind: 'api', role: 'default', source: 'blueprint:ada' },
      ],
      wires: { handoff: true, as_tool: true },
    })
  })

  it('creates a roster when the team is new', async () => {
    vi.mocked(fetchTeamRosters).mockResolvedValue({ object: 'list', data: [] })
    renderCard()
    expect(screen.getByTestId('support-nl-seating-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-seating-draft')).toHaveTextContent('Draft')
    expect(screen.getByTestId('support-nl-seat-team')).toHaveTextContent(SEAT_ON_TEAM_LABEL)
    fireEvent.click(screen.getByTestId('support-nl-seat-team'))
    await waitFor(() => {
      expect(createTeamRoster).toHaveBeenCalledWith({
        name: 'office',
        members: [
          {
            id: 'ada',
            name: 'Ada',
            kind: 'api',
            role: 'default',
            source: 'blueprint:ada',
          },
        ],
      })
    })
    await waitFor(() => {
      expect(screen.getByTestId('support-nl-seating-usable')).toHaveTextContent('Seated')
    })
    expect(updateTeamRoster).not.toHaveBeenCalled()
  })

  it('merges into an existing roster', async () => {
    vi.mocked(fetchTeamRosters).mockResolvedValue({
      object: 'list',
      data: [
        {
          id: 'office',
          object: 'team_roster',
          name: 'Office',
          members: [{ id: 'pat', kind: 'api', role: 'default', source: 'blueprint:pat' }],
          wires: { handoff: true, as_tool: true },
        },
      ],
    })
    renderCard()
    fireEvent.click(screen.getByTestId('support-nl-seat-team'))
    await waitFor(() => {
      expect(updateTeamRoster).toHaveBeenCalled()
    })
    const [, payload] = vi.mocked(updateTeamRoster).mock.calls[0]
    expect(payload.members?.map((row) => row.id)).toEqual(['pat', 'ada'])
    expect(createTeamRoster).not.toHaveBeenCalled()
  })
})

import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import SupportCreatedRoutineCard from '../SupportCreatedRoutineCard'
import { ADD_ROUTINE_LABEL, type SupportNlRoutineCard } from '../../lib/supportNlRoutine'
import { createRoutine } from '../../lib/routines'

vi.mock('../../lib/routines', () => ({
  createRoutine: vi.fn(),
}))

const CARD: SupportNlRoutineCard = {
  id: '',
  kind: 'routine',
  title: 'Daily standup',
  agentId: 'codey',
  instruction: 'posts notes',
  trigger: { kind: 'cron', expression: '0 9 * * *' },
  triggerLabel: 'Daily at 09:00',
  persisted: false,
  usable: false,
  chatHref: '/chat?blueprint=codey',
}

function LocationProbe() {
  const loc = useLocation()
  return <span data-testid="loc">{`${loc.pathname}${loc.search}`}</span>
}

function renderCard(card: SupportNlRoutineCard = CARD) {
  return render(
    <MemoryRouter initialEntries={['/chat']}>
      <Routes>
        <Route
          path="/chat"
          element={
            <>
              <SupportCreatedRoutineCard card={card} />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SupportCreatedRoutineCard (#1373)', () => {
  beforeEach(() => {
    vi.mocked(createRoutine).mockReset()
    vi.mocked(createRoutine).mockResolvedValue({
      id: 'rtn-1',
      name: CARD.title,
      instruction: CARD.instruction,
      active: true,
      trigger: { kind: 'cron', expression: '0 9 * * *' },
      history: [],
    })
  })

  it('drafts then persists via createRoutine', async () => {
    renderCard()
    expect(screen.getByTestId('support-nl-routine-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-routine-draft')).toHaveTextContent('Draft')
    expect(screen.getByTestId('support-nl-add-routine')).toHaveTextContent(ADD_ROUTINE_LABEL)
    fireEvent.click(screen.getByTestId('support-nl-add-routine'))
    await waitFor(() => {
      expect(createRoutine).toHaveBeenCalledWith('codey', {
        name: 'Daily standup',
        instruction: 'posts notes',
        active: true,
        trigger: { kind: 'cron', expression: '0 9 * * *' },
      })
    })
    await waitFor(() => {
      expect(screen.getByTestId('support-nl-routine-usable')).toHaveTextContent('Usable')
    })
  })
})

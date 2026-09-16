import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import SupportCreatedBlueprintCard from '../SupportCreatedBlueprintCard'
import { VIEW_EDIT_CODE_LABEL, type SupportNlBlueprintCard } from '../../lib/supportNlBlueprint'
import { FOCUS_AGENT_EVENT } from '../../lib/agentNotifications'

const CARD: SupportNlBlueprintCard = {
  id: 'ba_eng_tester',
  title: 'BA → Engineer → Tester',
  usable: true,
  chatHref: '/chat?blueprint=ba_eng_tester',
  graphLabel: 'BA → Engineer → Tester',
  edges: [
    ['ba', 'engineer'],
    ['engineer', 'tester'],
  ],
  userWrotePython: false,
  code: 'class BaEngTesterBlueprint:\n    pass\n',
}

function LocationProbe() {
  const loc = useLocation()
  return <span data-testid="loc">{`${loc.pathname}${loc.search}`}</span>
}

function renderCard(card: SupportNlBlueprintCard = CARD, initial = '/chat') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <Routes>
        <Route
          path="/chat"
          element={
            <>
              <SupportCreatedBlueprintCard card={card} />
              <LocationProbe />
            </>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

describe('SupportCreatedBlueprintCard (REQ-158)', () => {
  it('shows a usable team and hides Python until View / edit code', () => {
    renderCard()
    expect(screen.getByTestId('support-nl-blueprint-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-usable')).toHaveTextContent('Usable')
    expect(screen.getByTestId('support-nl-open-chat')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-code-hidden')).toBeInTheDocument()
    expect(screen.queryByTestId('support-nl-code')).not.toBeInTheDocument()
    expect(screen.queryByText(/class BaEngTesterBlueprint/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: VIEW_EDIT_CODE_LABEL }))
    expect(screen.getByTestId('support-nl-code')).toHaveValue(CARD.code)
    expect(screen.queryByTestId('support-nl-code-hidden')).not.toBeInTheDocument()
  })

  it('#434 Open in chat navigates off Support onto the new seat', () => {
    const focused: string[] = []
    const onFocus = (event: Event) => {
      const id = (event as CustomEvent<{ agentId?: string }>).detail?.agentId
      if (id) focused.push(id)
    }
    window.addEventListener(FOCUS_AGENT_EVENT, onFocus)
    renderCard(CARD, '/chat')
    expect(screen.getByTestId('loc')).toHaveTextContent('/chat')
    fireEvent.click(screen.getByTestId('support-nl-open-chat'))
    expect(screen.getByTestId('loc')).toHaveTextContent('/chat?blueprint=ba_eng_tester')
    expect(focused).toEqual(['ba_eng_tester'])
    window.removeEventListener(FOCUS_AGENT_EVENT, onFocus)
  })
})

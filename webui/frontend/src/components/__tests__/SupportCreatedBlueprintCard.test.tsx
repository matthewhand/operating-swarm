import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import SupportCreatedBlueprintCard from '../SupportCreatedBlueprintCard'
import {
  ADD_AS_AGENT_LABEL,
  SAVE_AS_BLUEPRINT_LABEL,
  VIEW_EDIT_CODE_LABEL,
  type SupportNlBlueprintCard,
} from '../../lib/supportNlBlueprint'
import { FOCUS_AGENT_EVENT } from '../../lib/agentNotifications'
import { createCustomBlueprint } from '../../lib/api'

vi.mock('../../lib/api', () => ({
  createCustomBlueprint: vi.fn(),
}))

const CARD: SupportNlBlueprintCard = {
  id: 'ba_eng_tester',
  title: 'BA → Engineer → Tester',
  usable: false,
  persisted: false,
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

describe('SupportCreatedBlueprintCard (REQ-158 / #440)', () => {
  beforeEach(() => {
    vi.mocked(createCustomBlueprint).mockReset()
    vi.mocked(createCustomBlueprint).mockResolvedValue({
      id: 'ba_eng_tester',
      name: CARD.title,
      description: '',
      category: 'api',
      tags: [],
      requirements: '',
      code: CARD.code,
      required_mcp_servers: [],
      env_vars: [],
      kind: 'api',
      rail: true,
    })
  })

  it('shows a draft team and hides Python until View / edit code', () => {
    renderCard()
    expect(screen.getByTestId('support-nl-blueprint-card')).toBeInTheDocument()
    expect(screen.getByTestId('support-nl-draft')).toHaveTextContent('Draft')
    expect(screen.getByTestId('support-nl-add-agent')).toHaveTextContent(ADD_AS_AGENT_LABEL)
    expect(screen.getByTestId('support-nl-save-blueprint')).toHaveTextContent(
      SAVE_AS_BLUEPRINT_LABEL,
    )
    expect(screen.queryByTestId('support-nl-open-chat')).not.toBeInTheDocument()
    expect(screen.getByTestId('support-nl-code-hidden')).toBeInTheDocument()
    expect(screen.queryByTestId('support-nl-code')).not.toBeInTheDocument()
    expect(screen.queryByText(/class BaEngTesterBlueprint/)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: VIEW_EDIT_CODE_LABEL }))
    expect(screen.getByTestId('support-nl-code')).toHaveValue(CARD.code)
    expect(screen.queryByTestId('support-nl-code-hidden')).not.toBeInTheDocument()
  })

  it('#440 Add as agent persists then navigates onto the new seat', async () => {
    const focused: string[] = []
    const onFocus = (event: Event) => {
      const id = (event as CustomEvent<{ agentId?: string }>).detail?.agentId
      if (id) focused.push(id)
    }
    window.addEventListener(FOCUS_AGENT_EVENT, onFocus)
    renderCard(CARD, '/chat')
    expect(screen.getByTestId('loc')).toHaveTextContent('/chat')
    fireEvent.click(screen.getByTestId('support-nl-add-agent'))
    await waitFor(() => {
      expect(createCustomBlueprint).toHaveBeenCalledWith(
        expect.objectContaining({
          id: 'ba_eng_tester',
          kind: 'api',
          rail: true,
          code: CARD.code,
        }),
      )
    })
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/chat?blueprint=ba_eng_tester')
    })
    expect(focused).toEqual(['ba_eng_tester'])
    window.removeEventListener(FOCUS_AGENT_EVENT, onFocus)
  })

  it('#440 Save as blueprint persists and stays on Support', async () => {
    renderCard(CARD, '/chat')
    fireEvent.click(screen.getByTestId('support-nl-save-blueprint'))
    await waitFor(() => {
      expect(createCustomBlueprint).toHaveBeenCalled()
    })
    await waitFor(() => {
      expect(screen.getByTestId('support-nl-usable')).toHaveTextContent('Usable')
    })
    expect(screen.getByTestId('loc')).toHaveTextContent('/chat')
    expect(screen.queryByTestId('support-nl-save-blueprint')).not.toBeInTheDocument()
  })
})

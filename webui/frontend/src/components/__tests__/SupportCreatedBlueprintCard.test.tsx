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

  it('shows a draft team and hides Python until View code', () => {
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

// #769 — the View/Edit reveal is a deliberate "show me the code" action: the
// card breaks out of the bubble's inline width (near-full pane) and the code
// surface shows the whole file — no cramped box, no inner height cap.
describe('SupportCreatedBlueprintCard code reveal (#769)', () => {
  beforeEach(() => {
    vi.mocked(createCustomBlueprint).mockReset()
    window.localStorage.clear()
  })

  it('revealed card breaks out to full width and the code surface is uncapped', async () => {
    renderCard()
    fireEvent.click(screen.getByRole('button', { name: VIEW_EDIT_CODE_LABEL }))
    const card = screen.getByTestId('support-nl-blueprint-card')
    expect(card.dataset.revealed).toBe('true')
    expect(card.className).toContain('support-nl-card--revealed')

    const code = screen.getByTestId('support-nl-code')
    expect(code.className).toContain('w-full')
    // "See the whole thing": generous floor, vertical resize allowed, and no
    // collapsed max-height cap class.
    expect(code.className).toContain('min-h-96')
    expect(code.className).toContain('resize-y')
    expect(code.className).not.toContain('max-h-')
  })

  it('hidden state stays compact (no breakout class, no textarea)', () => {
    renderCard()
    const card = screen.getByTestId('support-nl-blueprint-card')
    expect(card.className).not.toContain('support-nl-card--revealed')
    expect(screen.queryByTestId('support-nl-code')).toBeNull()
  })
})

describe('#807 — the revealed code view stacks above the bubble layer', () => {
  it('elevates instead of distorting: revealed card is position-elevated, full-width, and out of the bubble flow', async () => {
    const { readFileSync } = await import('node:fs')
    const { join } = await import('node:path')
    const src = readFileSync(
      join(process.cwd(), 'src/components/SupportCreatedBlueprintCard.tsx'),
      'utf8',
    )
    // #769's negative-margin breakout distorted the containing bubble; #807
    // replaces it with a stacked layer: elevated z-index over the transcript,
    // full chat-pane width, and a stable bubble underneath.
    expect(src).toMatch(/support-nl-card--revealed/)
    expect(src).toMatch(/relative z-20/)
    expect(src).not.toMatch(/-mx-3 sm:-mx-8/)
    expect(src).not.toMatch(/w-\[calc\(100%\+1\.5rem\)\]/)
  })
})

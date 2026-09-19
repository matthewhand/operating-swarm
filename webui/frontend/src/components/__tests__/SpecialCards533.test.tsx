/**
 * #533 — improved in-chat rendering of special messages.
 *
 * a. Approvals: the Safety approval card renders functional decisions
 *    (Allow once / Always allow / Deny) and reflects the post-decision state.
 * b. Status notices (context-cull, session-restore, generic) render as a
 *    collapsible card instead of raw text, inside the bubble — and therefore
 *    across all four bubble themes (speech, simple, irc, feed).
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../DaisyUI/Toast'
import { ToolCallPopup } from '../ToolCallPopup'
import { SpecialStatusCard } from '../SpecialCards'
import { ChatMessageBubble } from '../ChatMessageBubble'
import type { ToolCallState } from '../../lib/safety'
import type { BubbleTheme } from '../../lib/bubbleTheme'

function renderPage(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ToastProvider>
        <MemoryRouter initialEntries={['/chat']}>{ui}</MemoryRouter>
      </ToastProvider>
    </QueryClientProvider>,
  )
}

const BUBBLE_PROPS = {
  streaming: false,
  editing: false,
  onCancelEdit: () => {},
  onSaveEdit: () => {},
} as const

describe('#533a — approval card', () => {
  const pending: ToolCallState = {
    id: 'call-1',
    name: 'delete_file',
    status: 'running',
    concerned: true,
    needsApproval: true,
  }

  it('renders the Safety approval card with functional decisions', () => {
    const onDecision = vi.fn()
    renderPage(<ToolCallPopup tool={pending} onDecision={onDecision} />)

    const card = screen.getByRole('dialog', { name: 'Safety approval' })
    expect(within(card).getByText(/delete_file/)).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Allow once' }))
    expect(onDecision).toHaveBeenCalledWith('allow')

    fireEvent.click(within(card).getByRole('button', { name: 'Deny' }))
    expect(onDecision).toHaveBeenCalledWith('deny')
  })

  it('reflects the post-decision state (denied) with no decision buttons', () => {
    const denied: ToolCallState = { ...pending, needsApproval: false, status: 'denied' }
    renderPage(<ToolCallPopup tool={denied} onDecision={vi.fn()} />)

    expect(screen.queryByRole('dialog', { name: 'Safety approval' })).not.toBeInTheDocument()
    expect(screen.getByTestId('tool-status-badge')).toHaveAttribute('data-status', 'denied')
  })
})

describe('#533b-transcript — status-role messages collapse automatically', () => {
  it('a status message renders as the collapsible card, not raw text', () => {
    renderPage(
      <ChatMessageBubble
        role="status"
        agentName="Support"
        text="Context culled: 12 oldest messages dropped"
        {...BUBBLE_PROPS}
      />,
    )

    const bubble = screen.getByTestId('chat-bubble')
    const card = within(bubble).getByTestId('special-status-card')
    expect(within(card).getByText('Context culled: 12 oldest messages dropped')).toBeInTheDocument()
    // The raw text is the card's summary — not also dumped as bubble prose.
    expect(within(bubble).queryByTestId('chat-md')).not.toBeInTheDocument()
  })

  it('assistant messages still render normal markdown prose', () => {
    renderPage(
      <ChatMessageBubble
        role="assistant"
        agentName="Support"
        text="Hello there"
        {...BUBBLE_PROPS}
      />,
    )
    expect(screen.getByTestId('chat-md')).toBeInTheDocument()
    expect(screen.queryByTestId('special-status-card')).not.toBeInTheDocument()
  })
})

const THEMES: BubbleTheme[] = ['speech', 'simple', 'irc', 'feed']

describe('#533b — status notices render as collapsible cards in every theme', () => {
  for (const theme of THEMES) {
    it(`theme ${theme}: the notice is a collapsible card inside the bubble`, () => {
      renderPage(
        <ChatMessageBubble
          theme={theme}
          role="assistant"
          agentName="Support"
          text="Working…"
          {...BUBBLE_PROPS}
        >
          <SpecialStatusCard
            summary="Context culled: 12 oldest messages"
            badge="context"
            detail="Full cull report"
          />
        </ChatMessageBubble>,
      )

      // The card lives inside the theme-rendered bubble (children slot), so
      // every theme carries it with no per-theme branches.
      const bubble = screen.getByTestId('chat-bubble')
      const card = within(bubble).getByTestId('special-status-card')
      // eslint-disable-next-line testing-library/no-node-access
      const wrapper = bubble.closest('[data-message-theme]')
      expect(wrapper).not.toBeNull()
      expect(wrapper).toHaveAttribute('data-message-theme', theme)

      // Collapsed: summary visible, detail behind the disclosure.
      expect(within(card).getByText(/Context culled/)).toBeInTheDocument()
      // eslint-disable-next-line testing-library/no-node-access
      const content = card.querySelector('.collapse-content')
      expect(content).toBeTruthy()

      // Open: the detail becomes visible.
      ;(card as HTMLDetailsElement).open = true
      expect(card).toHaveTextContent('Full cull report')
    })
  }
})

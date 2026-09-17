import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { ContextUsageBadge } from '../ContextUsageBadge'
import type { ContextUsage } from '../../lib/contextUsage'

const usage = (overrides: Partial<ContextUsage> = {}): ContextUsage => ({
  type: 'context_usage',
  conversation_id: 'c1',
  agent_id: 'jeeves',
  tokens: 12300,
  window: null,
  pct: null,
  estimate: true,
  breakdown: { messages: 8000, summaries: 2000, system: 1500, tools: 800 },
  ...overrides,
})

describe('ContextUsageBadge (#215)', () => {
  it('renders the unknown-window estimate near the composer', () => {
    render(<ContextUsageBadge usage={usage()} />)
    const badge = screen.getByTestId('context-usage-badge')
    expect(badge).toHaveTextContent('~12.3k tokens, window unknown')
    expect(badge).toHaveAttribute('aria-label', 'Context window usage')
  })

  it('renders used/max when the seat window is known', () => {
    render(<ContextUsageBadge usage={usage({ tokens: 16000, window: 128000, pct: 13 })} />)
    expect(screen.getByTestId('context-usage-badge')).toHaveTextContent('~16k / 128k')
  })

  it('opens seat settings when clicked', () => {
    const onOpenDetail = vi.fn()
    render(<ContextUsageBadge usage={usage()} onOpenDetail={onOpenDetail} />)
    fireEvent.click(screen.getByRole('button', { name: 'Context window usage' }))
    expect(onOpenDetail).toHaveBeenCalledTimes(1)
  })

  it('renders nothing until a snapshot exists', () => {
    const { container } = render(<ContextUsageBadge usage={null} />)
    expect(container).toBeEmptyDOMElement()
  })
})

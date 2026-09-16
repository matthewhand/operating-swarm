import { render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ContextUsageDetail } from '../ContextUsageDetail'
import { recordUsageSpark, type ContextUsage } from '../../lib/contextUsage'

const usage: ContextUsage = {
  type: 'context_usage',
  conversation_id: 'c1',
  agent_id: 'jeeves',
  tokens: 12300,
  window: null,
  pct: null,
  estimate: true,
  breakdown: { messages: 8000, summaries: 2000, system: 1500, tools: 800 },
}

describe('ContextUsageDetail (#215)', () => {
  afterEach(() => {
    window.sessionStorage.clear()
    vi.unstubAllGlobals()
  })

  it('shows the honest unknown-window label and breakdown', () => {
    render(
      <ContextUsageDetail
        agentId="jeeves"
        conversationId="c1"
        usage={usage}
      />,
    )
    expect(screen.getByTestId('context-usage-detail')).toBeInTheDocument()
    expect(screen.getByTestId('context-usage-label')).toHaveTextContent(
      '~12.3k tokens, window unknown',
    )
    expect(screen.getByTestId('context-usage-messages')).toHaveTextContent('~8k')
    expect(screen.getByTestId('context-usage-summaries')).toHaveTextContent('~2k')
    expect(screen.getByTestId('context-usage-system')).toHaveTextContent('~1.5k')
    expect(screen.getByTestId('context-usage-tools')).toHaveTextContent('~800')
    expect(screen.getByText(/Estimate \(chars\/4\)/)).toBeInTheDocument()
  })

  it('draws a sparkline once the seat has more than one sample', () => {
    recordUsageSpark('c1', 1000)
    recordUsageSpark('c1', 12300)
    render(
      <ContextUsageDetail
        agentId="jeeves"
        conversationId="c1"
        usage={usage}
      />,
    )
    expect(screen.getByTestId('context-usage-sparkline')).toBeInTheDocument()
  })

  it('fetches usage when opened without a snapshot', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => usage,
      } as Response),
    )
    render(<ContextUsageDetail agentId="jeeves" conversationId="c1" />)
    await waitFor(() => {
      expect(screen.getByTestId('context-usage-label')).toHaveTextContent(
        '~12.3k tokens, window unknown',
      )
    })
  })
})

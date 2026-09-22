/**
 * #720 — the computer pane renders the agent's Daytona sandbox display.
 *
 * Contracts:
 * - GET /v1/agents/<id>/sandbox-display/ drives the pane; an empty payload
 *   (`display: null`) renders an honest empty state with the reason —
 *   never a fabricated screenshot.
 * - An iframe display renders the preview URL in a sandboxed iframe with a
 *   manual refresh button; secrets never appear in the DOM.
 * - The query only polls while the pane is open.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ComputerControlStub } from '../ComputerControlStub'

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

describe('#720 sandbox display in the computer pane', () => {
  let displayPayload: Record<string, unknown>
  let displayHits: number

  beforeEach(() => {
    displayHits = 0
    displayPayload = { agent_id: 'codey', provider: 'none', display: null, reason: 'provider_not_daytona' }
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('sandbox-display')) {
          displayHits += 1
          return jsonResponse(displayPayload)
        }
        if (url.includes('/test-schedules/status')) {
          return jsonResponse({ object: 'test_schedule_status', failure_count: 0, failures: [] })
        }
        if (url.includes('/routines')) {
          return jsonResponse({ object: 'routine_list', agent_id: 'codey', routines: [] })
        }
        return jsonResponse({ data: [] })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function openPane() {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ComputerControlStub agentId="codey" agentName="Codey" />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Computer control' }))
    await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
  }

  it('shows the honest empty state when no sandbox is configured', async () => {
    await openPane()
    const region = await screen.findByTestId('sandbox-display')
    expect(region).toHaveTextContent('No sandbox configured')
    expect(region).toHaveTextContent('provider_not_daytona')
    expect(screen.queryByTestId('sandbox-display-frame')).not.toBeInTheDocument()
  })

  it('renders an iframe for a live sandbox preview URL with a refresh control', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: { kind: 'iframe', url: 'https://sandbox.example.invalid/preview/' },
    }
    await openPane()
    const frame = await screen.findByTestId('sandbox-display-frame')
    expect(frame).toHaveAttribute('src', 'https://sandbox.example.invalid/preview/')
    expect(frame).toHaveAttribute('title', "Codey's sandbox")
    const before = displayHits
    fireEvent.click(screen.getByTestId('sandbox-display-refresh'))
    await waitFor(() => expect(displayHits).toBeGreaterThan(before))
  })

  it('explains an inactive daytona sandbox instead of pretending', async () => {
    displayPayload = { agent_id: 'codey', provider: 'daytona', display: null, reason: 'no_active_sandbox' }
    await openPane()
    const region = await screen.findByTestId('sandbox-display')
    expect(region).toHaveTextContent('Sandbox not active')
    expect(region).toHaveTextContent('no_active_sandbox')
  })
})

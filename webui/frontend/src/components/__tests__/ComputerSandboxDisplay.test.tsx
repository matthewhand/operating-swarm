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
import { OPEN_SETTINGS_EVENT } from '../SettingsSheet'

/** #1077: capture which settings section the Configure action requests. */
function captureSettingsSection(): { read: () => string | null; stop: () => void } {
  let section: string | null = null
  const handler = (event: Event) => {
    section = (event as CustomEvent<{ section?: string }>).detail?.section ?? null
  }
  window.addEventListener(OPEN_SETTINGS_EVENT, handler)
  return {
    read: () => section,
    stop: () => window.removeEventListener(OPEN_SETTINGS_EVENT, handler),
  }
}

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
    expect(region).toHaveTextContent('No sandbox provider configured')
    // #1077: the raw internal reason never reaches the user; a Configure
    // action routes straight to the sandbox settings section.
    expect(region).not.toHaveTextContent('provider_not_daytona')
    const configure = screen.getByTestId('sandbox-display-configure')
    const probe = captureSettingsSection()
    fireEvent.click(configure)
    expect(probe.read()).toBe('sandboxes')
    probe.stop()
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

  it('D5: sandboxes the preview iframe with allow-scripts only', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: { kind: 'iframe', url: 'https://sandbox.daytona.example.invalid/preview/' },
    }
    await openPane()
    const frame = await screen.findByTestId('sandbox-display-frame')
    const attr = frame.getAttribute('sandbox') ?? ''
    expect(attr).toContain('allow-scripts')
    expect(attr).not.toContain('allow-same-origin')
  })

  it('D1: surfaces availability in the empty state, distinct from the reason', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'none',
      display: null,
      reason: 'provider_not_daytona',
      available: false,
    }
    await openPane()
    const indicator = await screen.findByTestId('sandbox-display-available')
    expect(indicator).toHaveTextContent('Not available')
    expect(indicator).toHaveAttribute('data-available', 'false')
    expect(screen.getByTestId('sandbox-display-reason')).toHaveTextContent(
      'No sandbox provider configured',
    )
  })

  it('D1: surfaces availability alongside a live preview', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: { kind: 'iframe', url: 'https://sandbox.example.invalid/preview/' },
      available: true,
      sandbox: { id: 'vm-available', status: 'started' },
    }
    await openPane()
    await screen.findByTestId('sandbox-display-frame')
    const indicator = screen.getByTestId('sandbox-display-available')
    expect(indicator).toHaveTextContent('Available')
    expect(indicator).toHaveAttribute('data-available', 'true')
  })

  it('D3: explains an inactive daytona sandbox with friendly copy, raw code in data-attr', async () => {
    displayPayload = { agent_id: 'codey', provider: 'daytona', display: null, reason: 'no_active_sandbox' }
    await openPane()
    const region = await screen.findByTestId('sandbox-display')
    expect(region).toHaveTextContent('Sandbox not active')
    // The internal code never reads as user-facing text...
    expect(region).not.toHaveTextContent('no_active_sandbox')
    // ...but stays available for debugging via the tooltip/data-attr.
    const reasonNode = screen.getByTestId('sandbox-display-reason')
    expect(reasonNode).toHaveAttribute('data-reason', 'no_active_sandbox')
    expect(reasonNode).toHaveAttribute('title', 'no_active_sandbox')
  })

  it('D2: renders the credential row in the live branch, never the value', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: { kind: 'iframe', url: 'https://sandbox.example.invalid/preview/' },
      available: true,
      sandbox: { id: 'vm-live', status: 'started' },
      credential: { env_var: 'DAYTONA_API_KEY', set: true },
    }
    await openPane()
    await screen.findByTestId('sandbox-display-frame')
    const credential = screen.getByTestId('sandbox-display-credential')
    expect(credential).toHaveTextContent('DAYTONA_API_KEY')
    expect(credential).toHaveTextContent('set')
    expect(credential).not.toHaveTextContent('sk-')
  })

  it('names the credential env var and shows the operator hint when unreachable', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: null,
      reason: 'no_active_sandbox',
      available: false,
      sandbox: null,
      credential: { env_var: 'DAYTONA_API_KEY', set: false },
      probe: {
        ok: false,
        classification: 'env_name_unset',
        detail: 'Environment variable DAYTONA_API_KEY is not set in the server environment.',
        operator_hint: 'systemctl --user set-environment DAYTONA_API_KEY=<key>',
      },
    }
    await openPane()
    const region = await screen.findByTestId('sandbox-display')
    expect(region).toHaveTextContent('Sandbox not active')
    const credential = screen.getByTestId('sandbox-display-credential')
    expect(credential).toHaveTextContent('DAYTONA_API_KEY')
    expect(credential).toHaveTextContent('not set')
    expect(screen.getByTestId('sandbox-display-hint')).toHaveTextContent('systemctl')
    expect(screen.queryByTestId('sandbox-display-frame')).not.toBeInTheDocument()
  })

  it('shows the live sandbox id and status alongside the preview', async () => {
    displayPayload = {
      agent_id: 'codey',
      provider: 'daytona',
      display: { kind: 'iframe', url: 'https://sandbox.example.invalid/preview/' },
      available: true,
      sandbox: { id: 'vm-123', status: 'started' },
    }
    await openPane()
    await screen.findByTestId('sandbox-display-frame')
    const status = screen.getByTestId('sandbox-display-status')
    expect(status).toHaveTextContent('vm-123')
    expect(status).toHaveTextContent('started')
  })
})

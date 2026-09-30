/**
 * #1447 — drop the Computer Control Agent tab; keep config vs routines IA.
 *
 * Config (identity, role, routing, instructions, sandbox opt-in) lives on
 * `AgentConfigSidepane`. Computer Control owns Routines and Test schedule.
 * The two surfaces must not host each other's fields.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ComputerControlStub } from '../ComputerControlStub'
import AgentConfigSidepane from '../AgentConfigSidepane'

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

describe('#1447 config vs routines IA', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input)
        if (url.includes('/test-schedules/status')) {
          return jsonResponse({ object: 'test_schedule_status', failure_count: 0, failures: [] })
        }
        if (url.includes('/test-schedules')) {
          return jsonResponse({ object: 'test_schedule_list', schedules: [], failure_count: 0 })
        }
        if (url.includes('/routines')) {
          return jsonResponse({ object: 'routine_list', agent_id: 'codey', routines: [] })
        }
        if (url.includes('/llm-profiles')) {
          return jsonResponse({
            object: 'llm_profiles',
            profiles: [],
            default_llm_profile: '',
            warnings: [],
          })
        }
        return jsonResponse({ data: [] })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    localStorage.clear()
  })

  it('Computer Control has Routines + Test schedule only — no Agent tab or config fields', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ComputerControlStub agentId="codey" agentName="Codey" />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Computer control' }))
    const dialog = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })

    expect(within(dialog).getAllByRole('tab').map((tab) => tab.textContent)).toEqual([
      'Routines',
      'Test schedule',
    ])
    expect(within(dialog).queryByRole('tab', { name: /^Agent$/ })).toBeNull()
    expect(within(dialog).queryByTestId('agent-customisation-pane')).toBeNull()
    expect(within(dialog).queryByTestId('agent-config-sidepane')).toBeNull()
    expect(within(dialog).queryByTestId('sandbox-opt-in')).toBeNull()
    expect(within(dialog).queryByLabelText('Agent name')).toBeNull()
    expect(within(dialog).queryByLabelText('System instruction')).toBeNull()
    expect(within(dialog).queryByRole('button', { name: /^Save agent$/ })).toBeNull()
    // The routines pane is a lazy chunk fed by a query — wait for it rather
    // than racing its first paint.
    expect(await within(dialog).findByRole('heading', { name: 'Routines' })).toBeInTheDocument()
  })

  it('AgentConfigSidepane owns config fields and does not render Routines', () => {
    render(
      <AgentConfigSidepane
        agentId="codey"
        agentName="Codey"
        agentKind="api"
        workspaceEditable
        onClose={() => {}}
      />,
    )
    const pane = screen.getByTestId('agent-config-sidepane')
    expect(within(pane).getByTestId('agent-config-name-input')).toBeInTheDocument()
    expect(within(pane).getByTestId('agent-config-role')).toBeInTheDocument()
    expect(within(pane).getByTestId('agent-config-profile')).toBeInTheDocument()
    expect(within(pane).getByTestId('agent-config-instructions')).toBeInTheDocument()
    expect(within(pane).getByTestId('sandbox-opt-in')).toBeInTheDocument()
    expect(within(pane).queryByRole('heading', { name: 'Routines' })).toBeNull()
    expect(within(pane).queryByRole('tab', { name: 'Routines' })).toBeNull()
    expect(within(pane).queryByRole('tab', { name: 'Test schedule' })).toBeNull()
  })
})

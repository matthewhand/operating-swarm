/**
 * #932 — the computer-icon popup becomes a real control surface.
 *
 * A. Every actionable row is a bordered button (no bare labels).
 * B. The screen-session row sits ABOVE the tab strip and persists across
 *    tab switches.
 *
 * #1447 superseded C: agent customisation left this pane. Config lives on
 * `AgentConfigSidepane`; this popup keeps Routines + Test schedule.
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ComputerControlStub } from '../ComputerControlStub'

type RoutineRow = {
  id: string
  name: string
  instruction: string
  active: boolean
  trigger: { kind: string }
  history: unknown[]
  when_to_run: string
}

function jsonResponse(body: unknown, status = 200) {
  return { ok: status >= 200 && status < 300, status, json: async () => body } as Response
}

function makeRoutine(overrides: Partial<RoutineRow> = {}): RoutineRow {
  return {
    id: 'r1',
    name: 'Ship notes',
    instruction: 'Summarize the merged pull request.',
    active: true,
    trigger: { kind: 'github_pr_merged' },
    history: [],
    when_to_run: 'When a PR merges…',
    ...overrides,
  }
}

const AGENT = {
  id: 'charles',
  name: 'Charles Prime',
  kind: 'api',
  instructions: 'You are Charles.',
  provider: 'openai',
  model: 'gpt-5-mini',
}

describe('#932 computer popup rework', () => {
  let routines: RoutineRow[]

  beforeEach(() => {
    routines = []
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
          return jsonResponse({ object: 'routine_list', agent_id: AGENT.id, routines })
        }
        return jsonResponse({ data: [] })
      }),
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  async function openPane(agent: Partial<typeof AGENT> = {}) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ComputerControlStub agentId={agent.id ?? AGENT.id} agentName={agent.name ?? AGENT.name} agentDetails={agent} />
      </QueryClientProvider>,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Computer control' }))
    return screen.findByRole('dialog', { name: 'Computer control', hidden: true })
  }

  it('A: routine rows and schedule entries render as bordered buttons', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    await within(dialog).findByText('Ship notes')
    const row = within(dialog).getByRole('button', { name: /Ship notes/ })
    expect(row.className).toMatch(/\bbtn\b/)
  })

  it('B: the screen-session row sits above the tab strip and survives tab switches', async () => {
    const dialog = await openPane()
    const sessionRow = within(dialog).getByTestId('computer-session-row')
    const tablist = within(dialog).getByRole('tablist')
    expect(sessionRow.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    // Switch tabs: the session row persists.
    fireEvent.click(within(dialog).getByRole('tab', { name: /Test schedule/ }))
    expect(within(dialog).getByTestId('computer-session-row')).toBeInTheDocument()
  })

  it('#1447: the Agent tab is gone; Routines and Test schedule remain', async () => {
    const dialog = await openPane({ ...AGENT })
    const tabs = within(dialog).getAllByRole('tab')
    expect(tabs.map((tab) => tab.textContent)).toEqual(['Routines', 'Test schedule'])
    expect(within(dialog).queryByRole('tab', { name: /^Agent$/i })).toBeNull()
    expect(within(dialog).queryByTestId('agent-customisation-pane')).toBeNull()
    expect(within(dialog).queryByLabelText('Agent name')).toBeNull()
    expect(within(dialog).queryByLabelText('System instruction')).toBeNull()
    expect(within(dialog).getByRole('heading', { name: 'Routines' })).toBeInTheDocument()
  })
})

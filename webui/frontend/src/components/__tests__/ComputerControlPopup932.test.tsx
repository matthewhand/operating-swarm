/**
 * #932 — the computer-icon popup becomes a real control surface.
 *
 * A. Every actionable row is a bordered button (no bare labels).
 * B. The screen-session row sits ABOVE the tab strip and persists across
 *    tab switches.
 * C. Agent customisation inline: name (all kinds) +, for API agents,
 *    system instruction with an AI-writer overlay and a provider/model pick.
 */
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  let patchBody: Record<string, unknown> | null

  beforeEach(() => {
    routines = []
    patchBody = null
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/assist-draft')) {
          return jsonResponse({ status: 'success', draft: 'Drafted instruction by AI.' })
        }
        if (url.includes('/llm-profiles')) {
          return jsonResponse({
            object: 'llm_profiles',
            profiles: [
              { id: 'openai/gpt-5-mini', owned_by: 'openai', model: 'gpt-5-mini' },
              { id: 'anthropic/claude-4', owned_by: 'anthropic', model: 'claude-4' },
            ],
            default_llm_profile: 'openai/gpt-5-mini',
            warnings: [],
          })
        }
        if (url.includes('/blueprints/custom/charles') && method === 'PATCH') {
          patchBody = init?.body ? JSON.parse(String(init.body)) : {}
          return jsonResponse({ object: 'blueprint', id: 'charles', ...patchBody })
        }
        if (url.includes('/test-schedules/status')) {
          return jsonResponse({ object: 'test_schedule_status', failure_count: 0, failures: [] })
        }
        if (url.includes('/test-schedules') && method === 'GET') {
          return jsonResponse({ object: 'test_schedule_list', schedules: [], failure_count: 0 })
        }
        if (url.includes('/routines') && method === 'GET') {
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

  it('C: an API agent exposes name, system instruction + writer, and provider/model', async () => {
    const dialog = await openPane({ ...AGENT })
    fireEvent.click(within(dialog).getByRole('tab', { name: /Agent/i }))
    const nameField = await within(dialog).findByLabelText('Agent name')
    expect(nameField).toHaveValue('Charles Prime')
    const instruction = within(dialog).getByLabelText('System instruction')
    expect(instruction).toHaveValue('You are Charles.')
    // AI-writer overlay drafts and applies back only on Apply.
    const writerBtn = within(dialog).getByRole('button', { name: /AI (draft|writer)/i })
    await act(async () => {
      fireEvent.click(writerBtn)
    })
    const overlay = await within(dialog).findByTestId('ai-writer-overlay')
    expect(await within(overlay).findByText('Drafted instruction by AI.')).toBeInTheDocument()
    fireEvent.click(within(overlay).getByRole('button', { name: /^Apply$/ }))
    await waitFor(() =>
      expect(within(dialog).getByLabelText('System instruction')).toHaveValue(
        'Drafted instruction by AI.',
      ),
    )
    // Provider/model pick is present for API agents.
    expect(within(dialog).getByLabelText('Provider / model')).toBeInTheDocument()
    // Save persists everything through PATCH.
    fireEvent.change(within(dialog).getByLabelText('Agent name'), {
      target: { value: 'Charles Prime X' },
    })
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /^Save agent$/ }))
    })
    await waitFor(() => expect(patchBody).not.toBeNull())
    expect(patchBody).toMatchObject({
      name: 'Charles Prime X',
      instructions: 'Drafted instruction by AI.',
    })
  })

  it('C: non-API agents do not get the instruction/provider fields', async () => {
    const dialog = await openPane({ ...AGENT, kind: 'cli' })
    fireEvent.click(within(dialog).getByRole('tab', { name: /Agent/i }))
    expect(await within(dialog).findByLabelText('Agent name')).toBeInTheDocument()
    expect(within(dialog).queryByLabelText('System instruction')).toBeNull()
    expect(within(dialog).queryByLabelText('Provider / model')).toBeNull()
  })
})

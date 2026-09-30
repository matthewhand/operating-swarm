import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ComputerControlStub } from '../ComputerControlStub'
import { openChromeOverlay } from '../../lib/chromeOverlay'

type RoutineRow = {
  id: string
  name: string
  instruction: string
  active: boolean
  model?: string
  trigger: { kind: string; owner_repo: string; event: string; actor: string }
  history: Array<{ id: string; ran_at: string; status: string; source: string }>
  when_to_run: string
}

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response
}

function makeRoutine(overrides: Partial<RoutineRow> = {}): RoutineRow {
  return {
    id: 'r1',
    name: 'Ship notes',
    instruction: 'Summarize the merged pull request.',
    active: true,
    trigger: {
      kind: 'github_pr_merged',
      owner_repo: 'owner/repo',
      event: 'merged',
      actor: 'anyone',
    },
    history: [],
    when_to_run: 'When a PR merges in owner/repo…',
    ...overrides,
  }
}

describe('ComputerControlStub (REQ-80 / #432)', () => {
  let routines: RoutineRow[]

  beforeEach(() => {
    routines = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input)
        const method = (init?.method || 'GET').toUpperCase()
        if (url.includes('/routines/github-merge')) {
          return jsonResponse({ object: 'routine_merge_delivery', fired: [], count: 0 })
        }
        if (url.includes('/test-run')) {
          const id = url.match(/routines\/([^/]+)\/test-run/)?.[1]
          const row = routines.find((item) => item.id === id)
          if (!row) return jsonResponse({ error: 'Routine not found.' }, 404)
          return jsonResponse({
            object: 'routine_dry_run',
            dry_run: true,
            ...row,
            preview: {
              dry_run: true,
              side_effects: 'none',
              note: 'Dry-run preview. No messages sent, no PRs merged, instruction not executed.',
              trigger_summary: row.when_to_run,
              trigger_kind: row.trigger.kind,
              trigger_match: { kind: row.trigger.kind, summary: row.when_to_run, configured: true },
              prompt: row.instruction,
              model: row.model || '',
              armed: row.active,
              would_run_if_triggered: row.active,
            },
          })
        }
        if (url.includes('/routines/') && method === 'PATCH') {
          const id = url.match(/routines\/([^/]+)/)?.[1]
          const row = routines.find((item) => item.id === id)
          if (!row) return jsonResponse({ error: 'Routine not found.' }, 404)
          const patch = init?.body ? (JSON.parse(String(init.body)) as Partial<RoutineRow>) : {}
          Object.assign(row, patch)
          if (patch.trigger) row.when_to_run = `When a PR merges in ${patch.trigger.owner_repo || row.trigger.owner_repo}…`
          return jsonResponse({ object: 'routine', ...row })
        }
        if (url.includes('/routines/') && method === 'DELETE') {
          const id = url.match(/routines\/([^/]+)/)?.[1]
          routines = routines.filter((item) => item.id !== id)
          return jsonResponse({}, 204)
        }
        if (url.includes('/routines') && method === 'POST') {
          const body = init?.body ? (JSON.parse(String(init.body)) as Partial<RoutineRow>) : {}
          const created = makeRoutine({
            id: `r-${routines.length + 1}`,
            name: body.name || 'New routine',
            instruction: body.instruction || '',
            active: body.active ?? false,
            model: body.model || '',
            trigger: {
              kind: 'github_pr_merged',
              owner_repo: '',
              event: 'merged',
              actor: 'anyone',
            },
            when_to_run: 'When a PR merges in a GitHub repo…',
          })
          routines.push(created)
          return jsonResponse({ object: 'routine', ...created }, 201)
        }
        if (url.includes('/llm-profiles')) {
          return jsonResponse({
            object: 'llm_profiles',
            profiles: [
              { id: 'orchestration', object: 'llm_profile', source: 'config', owned_by: 'openai', model: 'gpt-4o-mini' },
              { id: 'auxiliary', object: 'llm_profile', source: 'config', owned_by: 'openai', model: 'gpt-4o-mini' },
            ],
          })
        }
        if (url.includes('/routines') && method === 'GET') {
          return jsonResponse({ object: 'routine_list', agent_id: 'codey', routines })
        }
        if (url.includes('/test-schedules/status')) {
          return jsonResponse({ object: 'test_schedule_status', failure_count: 0, failures: [] })
        }
        if (url.includes('/test-schedules') && method === 'GET') {
          return jsonResponse({
            object: 'test_schedule_list',
            schedules: [
              {
                id: 'seed-remote-harness-health',
                name: 'Remote harness health',
                active: false,
                trigger: { kind: 'interval', seconds: 3600 },
                target: { kind: 'fleet', fleet: 'all' },
                check: { kind: 'harness_health', name: 'remote_health' },
                history: [],
                when_to_run: 'Every 1 hour…',
              },
            ],
            failure_count: 0,
          })
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
    const dialog = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
    expect(dialog).toHaveClass('modal-open')
    expect(dialog).toHaveClass('modal-end')
    return dialog
  }

  it('shows an icon-only computer control that expands a right pane', async () => {
    const dialog = await openPane()
    const trigger = screen.getByRole('button', { name: 'Computer control' })
    expect(trigger).toHaveAttribute('aria-haspopup', 'dialog')
    expect(trigger).toHaveClass('btn-square')
    expect(trigger.querySelector('svg')).toBeTruthy()
    expect(trigger).not.toHaveTextContent(/Computer control/i)
    expect(dialog.textContent).not.toMatch(/WIP|E2B|xdotool|CDP|CUA|:8001/i)
  })

  it('shows the thumbnail region above the tab strip on every tab (#1077)', async () => {
    const dialog = await openPane()
    const thumbnail = within(dialog).getByTestId('agent-screen-thumbnail')
    const tablist = within(dialog).getByRole('tablist', { name: 'Computer control panes' })
    // the viewport lives above the tab navigation, not inside a tab pane
    expect(thumbnail.compareDocumentPosition(tablist) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(thumbnail).getByText("Codey's screen")).toBeInTheDocument()
    expect(within(thumbnail).getByText('No screen session')).toBeInTheDocument()
    expect(thumbnail.querySelector('img')).toBeNull()
    // switching tabs never unmounts it (#1447: Agent tab is gone)
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Routines' }))
    expect(within(dialog).getByTestId('agent-screen-thumbnail')).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('tab', { name: 'Test schedule' }))
    expect(within(dialog).getByTestId('agent-screen-thumbnail')).toBeTruthy()
  })

  it('creates a routine from + and opens the editor; Back returns to the list', async () => {
    const dialog = await openPane()
    // The routines pane is a lazy chunk fed by a query — wait for the
    // Add routine affordance rather than racing its first paint.
    fireEvent.click(await within(dialog).findByRole('button', { name: 'Add routine' }))
    const editor = await within(dialog).findByTestId('routine-editor')
    expect(within(editor).getByRole('heading', { name: 'Routine' })).toBeInTheDocument()
    expect(within(editor).getByLabelText('Name')).toHaveValue('New routine')
    expect(within(editor).getByLabelText('Agent Instructions')).toBeInTheDocument()
    expect(within(editor).getByRole('switch', { name: 'Armed' })).toBeInTheDocument()
    expect(within(editor).getByRole('button', { name: 'Test' })).toBeInTheDocument()
    expect(within(editor).getByRole('button', { name: 'Save' })).toBeInTheDocument()
    expect(within(editor).getByLabelText('Model')).toBeInTheDocument()
    expect(within(editor).getByRole('button', { name: 'Delete' })).toBeInTheDocument()
    expect(within(editor).getByText('When to run')).toBeInTheDocument()
    expect(within(editor).getByDisplayValue('When a PR merges')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Back' }))
    })
    expect(within(dialog).queryByTestId('routine-editor')).not.toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Routines' })).toBeInTheDocument()
    expect(within(dialog).getByText('New routine')).toBeInTheDocument()
  })

  it('opens an existing row in the editor and Test shows a dry-run preview', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    expect(await within(dialog).findByText('When a PR merges in owner/repo…')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    expect(within(editor).getByLabelText('Repository')).toHaveValue('owner/repo')

    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Test' }))
    })
    const preview = await within(editor).findByTestId('routine-dry-run-preview')
    expect(preview).toHaveTextContent('Dry-run preview')
    expect(within(preview).getByTestId('routine-dry-run-prompt')).toHaveTextContent(
      'Summarize the merged pull request.',
    )
    expect(within(preview).getByTestId('routine-dry-run-side-effects')).toHaveTextContent('none')
    expect(within(editor).queryByText('Just now')).not.toBeInTheDocument()
  })

  it('keeps an unsaved instruction when another field round-trips (#1405)', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    expect(await within(dialog).findByText('When a PR merges in owner/repo…')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    fireEvent.change(within(editor).getByLabelText('Agent Instructions'), {
      target: { value: 'Edited locally.' },
    })
    const name = within(editor).getByLabelText('Name')
    fireEvent.change(name, { target: { value: 'Ship notes renamed' } })
    fireEvent.blur(name)
    await waitFor(() => expect(routines[0]?.name).toBe('Ship notes renamed'))
    expect(within(editor).getByLabelText('Agent Instructions')).toHaveValue('Edited locally.')
    expect(routines[0]?.instruction).toBe('Summarize the merged pull request.')
  })

  it('persists the model as a profile id and previews the on-screen prompt (#1405)', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    expect(await within(dialog).findByText('When a PR merges in owner/repo…')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    const model = await within(editor).findByLabelText('Model')
    expect(await within(editor).findByRole('option', { name: 'orchestration' })).toBeInTheDocument()
    expect(within(editor).queryByRole('option', { name: 'gpt-4o-mini' })).not.toBeInTheDocument()
    fireEvent.change(model, { target: { value: 'auxiliary' } })
    await waitFor(() => expect(routines[0]?.model).toBe('auxiliary'))

    fireEvent.change(within(editor).getByLabelText('Agent Instructions'), {
      target: { value: 'Edited locally.' },
    })
    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Test' }))
    })
    expect(await within(editor).findByTestId('routine-dry-run-prompt')).toHaveTextContent('Edited locally.')
  })

  it('clears a dry-run preview when a different routine is opened (#1405)', async () => {
    routines.push(makeRoutine())
    routines.push(makeRoutine({ id: 'r2', name: 'Other notes', instruction: 'Second prompt.' }))
    const dialog = await openPane()
    expect(await within(dialog).findByText('Ship notes')).toBeInTheDocument()
    expect(await within(dialog).findByText('Other notes')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Test' }))
    })
    expect(await within(editor).findByTestId('routine-dry-run-preview')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Back' }))
    })
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Other notes/ }))
    })
    const next = await within(dialog).findByTestId('routine-editor')
    expect(within(next).queryByTestId('routine-dry-run-preview')).not.toBeInTheDocument()
  })

  it('deletes a routine after confirm and returns to an empty list', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    expect(await within(dialog).findByText('Ship notes')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Delete' }))
    })
    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Confirm delete' }))
    })
    expect(await within(dialog).findByRole('heading', { name: 'Routines' })).toBeInTheDocument()
    expect(within(dialog).queryByText('Ship notes')).not.toBeInTheDocument()
    expect(within(dialog).getByText('No routines yet.')).toBeInTheDocument()
  })

  it('switches to the Test schedule pane with seeded fleet proofs', async () => {
    const dialog = await openPane()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('tab', { name: /Test schedule/ }))
    })
    expect(await within(dialog).findByTestId('test-schedule-pane')).toBeInTheDocument()
    expect(within(dialog).getByRole('heading', { name: 'Test schedule' })).toBeInTheDocument()
    expect(await within(dialog).findByText('Remote harness health')).toBeInTheDocument()
    expect(within(dialog).getByText('Every 1 hour…')).toBeInTheDocument()
  })

  it('opens from the chrome overlay bus without leaving chat chrome', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={client}>
        <ComputerControlStub agentId="codey" agentName="Codey" />
      </QueryClientProvider>,
    )
    await act(async () => {
      openChromeOverlay('computer-control')
    })
    const dialog = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
    expect(dialog).toHaveClass('modal-open')
    expect(dialog).toHaveClass('modal-end')
  })
})

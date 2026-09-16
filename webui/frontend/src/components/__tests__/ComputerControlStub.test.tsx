import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ComputerControlStub } from '../ComputerControlStub'
import { openChromeOverlay } from '../../lib/chromeOverlay'

type RoutineRow = {
  id: string
  name: string
  instruction: string
  active: boolean
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
          row.history = [
            {
              id: 'h-now',
              ran_at: new Date().toISOString(),
              status: 'success',
              source: 'test_run',
            },
            ...row.history,
          ]
          return jsonResponse({ object: 'routine', ...row })
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
    render(<ComputerControlStub agentId="codey" agentName="Codey" />)
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

  it('shows the thumbnail region above Routines and +', async () => {
    const dialog = await openPane()
    const thumbnail = within(dialog).getByTestId('agent-screen-thumbnail')
    const routinesHeading = within(dialog).getByRole('heading', { name: 'Routines' })
    const add = within(dialog).getByRole('button', { name: 'Add routine' })
    expect(thumbnail.compareDocumentPosition(routinesHeading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(routinesHeading.compareDocumentPosition(add) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(within(thumbnail).getByText("Codey's screen")).toBeInTheDocument()
    expect(within(thumbnail).getByText('No screen session')).toBeInTheDocument()
    expect(thumbnail.querySelector('img')).toBeNull()
  })

  it('creates a routine from + and opens the editor; Back returns to the list', async () => {
    const dialog = await openPane()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: 'Add routine' }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    expect(within(editor).getByRole('heading', { name: 'Routine' })).toBeInTheDocument()
    expect(within(editor).getByLabelText('Name')).toHaveValue('New routine')
    expect(within(editor).getByLabelText('Instruction')).toBeInTheDocument()
    expect(within(editor).getByLabelText('Active')).toBeInTheDocument()
    expect(within(editor).getByRole('button', { name: 'Test run' })).toBeInTheDocument()
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

  it('opens an existing row in the editor and Test run appends relative-time history', async () => {
    routines.push(makeRoutine())
    const dialog = await openPane()
    expect(await within(dialog).findByText('When a PR merges in owner/repo…')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(within(dialog).getByRole('button', { name: /Ship notes/ }))
    })
    const editor = await within(dialog).findByTestId('routine-editor')
    expect(within(editor).getByLabelText('Repository')).toHaveValue('owner/repo')

    await act(async () => {
      fireEvent.click(within(editor).getByRole('button', { name: 'Test run' }))
    })
    expect(await within(editor).findByText('Just now')).toBeInTheDocument()
    expect(within(editor).getByLabelText('Routine history').querySelector('.text-success, .text-success *')).toBeTruthy()
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
    render(<ComputerControlStub agentId="codey" agentName="Codey" />)
    await act(async () => {
      openChromeOverlay('computer-control')
    })
    const dialog = await screen.findByRole('dialog', { name: 'Computer control', hidden: true })
    expect(dialog).toHaveClass('modal-open')
    expect(dialog).toHaveClass('modal-end')
  })
})

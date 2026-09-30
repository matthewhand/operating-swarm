/**
 * #1403 — GitHub-issue triggers pre-select Open Pull Request; removal persists.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import { TOOL_OPEN_PULL_REQUEST, type Routine } from '../../lib/routines'

const { createRoutineMock, updateRoutineMock } = vi.hoisted(() => ({
  createRoutineMock: vi.fn(),
  updateRoutineMock: vi.fn(),
}))

vi.mock('../../lib/routines', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routines')>()
  return {
    ...actual,
    createRoutine: (...args: unknown[]) => createRoutineMock(...args),
    updateRoutine: (...args: unknown[]) => updateRoutineMock(...args),
  }
})

function renderCreate() {
  return render(
    <RoutineEditorDialog
      open
      onClose={() => {}}
      prefill={{ agentId: 'codey' }}
    />,
  )
}

function chooseIssueTrigger() {
  fireEvent.change(screen.getByLabelText('Trigger'), { target: { value: 'github_event' } })
  const repo = screen.getByTestId('github-trigger-repo')
  fireEvent.change(repo, { target: { value: 'owner/repo' } })
  fireEvent.blur(repo)
}

describe('RoutineEditorDialog Open PR tool (#1403)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
    updateRoutineMock.mockReset()
  })

  it('defaults Open Pull Request off for a PR-merge trigger', () => {
    renderCreate()
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    expect(box.checked).toBe(false)
    expect(screen.getByTestId('routine-tools')).toBeInTheDocument()
  })

  it('pre-selects Open Pull Request when the trigger is a GitHub issue event', () => {
    renderCreate()
    fireEvent.change(screen.getByLabelText('Trigger'), { target: { value: 'github_event' } })
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    expect(box.checked).toBe(true)
  })

  it('omits tools on create when the operator never toggled them', async () => {
    createRoutineMock.mockResolvedValueOnce({
      id: 'r-new',
      name: 'New routine',
      instruction: '',
      active: true,
      trigger: { kind: 'github_event', event_type: 'issues.opened', owner_repo: '' },
      tools: [TOOL_OPEN_PULL_REQUEST],
      tools_explicit: false,
      history: [],
    })
    renderCreate()
    chooseIssueTrigger()
    fireEvent.click(screen.getByTestId('routine-editor-save'))
    await waitFor(() => expect(createRoutineMock).toHaveBeenCalled())
    const payload = createRoutineMock.mock.calls[0][1] as { tools?: string[] }
    expect(payload.tools).toBeUndefined()
  })

  it('persists removal when the operator unchecks Open Pull Request', async () => {
    createRoutineMock.mockResolvedValueOnce({
      id: 'r-new',
      name: 'New routine',
      instruction: '',
      active: true,
      trigger: { kind: 'github_event', event_type: 'issues.opened', owner_repo: '' },
      tools: [],
      tools_explicit: true,
      history: [],
    })
    renderCreate()
    chooseIssueTrigger()
    fireEvent.click(screen.getByTestId('routine-tool-open-pull-request'))
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    expect(box.checked).toBe(false)
    fireEvent.click(screen.getByTestId('routine-editor-save'))
    await waitFor(() => expect(createRoutineMock).toHaveBeenCalled())
    const payload = createRoutineMock.mock.calls[0][1] as { tools?: string[] }
    expect(payload.tools).toEqual([])
  })

  it('PATCHes tools when editing an existing issue routine', async () => {
    const initial: Routine = {
      id: 'r-1',
      name: 'Solve',
      instruction: 'Fix it.',
      active: true,
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: 'owner/repo',
      },
      tools: [TOOL_OPEN_PULL_REQUEST],
      tools_explicit: false,
      history: [],
    }
    updateRoutineMock.mockResolvedValue({ ...initial, tools: [], tools_explicit: true })
    render(
      <RoutineEditorDialog open onClose={() => {}} initial={initial} agentId="codey" />,
    )
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    expect(box.checked).toBe(true)
    fireEvent.click(box)
    // Uncheck must show immediately. tools_explicit is still false on the
    // server row, so the optimistic draft has to record the operator choice.
    expect(box.checked).toBe(false)
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock.mock.calls[0][2]).toEqual({ tools: [] })
  })

  it('restores the checkbox when the tools PATCH fails', async () => {
    const initial: Routine = {
      id: 'r-1',
      name: 'Solve',
      instruction: 'Fix it.',
      active: true,
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: 'owner/repo',
      },
      tools: [TOOL_OPEN_PULL_REQUEST],
      tools_explicit: false,
      history: [],
    }
    updateRoutineMock.mockRejectedValueOnce(new Error('nope'))
    render(
      <RoutineEditorDialog open onClose={() => {}} initial={initial} agentId="codey" />,
    )
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    fireEvent.click(box)
    expect(box.checked).toBe(false)
    await waitFor(() => expect(box.checked).toBe(true))
    expect(screen.getByText('nope')).toBeInTheDocument()
  })

  it('keeps a name edit made while a tools PATCH is failing', async () => {
    const initial: Routine = {
      id: 'r-1',
      name: 'Solve',
      instruction: 'Fix it.',
      active: true,
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: 'owner/repo',
      },
      tools: [TOOL_OPEN_PULL_REQUEST],
      tools_explicit: false,
      history: [],
    }
    let rejectUpdate: (err: Error) => void = () => {}
    updateRoutineMock.mockImplementation(
      () =>
        new Promise((_, reject) => {
          rejectUpdate = reject
        }),
    )
    render(
      <RoutineEditorDialog open onClose={() => {}} initial={initial} agentId="codey" />,
    )
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    fireEvent.click(box)
    expect(box.checked).toBe(false)
    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Renamed while saving' } })
    rejectUpdate(new Error('nope'))
    await waitFor(() => expect(box.checked).toBe(true))
    expect(screen.getByLabelText('Name')).toHaveValue('Renamed while saving')
    expect(screen.getByText('nope')).toBeInTheDocument()
  })
})

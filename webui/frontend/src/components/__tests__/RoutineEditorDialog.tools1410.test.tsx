/**
 * #1410 — instruction-gap suggestions: add / dismiss / no nag / no auto-enable.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import { TOOL_MEMORIES, TOOL_OPEN_PULL_REQUEST, type Routine } from '../../lib/routines'

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

vi.mock('../../lib/routineToolCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routineToolCatalog')>()
  return {
    ...actual,
    fetchRoutineToolCatalog: async () => actual.fallbackRoutineToolCatalog(),
  }
})

const intervalRoutine: Routine = {
  id: 'r-1410',
  name: 'Hourly recap',
  instruction: 'Summarize the last hour.',
  active: true,
  trigger: { kind: 'interval', seconds: 3600 },
  tools: [],
  tools_explicit: true,
  history: [],
}

describe('RoutineEditorDialog tool suggestions (#1410)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
    updateRoutineMock.mockReset()
    updateRoutineMock.mockImplementation(async (_agent: string, _id: string, patch: Partial<Routine>) => ({
      ...intervalRoutine,
      ...patch,
    }))
  })

  it('suggests Open Pull Request when instructions mention a PR and does not auto-enable it', () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{ ...intervalRoutine, instruction: 'Investigate the issue and open a pull request.' }}
        agentId="codey"
      />,
    )
    expect(screen.getByTestId('routine-tool-suggest-open_pull_request')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-suggest-reason-open_pull_request').textContent).toBe(
      'Instructions mention opening a PR — add Open Pull Request?',
    )
    const box = screen.getByTestId('routine-tool-open-pull-request') as HTMLInputElement
    expect(box.checked).toBe(false)
    expect(updateRoutineMock).not.toHaveBeenCalled()
  })

  it('adds Open Pull Request on one-click confirm', async () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{ ...intervalRoutine, instruction: 'Please open a PR.' }}
        agentId="codey"
      />,
    )
    fireEvent.click(screen.getByTestId('routine-tool-suggest-add-open_pull_request'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock.mock.calls[0][2]).toEqual({ tools: [TOOL_OPEN_PULL_REQUEST] })
  })

  it('suggests Memories when instructions mention MEMORIES', async () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{ ...intervalRoutine, instruction: 'Remember prior context from MEMORIES.' }}
        agentId="codey"
      />,
    )
    expect(screen.getByTestId('routine-tool-suggest-memories')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('routine-tool-suggest-add-memories'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock.mock.calls[0][2]).toEqual({ tools: [TOOL_MEMORIES] })
  })

  it('does not nag when the matching tool is already present', () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{
          ...intervalRoutine,
          instruction: 'Investigate the issue and open a pull request.',
          tools: [TOOL_OPEN_PULL_REQUEST],
        }}
        agentId="codey"
      />,
    )
    expect(screen.queryByTestId('routine-tool-suggest-open_pull_request')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routine-tool-suggestions')).not.toBeInTheDocument()
  })

  it('keeps a dismiss for the current draft', () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{ ...intervalRoutine, instruction: 'Please open a PR.' }}
        agentId="codey"
      />,
    )
    expect(screen.getByTestId('routine-tool-suggest-open_pull_request')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('routine-tool-suggest-dismiss-open_pull_request'))
    expect(screen.queryByTestId('routine-tool-suggest-open_pull_request')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Please open a PR!' },
    })
    expect(screen.queryByTestId('routine-tool-suggest-open_pull_request')).not.toBeInTheDocument()
  })

  it('updates suggestions as instructions change', () => {
    render(<RoutineEditorDialog open onClose={() => {}} initial={intervalRoutine} agentId="codey" />)
    expect(screen.queryByTestId('routine-tool-suggestions')).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Remember prior context from MEMORIES.' },
    })
    expect(screen.getByTestId('routine-tool-suggest-memories')).toBeInTheDocument()
  })
})

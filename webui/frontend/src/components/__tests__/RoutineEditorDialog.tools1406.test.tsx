/**
 * #1406 — + Add Tool or MCP picker: add / remove / persist; disabled reason.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import { fallbackRoutineToolCatalog } from '../../lib/routineToolCatalog'
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

vi.mock('../../lib/routineToolCatalog', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routineToolCatalog')>()
  return {
    ...actual,
    fetchRoutineToolCatalog: async () => actual.fallbackRoutineToolCatalog(),
  }
})

const intervalRoutine: Routine = {
  id: 'r-1',
  name: 'Hourly recap',
  instruction: 'Summarize the last hour.',
  active: true,
  trigger: { kind: 'interval', seconds: 3600 },
  tools: [],
  tools_explicit: true,
  history: [],
}

describe('RoutineEditorDialog extra tools (#1406)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
    updateRoutineMock.mockReset()
    updateRoutineMock.mockImplementation(async (_agent: string, _id: string, patch: Partial<Routine>) => ({
      ...intervalRoutine,
      ...patch,
    }))
  })

  it('opens the picker of catalog tools and installed MCP connectors', async () => {
    render(<RoutineEditorDialog open onClose={() => {}} initial={intervalRoutine} agentId="codey" />)
    fireEvent.click(screen.getByTestId('routine-add-tool-or-mcp'))
    expect(await screen.findByTestId('routine-tool-picker')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-pick-web_search')).toBeInTheDocument()
    expect(screen.getByTestId('routine-tool-pick-brave_search')).toBeInTheDocument()
    expect(fallbackRoutineToolCatalog().some((item) => item.id === 'web_search')).toBe(true)
  })

  it('adds a catalog tool and persists it', async () => {
    render(<RoutineEditorDialog open onClose={() => {}} initial={intervalRoutine} agentId="codey" />)
    fireEvent.click(screen.getByTestId('routine-add-tool-or-mcp'))
    fireEvent.click(await screen.findByTestId('routine-tool-pick-web_search'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock.mock.calls[0][2]).toEqual({ tools: ['web_search'] })
  })

  it('removes an extra tool and persists the list', async () => {
    const withTools: Routine = {
      ...intervalRoutine,
      tools: [TOOL_OPEN_PULL_REQUEST, 'web_search'],
      tools_explicit: true,
    }
    updateRoutineMock.mockImplementation(async (_agent: string, _id: string, patch: Partial<Routine>) => ({
      ...withTools,
      ...patch,
    }))
    render(<RoutineEditorDialog open onClose={() => {}} initial={withTools} agentId="codey" />)
    expect(screen.getByTestId('routine-tool-chip-web_search')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('routine-tool-remove-web_search'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock.mock.calls[0][2]).toEqual({ tools: [TOOL_OPEN_PULL_REQUEST] })
  })

  it('shows a clear reason on a disabled connector and does not add it', async () => {
    render(<RoutineEditorDialog open onClose={() => {}} initial={intervalRoutine} agentId="codey" />)
    fireEvent.click(screen.getByTestId('routine-add-tool-or-mcp'))
    const brave = await screen.findByTestId('routine-tool-pick-brave_search')
    expect(brave).toBeDisabled()
    expect(screen.getByTestId('routine-tool-reason-brave_search').textContent).toContain('BRAVE_API_KEY')
    expect(screen.getByTestId('routine-tool-reason-brave_search').textContent).toContain(
      'Tokens stay out of this builder',
    )
    fireEvent.click(brave)
    expect(updateRoutineMock).not.toHaveBeenCalled()
  })
})

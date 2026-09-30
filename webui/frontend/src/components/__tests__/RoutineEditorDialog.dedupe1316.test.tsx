/**
 * #1316 — the routine composer must not silently mint a twin.
 *
 * When the server answers 409, the editor surfaces an honest "already exists"
 * choice: open the existing routine, or deliberately create another.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import { DuplicateRoutineError, type Routine } from '../../lib/routines'

const { createRoutineMock } = vi.hoisted(() => ({ createRoutineMock: vi.fn() }))

vi.mock('../../lib/routines', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routines')>()
  return { ...actual, createRoutine: (...args: unknown[]) => createRoutineMock(...args) }
})

const existing: Routine = {
  id: 'r-existing',
  name: 'Ship notes',
  instruction: 'Summarize the merge.',
  active: true,
  trigger: {
    kind: 'github_pr_merged',
    owner_repo: 'owner/repo',
    event: 'merged',
    actor: 'anyone',
  },
  history: [],
}

function renderDialog(handlers: { onSaved?: (r: Routine) => void; onClose?: () => void } = {}) {
  return render(
    <RoutineEditorDialog
      open
      onClose={handlers.onClose ?? (() => {})}
      onSaved={handlers.onSaved}
      prefill={{ agentId: 'codey' }}
    />,
  )
}

describe('RoutineEditorDialog duplicate handling (#1316)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
  })

  it('offers "Open existing" when the server blocks a twin', async () => {
    createRoutineMock.mockRejectedValueOnce(
      new DuplicateRoutineError('already exists', existing),
    )
    const onSaved = vi.fn()
    const onClose = vi.fn()
    renderDialog({ onSaved, onClose })

    fireEvent.click(screen.getByTestId('routine-editor-save'))
    expect(await screen.findByTestId('routine-duplicate-conflict')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Open existing'))
    expect(onSaved).toHaveBeenCalledWith(existing)
    expect(onClose).toHaveBeenCalled()
  })

  it('creates anyway with allow_duplicate after the conflict', async () => {
    createRoutineMock
      .mockRejectedValueOnce(new DuplicateRoutineError('already exists', existing))
      .mockResolvedValueOnce({ ...existing, id: 'r-copy' })
    const onSaved = vi.fn()
    const onClose = vi.fn()
    renderDialog({ onSaved, onClose })

    fireEvent.click(screen.getByTestId('routine-editor-save'))
    await screen.findByTestId('routine-duplicate-conflict')

    fireEvent.click(screen.getByTestId('routine-create-anyway'))
    await waitFor(() => expect(createRoutineMock).toHaveBeenCalledTimes(2))
    expect(createRoutineMock.mock.calls[1][1]).toMatchObject({ allow_duplicate: true })
    expect(onSaved).toHaveBeenCalledWith(expect.objectContaining({ id: 'r-copy' }))
    expect(onClose).toHaveBeenCalled()
  })
})

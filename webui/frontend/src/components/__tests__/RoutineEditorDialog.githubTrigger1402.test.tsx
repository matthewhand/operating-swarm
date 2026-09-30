/**
 * #1402 — routine editor blocks unsupported / incomplete GitHub triggers
 * before Save, and persists chip fields as the OS trigger schema.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import { type Routine } from '../../lib/routines'
import { GITHUB_EVENT_ISSUE_COMMENT } from '../../lib/githubTriggerComposer'

const { createRoutineMock } = vi.hoisted(() => ({ createRoutineMock: vi.fn() }))

vi.mock('../../lib/routines', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routines')>()
  return { ...actual, createRoutine: (...args: unknown[]) => createRoutineMock(...args) }
})

function renderDialog() {
  return render(
    <RoutineEditorDialog open onClose={() => {}} onSaved={() => {}} prefill={{ agentId: 'codey' }} />,
  )
}

describe('RoutineEditorDialog GitHub trigger composer (#1402)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
  })

  it('shows chip fields when the trigger is a GitHub kind', () => {
    renderDialog()
    expect(screen.getByTestId('github-trigger-composer')).toBeInTheDocument()
    expect(screen.getByLabelText('Event kind')).toBeInTheDocument()
    expect(screen.getByLabelText('Actor scope')).toBeInTheDocument()
    expect(screen.getByLabelText('Object kind')).toBeInTheDocument()
    expect(screen.getByLabelText('Repository')).toBeInTheDocument()
  })

  it('blocks Save when Specific user is selected without a login', () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText('Actor scope'), { target: { value: 'specific' } })
    fireEvent.click(screen.getByTestId('routine-editor-save'))
    expect(createRoutineMock).not.toHaveBeenCalled()
    expect(screen.getAllByText(/GitHub login/i).length).toBeGreaterThanOrEqual(1)
  })

  it('blocks Save for a GitHub event without a repository', async () => {
    renderDialog()
    fireEvent.change(screen.getByLabelText('Trigger'), { target: { value: 'github_event' } })
    fireEvent.click(screen.getByTestId('routine-editor-save'))
    expect(createRoutineMock).not.toHaveBeenCalled()
    const notices = screen.getAllByText(/GitHub event triggers need a repository/i)
    expect(notices.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByTestId('github-trigger-unsupported')).toHaveTextContent(/owner\/repo/i)
  })

  it('saves an issue-comment trigger as github_event without loss', async () => {
    const created: Routine = {
      id: 'r-comment',
      name: 'Issue comments',
      instruction: 'Reply.',
      active: true,
      trigger: {
        kind: 'github_event',
        event_type: GITHUB_EVENT_ISSUE_COMMENT,
        owner_repo: 'acme/widgets',
        filters: { object_kind: 'issue' },
      },
      history: [],
    }
    createRoutineMock.mockResolvedValueOnce(created)
    renderDialog()

    fireEvent.change(screen.getByLabelText('Trigger'), { target: { value: 'github_event' } })
    fireEvent.change(screen.getByTestId('github-trigger-event'), { target: { value: 'comment' } })
    fireEvent.change(screen.getByTestId('github-trigger-object'), { target: { value: 'issue' } })
    fireEvent.change(screen.getByTestId('github-trigger-repo'), { target: { value: 'acme/widgets' } })
    fireEvent.blur(screen.getByTestId('github-trigger-repo'))
    fireEvent.click(screen.getByTestId('routine-editor-save'))

    await waitFor(() => expect(createRoutineMock).toHaveBeenCalled())
    expect(createRoutineMock.mock.calls[0][1].trigger).toEqual({
      kind: 'github_event',
      event_type: GITHUB_EVENT_ISSUE_COMMENT,
      owner_repo: 'acme/widgets',
      filters: { object_kind: 'issue' },
    })
  })
})

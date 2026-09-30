/**
 * #1405 — routine builder chrome: armed toggle, Save draft, Test dry-run, model.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import type { Routine } from '../../lib/routines'

const { createRoutineMock, updateRoutineMock, testRunRoutineMock } = vi.hoisted(() => ({
  createRoutineMock: vi.fn(),
  updateRoutineMock: vi.fn(),
  testRunRoutineMock: vi.fn(),
}))

vi.mock('../../lib/routines', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routines')>()
  return {
    ...actual,
    createRoutine: (...args: unknown[]) => createRoutineMock(...args),
    updateRoutine: (...args: unknown[]) => updateRoutineMock(...args),
    testRunRoutine: (...args: unknown[]) => testRunRoutineMock(...args),
  }
})

vi.mock('../../lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/api')>()
  return {
    ...actual,
    fetchLlmProfiles: vi.fn(async () => ({
      object: 'llm_profiles',
      profiles: [
        { id: 'orchestration', object: 'llm_profile', source: 'config', owned_by: 'openai', model: 'gpt-4o-mini' },
        { id: 'auxiliary', object: 'llm_profile', source: 'config', owned_by: 'openai', model: 'gpt-4o-mini' },
      ],
      default_llm_profile: 'orchestration',
      default_is_auto: false,
      override_per_task: false,
      task_llm_profiles: {},
      auto_picks: {},
      warnings: [],
      routes: {},
      task_classes: [],
    })),
  }
})

const saved: Routine = {
  id: 'r-1',
  name: 'Ship notes',
  instruction: 'Summarize the merge.',
  active: false,
  model: 'orchestration',
  trigger: {
    kind: 'github_pr_merged',
    owner_repo: 'owner/repo',
    event: 'merged',
    actor: 'anyone',
  },
  history: [],
}

function renderNew() {
  return render(
    <RoutineEditorDialog open onClose={() => {}} onSaved={() => {}} prefill={{ agentId: 'codey' }} />,
  )
}

function renderExisting(initial: Routine = saved) {
  return render(
    <RoutineEditorDialog
      open
      onClose={() => {}}
      onSaved={() => {}}
      initial={initial}
      agentId="codey"
    />,
  )
}

describe('RoutineEditorDialog builder chrome (#1405)', () => {
  beforeEach(() => {
    createRoutineMock.mockReset()
    updateRoutineMock.mockReset()
    testRunRoutineMock.mockReset()
  })

  it('shows Inactive/Active (armed) toggle, Save, Test, and a model picker', async () => {
    renderNew()
    const toggle = screen.getByTestId('routine-armed-toggle')
    expect(toggle).toHaveTextContent('Inactive')
    expect(toggle).toHaveTextContent('Active')
    expect(screen.getByRole('switch', { name: 'Armed' })).not.toBeChecked()
    expect(screen.getByTestId('routine-editor-save')).toHaveTextContent('Save')
    expect(screen.getByTestId('routine-editor-test')).toHaveTextContent('Test')
    expect(screen.getByLabelText('Agent Instructions')).toBeInTheDocument()
    expect(await screen.findByTestId('routine-model-picker')).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'orchestration' })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: 'gpt-4o-mini' })).not.toBeInTheDocument()
  })

  it('Save persists an inactive draft with the selected model', async () => {
    createRoutineMock.mockResolvedValueOnce({ ...saved, id: 'r-new' })
    renderNew()

    fireEvent.change(screen.getByLabelText('Name'), { target: { value: 'Draft recap' } })
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Keep this unpublished.' },
    })
    const model = await screen.findByTestId('routine-model-picker')
    fireEvent.change(model, { target: { value: 'orchestration' } })
    fireEvent.click(screen.getByTestId('routine-editor-save'))

    await waitFor(() => expect(createRoutineMock).toHaveBeenCalled())
    expect(createRoutineMock.mock.calls[0][0]).toBe('codey')
    expect(createRoutineMock.mock.calls[0][1]).toMatchObject({
      name: 'Draft recap',
      instruction: 'Keep this unpublished.',
      active: false,
      model: 'orchestration',
    })
  })

  it('armed toggle persists on an existing routine without requiring Save to be Active', async () => {
    updateRoutineMock.mockImplementation(async (_agent: string, _id: string, patch: Partial<Routine>) => ({
      ...saved,
      ...patch,
    }))
    renderExisting()

    const armed = screen.getByRole('switch', { name: 'Armed' })
    expect(armed).not.toBeChecked()
    fireEvent.click(armed)
    await waitFor(() =>
      expect(updateRoutineMock).toHaveBeenCalledWith('codey', 'r-1', { active: true }),
    )

    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Updated prompt.' },
    })
    const model = await screen.findByTestId('routine-model-picker')
    fireEvent.change(model, { target: { value: 'auxiliary' } })
    fireEvent.click(screen.getByTestId('routine-editor-save'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalledTimes(2))
    const savePatch = updateRoutineMock.mock.calls[1][2] as Partial<Routine>
    expect(savePatch).toMatchObject({
      instruction: 'Updated prompt.',
      model: 'auxiliary',
      active: true,
    })
  })

  it('Test shows a dry-run preview and does not fire a live run on an unsaved draft', async () => {
    renderNew()
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Preview this prompt.' },
    })
    fireEvent.click(screen.getByTestId('routine-editor-test'))

    const preview = await screen.findByTestId('routine-dry-run-preview')
    expect(preview).toHaveTextContent('Dry-run preview')
    expect(screen.getByTestId('routine-dry-run-prompt')).toHaveTextContent('Preview this prompt.')
    expect(screen.getByTestId('routine-dry-run-side-effects')).toHaveTextContent('none')
    expect(testRunRoutineMock).not.toHaveBeenCalled()
    expect(createRoutineMock).not.toHaveBeenCalled()
  })

  it('Test on a saved routine uses the dry-run endpoint and shows trigger + prompt', async () => {
    testRunRoutineMock.mockResolvedValueOnce({
      ...saved,
      dry_run: true,
      preview: {
        dry_run: true,
        side_effects: 'none',
        note: 'Dry-run preview. No messages sent, no PRs merged, instruction not executed.',
        trigger_summary: 'When a PR merges in owner/repo…',
        trigger_kind: 'github_pr_merged',
        trigger_match: {
          kind: 'github_pr_merged',
          summary: 'When a PR merges in owner/repo…',
          configured: true,
        },
        prompt: 'Summarize the merge.',
        model: 'orchestration',
        armed: false,
        would_run_if_triggered: false,
      },
    })
    renderExisting()
    fireEvent.click(screen.getByTestId('routine-editor-test'))
    const preview = await screen.findByTestId('routine-dry-run-preview')
    expect(testRunRoutineMock).toHaveBeenCalledWith('codey', 'r-1')
    expect(preview).toHaveTextContent('When a PR merges in owner/repo…')
    expect(screen.getByTestId('routine-dry-run-prompt')).toHaveTextContent('Summarize the merge.')
    expect(screen.getByTestId('routine-dry-run-model')).toHaveTextContent('orchestration')
  })

  it('armed toggle does not drop an unsaved instruction or model', async () => {
    updateRoutineMock.mockImplementation(async (_agent: string, _id: string, patch: Partial<Routine>) => ({
      ...saved,
      ...patch,
    }))
    renderExisting()
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Unsaved prompt.' },
    })
    const model = await screen.findByTestId('routine-model-picker')
    fireEvent.change(model, { target: { value: 'auxiliary' } })
    fireEvent.click(screen.getByRole('switch', { name: 'Armed' }))
    await waitFor(() =>
      expect(updateRoutineMock).toHaveBeenCalledWith('codey', 'r-1', { active: true }),
    )
    expect(screen.getByLabelText('Agent Instructions')).toHaveValue('Unsaved prompt.')
    expect(screen.getByTestId('routine-model-picker')).toHaveValue('auxiliary')

    fireEvent.click(screen.getByTestId('routine-editor-save'))
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalledTimes(2))
    expect(updateRoutineMock.mock.calls[1][2]).toMatchObject({
      instruction: 'Unsaved prompt.',
      model: 'auxiliary',
      active: true,
    })
  })

  it('Test previews the on-screen draft when it differs from the saved routine', async () => {
    testRunRoutineMock.mockResolvedValueOnce({
      ...saved,
      dry_run: true,
      preview: {
        dry_run: true,
        side_effects: 'none',
        note: 'Dry-run preview. No messages sent, no PRs merged, instruction not executed.',
        trigger_summary: 'When a PR merges in owner/repo…',
        trigger_kind: 'github_pr_merged',
        trigger_match: {
          kind: 'github_pr_merged',
          summary: 'When a PR merges in owner/repo…',
          configured: true,
        },
        prompt: 'Summarize the merge.',
        model: 'orchestration',
        armed: false,
        would_run_if_triggered: false,
      },
    })
    renderExisting()
    fireEvent.change(screen.getByLabelText('Agent Instructions'), {
      target: { value: 'Edited but not saved.' },
    })
    fireEvent.click(screen.getByTestId('routine-editor-test'))
    expect(await screen.findByTestId('routine-dry-run-prompt')).toHaveTextContent('Edited but not saved.')
    expect(testRunRoutineMock).toHaveBeenCalledWith('codey', 'r-1')
  })
})

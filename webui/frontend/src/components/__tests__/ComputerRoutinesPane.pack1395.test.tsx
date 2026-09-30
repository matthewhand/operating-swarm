import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ComputerRoutinesPane } from '../ComputerRoutinesPane'
import { RoutineEditorDialog } from '../RoutineEditorDialog'
import type { Routine } from '../../lib/routines'

const { fetchRoutinesMock, updateRoutineMock, exportRoutinesPackMock, downloadRoutinesPackMock } =
  vi.hoisted(() => ({
    fetchRoutinesMock: vi.fn(),
    updateRoutineMock: vi.fn(),
    exportRoutinesPackMock: vi.fn(),
    downloadRoutinesPackMock: vi.fn(),
  }))

vi.mock('../../lib/routines', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routines')>()
  return {
    ...actual,
    fetchRoutines: (...args: unknown[]) => fetchRoutinesMock(...args),
    updateRoutine: (...args: unknown[]) => updateRoutineMock(...args),
  }
})

vi.mock('../../lib/routinePack', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../lib/routinePack')>()
  return {
    ...actual,
    exportRoutinesPack: (...args: unknown[]) => exportRoutinesPackMock(...args),
    downloadRoutinesPack: (...args: unknown[]) => downloadRoutinesPackMock(...args),
  }
})

const seatRoutines: Routine[] = [
  {
    id: 'r-watch',
    name: 'Notify {{channel}}',
    instruction: 'Post updates for {{owner_repo}}.',
    active: false,
    trigger: {
      kind: 'github_event',
      event_type: 'issues.opened',
      owner_repo: '{{owner_repo}}',
    },
    history: [],
  },
  {
    id: 'r-notes',
    name: 'Ship notes',
    instruction: 'Summarize the merge.',
    active: true,
    trigger: {
      kind: 'github_pr_merged',
      owner_repo: 'acme/widgets',
      event: 'merged',
      actor: 'anyone',
    },
    history: [],
    when_to_run: 'When a PR merges in acme/widgets…',
  },
  {
    id: 'r-nightly',
    name: 'Nightly recap',
    instruction: 'Summarize the day.',
    active: false,
    trigger: { kind: 'interval', seconds: 86400 },
    history: [],
  },
]

function renderPane() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ComputerRoutinesPane agentId="codey" agentName="Codey" />
    </QueryClientProvider>,
  )
}

describe('ComputerRoutinesPane pack UI (#1395)', () => {
  beforeEach(() => {
    fetchRoutinesMock.mockReset().mockResolvedValue(seatRoutines)
    updateRoutineMock.mockReset()
    exportRoutinesPackMock.mockReset().mockResolvedValue({
      object: 'agent_routines_pack',
      kind: 'agent_routines_pack',
      schema: 1,
      routines: [],
      fill_ins: [
        { key: 'channel', label: 'Channel', required: true },
        { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
      ],
    })
    downloadRoutinesPackMock.mockReset()
  })

  it('shows pending-fill, enabled, and paused on the routines list', async () => {
    renderPane()
    expect(await screen.findByTestId('routine-list-status-r-watch')).toHaveTextContent('Pending fill')
    expect(screen.getByTestId('routine-list-status-r-notes')).toHaveTextContent('Enabled')
    expect(screen.getByTestId('routine-list-status-r-nightly')).toHaveTextContent('Paused')
    expect(screen.getByTestId('routine-list-status-r-watch')).toHaveAttribute('data-status', 'pending-fill')
    expect(screen.getByTestId('routine-list-status-r-notes')).toHaveAttribute('data-status', 'enabled')
  })

  it('previews required fill-ins from the pack pane', async () => {
    renderPane()
    await screen.findByText('Ship notes')
    fireEvent.click(screen.getByTestId('routine-pack-open'))
    expect(screen.getByTestId('routine-pack-pane')).toBeInTheDocument()
    expect(screen.getByTestId('routine-pack-export-preview-channel')).toHaveTextContent('Channel')
    expect(screen.getByTestId('routine-pack-export-preview-owner_repo')).toHaveTextContent(
      'GitHub owner/repo',
    )
    fireEvent.click(screen.getByTestId('routine-pack-export'))
    await waitFor(() => expect(exportRoutinesPackMock).toHaveBeenCalled())
    expect(downloadRoutinesPackMock).toHaveBeenCalled()
  })

  it('refuses to enable a pending-fill routine from the editor', async () => {
    renderPane()
    fireEvent.click(await screen.findByText('Notify {{channel}}'))
    expect(await screen.findByTestId('routine-editor-pending-fill')).toHaveTextContent(/Pending fill/)
    fireEvent.click(screen.getByRole('switch', { name: 'Armed' }))
    expect(await screen.findByTestId('computer-routines-error')).toHaveTextContent(
      'Complete required fill-ins before enabling: Channel, GitHub owner/repo.',
    )
    expect(updateRoutineMock).not.toHaveBeenCalled()
  })

  it('pauses an enabled routine when a save still has required fill-ins', async () => {
    updateRoutineMock.mockResolvedValue({
      ...seatRoutines[1],
      instruction: 'Post to {{channel}}',
      active: false,
    })
    renderPane()
    fireEvent.click(await screen.findByText('Ship notes'))
    const instruction = await screen.findByLabelText('Agent Instructions')
    fireEvent.change(instruction, { target: { value: 'Post to {{channel}}' } })
    fireEvent.blur(instruction)
    await waitFor(() => expect(updateRoutineMock).toHaveBeenCalled())
    expect(updateRoutineMock).toHaveBeenCalledWith(
      'codey',
      'r-notes',
      expect.objectContaining({ instruction: 'Post to {{channel}}', active: false }),
    )
    expect(await screen.findByTestId('computer-routines-error')).toHaveTextContent(
      'Complete required fill-ins before enabling: Channel.',
    )
  })

  it('shows pending-fill from API flags without treating a filled repo as missing', async () => {
    fetchRoutinesMock.mockResolvedValue([
      {
        ...seatRoutines[1],
        id: 'r-ready',
        name: 'Ship notes',
        active: true,
        enabled: true,
        pending_fill: false,
      },
      {
        id: 'r-pending',
        name: 'Issue solver',
        instruction: 'Fix it.',
        active: false,
        enabled: false,
        pending_fill: true,
        fill_in_keys: ['owner_repo', 'channel'],
        trigger: {
          kind: 'github_event',
          event_type: 'issues.opened',
          owner_repo: '{{FILL_IN}}',
        },
        history: [],
      },
    ])
    renderPane()
    expect(await screen.findByTestId('routine-list-status-r-ready')).toHaveTextContent('Enabled')
    expect(screen.getByTestId('routine-list-status-r-pending')).toHaveTextContent('Pending fill')
  })

  it('blocks enabling a paused pending-fill routine and still allows pausing an active one', async () => {
    const pending: Routine = {
      id: 'r-pending',
      name: 'Issue solver',
      instruction: 'Fix it.',
      active: false,
      enabled: false,
      pending_fill: true,
      fill_in_keys: ['owner_repo', 'channel'],
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: '{{FILL_IN}}',
      },
      history: [],
    }
    fetchRoutinesMock.mockResolvedValue([
      { ...seatRoutines[0], pending_fill: true, fill_in_keys: ['owner_repo'], active: true },
      pending,
    ])
    renderPane()
    fireEvent.click(await screen.findByRole('button', { name: /Issue solver/ }))
    expect(screen.getByTestId('routine-armed-switch')).toBeDisabled()
    expect(screen.getByTestId('routine-enable-gated')).toHaveTextContent(
      'Fill in GitHub owner/repo, Channel before enabling.',
    )
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    fireEvent.click(await screen.findByRole('button', { name: /Notify/ }))
    expect(screen.getByTestId('routine-armed-switch')).toBeEnabled()
    expect(screen.getByTestId('routine-armed-switch')).toBeChecked()
  })
})

describe('RoutineEditorDialog enable gate (#1395)', () => {
  it('disables Armed while a pending-fill routine is paused', () => {
    render(
      <RoutineEditorDialog
        open
        onClose={() => {}}
        initial={{
          id: 'r-pending',
          name: 'Issue solver',
          instruction: 'Fix {{owner_repo}}.',
          active: false,
          pending_fill: true,
          fill_in_keys: ['owner_repo'],
          trigger: {
            kind: 'github_event',
            event_type: 'issues.opened',
            owner_repo: '{{owner_repo}}',
          },
          history: [],
        }}
      />,
    )
    expect(screen.getByTestId('routine-armed-switch')).toBeDisabled()
    expect(screen.getByTestId('routine-enable-gated')).toHaveTextContent('GitHub owner/repo')
  })
})

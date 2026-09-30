import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import RoutinePackPicker from '../RoutinePackPicker'
import type { Routine } from '../../lib/routines'
import type { RoutinePack, RoutinePackImport } from '../../lib/routinePack'

const routines: Routine[] = [
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
    when_to_run: 'When an issue opens…',
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
]

const pack: RoutinePack = {
  object: 'agent_routines_pack',
  kind: 'agent_routines_pack',
  schema: 1,
  agent_id: 'codey',
  fill_ins: [
    { key: 'channel', label: 'Channel', required: true },
    { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
  ],
  routines: [
    {
      name: 'Notify {{channel}}',
      instruction: 'Post updates for {{owner_repo}}.',
      trigger: {
        kind: 'github_event',
        event_type: 'issues.opened',
        owner_repo: '{{owner_repo}}',
      },
    },
  ],
}

function importedResult(overrides: Partial<RoutinePackImport> = {}): RoutinePackImport {
  return {
    object: 'agent_routines_pack_import',
    agent_id: 'codey',
    pending_enable: true,
    created_count: 1,
    skipped: [],
    fill_ins_applied: [],
    fill_ins_remaining: [
      { key: 'channel', label: 'Channel', required: true },
      { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
    ],
    routines: [
      {
        id: 'r-imported',
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
    ],
    pack,
    ...overrides,
  }
}

describe('RoutinePackPicker (#1395)', () => {
  it('previews required fill-ins for the selected routines before export', () => {
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn()}
        enableRoutines={vi.fn()}
      />,
    )

    expect(screen.getByTestId('routine-pack-export-preview-channel')).toHaveTextContent('Channel')
    expect(screen.getByTestId('routine-pack-export-preview-owner_repo')).toHaveTextContent(
      'GitHub owner/repo',
    )

    fireEvent.click(screen.getByTestId('routine-pack-select-r-watch'))
    expect(screen.queryByTestId('routine-pack-export-preview-channel')).not.toBeInTheDocument()
    expect(screen.getByTestId('routine-pack-export-preview-owner_repo')).toHaveTextContent(
      'GitHub owner/repo',
    )
  })

  it('exports only the selected routines and reports pack fill-ins', async () => {
    const exportPack = vi.fn().mockResolvedValue(pack)
    const downloadPack = vi.fn()
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={exportPack}
        importPack={vi.fn()}
        enableRoutines={vi.fn()}
        downloadPack={downloadPack}
      />,
    )

    fireEvent.click(screen.getByTestId('routine-pack-select-r-notes'))
    fireEvent.click(screen.getByTestId('routine-pack-export'))

    await waitFor(() => expect(exportPack).toHaveBeenCalled())
    expect(exportPack).toHaveBeenCalledWith('codey', {
      routineIds: ['r-watch'],
      includePresets: false,
    })
    expect(downloadPack).toHaveBeenCalledWith(pack)
    expect(await screen.findByTestId('routine-pack-export-hint')).toHaveTextContent(
      /Required fill-ins: Channel, GitHub owner\/repo/,
    )
  })

  it('disables export until a routine or presets are selected', () => {
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn()}
        enableRoutines={vi.fn()}
      />,
    )
    fireEvent.click(screen.getByTestId('routine-pack-select-r-watch'))
    fireEvent.click(screen.getByTestId('routine-pack-select-r-notes'))
    expect(screen.getByTestId('routine-pack-export')).toBeDisabled()
    expect(screen.getByTestId('routine-pack-export-hint')).toHaveTextContent(/Select at least one routine/)
    expect(screen.getByTestId('routine-pack-export-preview-empty')).toHaveTextContent(
      /Select routines to preview/,
    )

    fireEvent.click(screen.getByTestId('routine-pack-include-presets'))
    expect(screen.getByTestId('routine-pack-export')).toBeEnabled()
  })

  it('shows a clear error and does not enable when fill-ins are incomplete', async () => {
    const enableRoutines = vi.fn()
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn().mockResolvedValue(importedResult())}
        enableRoutines={enableRoutines}
      />,
    )

    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))

    expect(await screen.findByTestId('routine-pack-fill-ins')).toBeInTheDocument()
    expect(screen.getByTestId('routine-pack-enable')).toBeEnabled()

    fireEvent.click(screen.getByTestId('routine-pack-enable'))
    expect(await screen.findByTestId('routine-pack-error')).toHaveTextContent(
      'Complete required fill-ins before enabling: Channel, GitHub owner/repo.',
    )
    expect(enableRoutines).not.toHaveBeenCalled()

    fireEvent.change(screen.getByTestId('routine-pack-fill-in-channel'), {
      target: { value: 'ops' },
    })
    fireEvent.click(screen.getByTestId('routine-pack-enable'))
    expect(await screen.findByTestId('routine-pack-error')).toHaveTextContent(
      'Complete required fill-ins before enabling: GitHub owner/repo.',
    )
    expect(enableRoutines).not.toHaveBeenCalled()
  })

  it('enables imported routines only after every required fill-in is set', async () => {
    const enabled = {
      id: 'r-imported',
      name: 'Notify ops',
      instruction: 'Post updates for acme/widgets.',
      active: true,
      trigger: {
        kind: 'github_event' as const,
        event_type: 'issues.opened',
        owner_repo: 'acme/widgets',
      },
      history: [],
    }
    const enableRoutines = vi.fn().mockResolvedValue([enabled])
    const onImported = vi.fn()
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn().mockResolvedValue(importedResult())}
        enableRoutines={enableRoutines}
        onImported={onImported}
      />,
    )

    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    await screen.findByTestId('routine-pack-fill-in-channel')

    fireEvent.change(screen.getByTestId('routine-pack-fill-in-channel'), {
      target: { value: 'ops' },
    })
    fireEvent.change(screen.getByTestId('routine-pack-fill-in-owner_repo'), {
      target: { value: 'acme/widgets' },
    })
    fireEvent.click(screen.getByTestId('routine-pack-enable'))

    await waitFor(() => expect(enableRoutines).toHaveBeenCalled())
    expect(enableRoutines).toHaveBeenCalledWith(
      'codey',
      expect.arrayContaining([expect.objectContaining({ id: 'r-imported' })]),
      { channel: 'ops', owner_repo: 'acme/widgets' },
    )
    expect(await screen.findByTestId('routine-pack-enable-result')).toHaveTextContent('Enabled 1 routine.')
    expect(screen.queryByTestId('routine-pack-fill-ins')).not.toBeInTheDocument()
    expect(screen.queryByTestId('routine-pack-error')).not.toBeInTheDocument()
  })

  it('imports without fill-in values and drops them when the pack JSON changes', async () => {
    const importPack = vi.fn().mockResolvedValue(importedResult())
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={importPack}
        enableRoutines={vi.fn()}
      />,
    )

    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    const channel = await screen.findByTestId('routine-pack-fill-in-channel')
    fireEvent.change(channel, { target: { value: 'ops' } })

    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: `${JSON.stringify(pack)} ` },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    expect(await screen.findByTestId('routine-pack-fill-in-channel')).toHaveValue('')
    expect(importPack).toHaveBeenCalledTimes(2)
    expect(importPack.mock.calls[0]).toEqual(['codey', pack])
    expect(importPack.mock.calls[1]).toEqual(['codey', pack])
  })

  it('does not enable a skipped duplicate', async () => {
    const enableRoutines = vi.fn()
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn().mockResolvedValue(
          importedResult({
            created_count: 0,
            routines: [
              {
                id: 'r-live',
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
              },
            ],
            skipped: [{ name: 'Ship notes', existing_routine_id: 'r-live', reason: 'duplicate' }],
            fill_ins_remaining: [],
          }),
        )}
        enableRoutines={enableRoutines}
      />,
    )

    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    expect(await screen.findByTestId('routine-pack-import-result')).toHaveTextContent(/Skipped 1 duplicate/)
    expect(screen.queryByTestId('routine-pack-fill-ins')).not.toBeInTheDocument()
    expect(enableRoutines).not.toHaveBeenCalled()
  })

  it('previews fill-ins that export will require and shows the slug', () => {
    const withSlug = routines.map((row) => (row.id === 'r-notes' ? { ...row, slug: 'ship-notes' } : row))
    render(
      <RoutinePackPicker agentId="codey" routines={withSlug} exportPack={vi.fn()} importPack={vi.fn()} />,
    )
    expect(screen.getByTestId('routine-pack-slug-r-notes')).toHaveTextContent('ship-notes')
    expect(screen.getByTestId('routine-pack-fill-in-preview')).toHaveTextContent('{{FILL_IN}}')
    expect(screen.getByTestId('routine-pack-fill-in-preview')).toHaveTextContent('GitHub owner/repo')
  })

  it('shows a clear error when enable is clicked before fill-ins are complete', async () => {
    const enableRoutines = vi.fn()
    const withChannel = importedResult({
      fill_ins_remaining: [
        { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
        { key: 'channel', label: 'Channel', required: true },
      ],
    })
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={vi.fn().mockResolvedValue(withChannel)}
        enableRoutines={enableRoutines}
      />,
    )
    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    expect(await screen.findByTestId('routine-pack-fill-in-channel')).toBeInTheDocument()
    fireEvent.click(screen.getByTestId('routine-pack-enable'))
    expect(screen.getByTestId('routine-pack-error')).toHaveTextContent(
      'Complete required fill-ins before enabling: Channel, GitHub owner/repo.',
    )
    expect(enableRoutines).not.toHaveBeenCalled()
  })

  it('does not fill or enable a skipped duplicate', async () => {
    const created = importedResult().routines[0]
    const existing: Routine = {
      ...routines[1],
      id: 'r-existing',
      active: false,
    }
    const importPack = vi.fn().mockResolvedValue(
      importedResult({
        routines: [created, existing],
        skipped: [{ name: existing.name, existing_routine_id: existing.id, reason: 'duplicate' }],
      }),
    )
    const enableRoutines = vi.fn().mockResolvedValue([
      {
        ...created,
        active: true,
        trigger: { ...created.trigger, owner_repo: 'acme/widgets' },
      },
    ])
    render(
      <RoutinePackPicker
        agentId="codey"
        routines={routines}
        exportPack={vi.fn()}
        importPack={importPack}
        enableRoutines={enableRoutines}
      />,
    )
    fireEvent.change(screen.getByTestId('routine-pack-import-json'), {
      target: { value: JSON.stringify(pack) },
    })
    fireEvent.click(screen.getByTestId('routine-pack-import'))
    expect(await screen.findByTestId('routine-pack-fill-in-owner_repo')).toBeInTheDocument()
    fireEvent.change(screen.getByTestId('routine-pack-fill-in-channel'), {
      target: { value: 'ops' },
    })
    fireEvent.change(screen.getByTestId('routine-pack-fill-in-owner_repo'), {
      target: { value: 'acme/widgets' },
    })
    fireEvent.click(screen.getByTestId('routine-pack-enable'))
    await waitFor(() => expect(enableRoutines).toHaveBeenCalled())
    const enabledRows = enableRoutines.mock.calls[0][1] as Routine[]
    expect(enabledRows.map((row) => row.id)).toEqual(['r-imported'])
  })

  it('selects routines that arrive after the picker mounts', () => {
    const { rerender } = render(
      <RoutinePackPicker agentId="codey" routines={[]} exportPack={vi.fn()} importPack={vi.fn()} />,
    )
    expect(screen.getByTestId('routine-pack-export')).toBeDisabled()
    rerender(
      <RoutinePackPicker agentId="codey" routines={routines} exportPack={vi.fn()} importPack={vi.fn()} />,
    )
    expect(screen.getByTestId('routine-pack-select-r-notes')).toBeChecked()
    expect(screen.getByTestId('routine-pack-export')).toBeEnabled()
  })
})

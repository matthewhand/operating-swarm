import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  FILL_IN_SCAN_RE,
  applyFillIns,
  applyImportedRoutineFillIns,
  canExportRoutinesPack,
  enableBlockedReason,
  enableImportedRoutines,
  exportBlockedReason,
  exportRoutinesPack,
  filledMapping,
  importRoutinesPack,
  incompleteFillInMessage,
  parsePackJson,
  previewRequiredFillIns,
  fillInsAfterImport,
  remainingFillIns,
  routineEnableGate,
  routineListStatus,
  routinePackStatus,
  routinePackStatusLabel,
  routinesImportPath,
  routinesPackPath,
  routinesPendingEnable,
  scanFillInKeys,
} from '../routinePack'
import type { Routine } from '../routines'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

const pack = {
  object: 'agent_routines_pack',
  kind: 'agent_routines_pack',
  schema: 1,
  fill_ins: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
  routines: [
    {
      name: 'GitHub Issue Solver (Issue → PR)',
      instruction: 'Investigate the issue in {{owner_repo}}.',
      trigger: {
        kind: 'github_event' as const,
        event_type: 'issues.opened',
        owner_repo: '{{owner_repo}}',
      },
    },
  ],
}

const pendingRoutine: Routine = {
  id: 'r-imported',
  name: 'Notify {{channel}}',
  instruction: 'Investigate the issue in {{owner_repo}}.',
  active: false,
  trigger: {
    kind: 'github_event',
    event_type: 'issues.opened',
    owner_repo: '{{owner_repo}}',
  },
  history: [],
}

describe('routine pack helpers (#1395)', () => {
  it('blocks export until a routine is selected or presets are included', () => {
    expect(canExportRoutinesPack([])).toBe(false)
    expect(exportBlockedReason([])).toMatch(/Select at least one routine/)
    expect(canExportRoutinesPack(['r-1'])).toBe(true)
    expect(canExportRoutinesPack([], true)).toBe(true)
    expect(exportBlockedReason(['r-1'])).toBeNull()
  })

  it('parses a wrapped pack object and rejects empty or invalid JSON', () => {
    expect(parsePackJson(JSON.stringify({ pack }))).toEqual(pack)
    expect(parsePackJson(JSON.stringify(pack))).toEqual(pack)
    expect(() => parsePackJson('')).toThrow(/Paste a routines pack/)
    expect(() => parsePackJson('{')).toThrow(/not valid JSON/)
  })

  it('substitutes fill-in tokens even after a shared global scan advanced lastIndex', () => {
    FILL_IN_SCAN_RE.lastIndex = 40
    const filled = applyFillIns('Watch {{channel}} in {{owner_repo}}', {
      channel: 'ops',
      owner_repo: 'acme/widgets',
    })
    expect(filled).toBe('Watch ops in acme/widgets')
    expect(applyFillIns(pack.routines[0], { owner_repo: 'acme/widgets' }).trigger.owner_repo).toBe(
      'acme/widgets',
    )
    expect(scanFillInKeys(pack.routines[0])).toEqual(['owner_repo'])
    expect(remainingFillIns(pack.routines)).toEqual([
      { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
    ])
    expect(filledMapping({ owner_repo: '  acme/widgets  ', cron: '' })).toEqual({
      owner_repo: 'acme/widgets',
    })
  })

  it('previews required fill-ins, including an empty GitHub owner/repo', () => {
    expect(
      previewRequiredFillIns([
        {
          name: 'Notify {{channel}}',
          instruction: 'Post the recap.',
          trigger: {
            kind: 'github_pr_merged',
            owner_repo: '',
            event: 'merged',
            actor: 'anyone',
          },
        },
      ]),
    ).toEqual([
      { key: 'channel', label: 'Channel', required: true },
      { key: 'owner_repo', label: 'GitHub owner/repo', required: true },
    ])
    expect(
      previewRequiredFillIns([
        {
          name: 'Ship notes',
          instruction: 'Summarize the merge.',
          trigger: {
            kind: 'github_pr_merged',
            owner_repo: 'acme/widgets',
            event: 'merged',
            actor: 'anyone',
          },
        },
      ]).map((slot) => slot.key),
    ).toEqual(['owner_repo'])
  })

  it('previews concrete repo and channel ids as required fill-ins', () => {
    const rows: Routine[] = [
      {
        id: 'r-notes',
        name: 'Ship notes',
        instruction: 'Summarize acme/widgets.',
        active: true,
        trigger: {
          kind: 'github_pr_merged',
          owner_repo: 'acme/widgets',
          event: 'merged',
          actor: 'anyone',
          channel: 'C0123ABCDEF',
        } as Routine['trigger'],
        history: [],
      },
    ]
    expect(previewRequiredFillIns(rows).map((slot) => slot.key)).toEqual(['owner_repo', 'channel'])
    const emptyRepo: Routine[] = [
      {
        ...rows[0],
        id: 'r-new',
        trigger: {
          kind: 'github_pr_merged',
          owner_repo: '',
          event: 'merged',
          actor: 'anyone',
        },
      },
    ]
    expect(previewRequiredFillIns(emptyRepo).map((slot) => slot.key)).toEqual(['owner_repo'])
    const split = previewRequiredFillIns([
      {
        ...rows[0],
        trigger: {
          kind: 'github_event',
          event_type: 'issues.opened',
          owner: 'acme',
          repo: 'widgets',
        } as unknown as Routine['trigger'],
      },
    ])
    expect(split.map((slot) => slot.key)).toEqual(['owner_repo'])
    expect(
      previewRequiredFillIns([
        {
          ...rows[0],
          trigger: { kind: 'interval', seconds: 3600 },
        },
      ]),
    ).toEqual([])
    const placeholder = applyFillIns(
      { owner_repo: '{{FILL_IN}}', channel: '{{FILL_IN}}', note: 'see {{owner_repo}}' },
      { owner_repo: 'acme/widgets', channel: 'C0123ABCDEF' },
    )
    expect(placeholder).toEqual({
      owner_repo: 'acme/widgets',
      channel: 'C0123ABCDEF',
      note: 'see acme/widgets',
    })
    expect(
      applyFillIns(
        { owner_repo: 'see {{FILL_IN}}', channel: 'room {{FILL_IN}}' },
        { owner_repo: 'acme/widgets', channel: 'C0123ABCDEF' },
      ),
    ).toEqual({
      owner_repo: 'see acme/widgets',
      channel: 'room C0123ABCDEF',
    })
  })

  it('labels pending-fill, enabled, and paused separately', () => {
    expect(routineListStatus(pendingRoutine)).toBe('pending-fill')
    expect(
      routineListStatus({
        ...pendingRoutine,
        name: 'Ship notes',
        instruction: 'Summarize the merge.',
        active: true,
        trigger: {
          kind: 'github_pr_merged',
          owner_repo: 'acme/widgets',
          event: 'merged',
          actor: 'anyone',
        },
      }),
    ).toBe('enabled')
    expect(
      routineListStatus({
        ...pendingRoutine,
        name: 'Nightly recap',
        instruction: 'Summarize the day.',
        active: false,
        trigger: { kind: 'interval', seconds: 86400 },
      }),
    ).toBe('paused')
    expect(routinePackStatus({ active: false, pending_fill: true })).toBe('pending-fill')
    expect(routinePackStatusLabel('pending-fill')).toBe('Pending fill')
    expect(routinePackStatus({ active: true, enabled: true, pending_fill: false })).toBe('enabled')
    expect(routinePackStatusLabel('enabled')).toBe('Enabled')
    expect(routinePackStatus({ active: false })).toBe('paused')
    expect(
      routinePackStatus({
        active: true,
        name: 'Notes',
        instruction: 'Use {{owner_repo}}.',
        trigger: { kind: 'interval', seconds: 60 },
      }),
    ).toBe('pending-fill')
    expect(routineEnableGate({ active: false, pending_fill: true, fill_in_keys: ['owner_repo', 'channel'] })).toEqual({
      blocked: true,
      message: 'Fill in GitHub owner/repo, Channel before enabling.',
    })
    expect(routineEnableGate({ active: true, pending_fill: true, fill_in_keys: ['channel'] }).blocked).toBe(false)
    expect(routineEnableGate({ active: true, pending_fill: false }).message).toBeNull()
    expect(
      routinesPendingEnable({
        routines: [
          { id: 'r-new', name: 'New', instruction: '', active: false, trigger: { kind: 'interval', seconds: 60 }, history: [] },
          { id: 'r-old', name: 'Old', instruction: '', active: true, trigger: { kind: 'interval', seconds: 60 }, history: [] },
        ],
        skipped: [{ name: 'Old', existing_routine_id: 'r-old', reason: 'duplicate' }],
      }).map((row) => row.id),
    ).toEqual(['r-new'])
    expect(
      fillInsAfterImport({
        object: 'agent_routines_pack_import',
        agent_id: 'codey',
        pending_enable: true,
        created_count: 0,
        fill_ins_applied: [],
        fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
        routines: [
          { id: 'r-old', name: 'Old', instruction: 'Use {{owner_repo}}.', active: true, trigger: { kind: 'interval', seconds: 60 }, history: [] },
        ],
        skipped: [{ name: 'Old', existing_routine_id: 'r-old', reason: 'duplicate' }],
      }),
    ).toEqual([])
  })

  it('treats an underscore fill-in key as required, matching the server scan', () => {
    expect(
      remainingFillIns([
        {
          name: 'Notify {{_channel}}',
          instruction: 'Post the recap.',
          trigger: { kind: 'interval', seconds: 3600 },
        },
      ]),
    ).toEqual([{ key: '_channel', label: ' channel', required: true }])
  })

  it('enables only inactive rows this import created', () => {
    const created = { ...pendingRoutine, id: 'r-new' }
    const existing = {
      ...pendingRoutine,
      id: 'r-live',
      name: 'Ship notes',
      instruction: 'Summarize the merge.',
      active: true,
      trigger: {
        kind: 'github_pr_merged' as const,
        owner_repo: 'acme/widgets',
        event: 'merged' as const,
        actor: 'anyone' as const,
      },
    }
    expect(
      routinesPendingEnable({
        routines: [created, existing],
        skipped: [{ name: 'Ship notes', existing_routine_id: 'r-live', reason: 'duplicate' }],
      }).map((row) => row.id),
    ).toEqual(['r-new'])
  })

  it('blocks enable while required fill-ins are incomplete', () => {
    expect(enableBlockedReason([pendingRoutine], {})).toBe(
      'Complete required fill-ins before enabling: Channel, GitHub owner/repo.',
    )
    expect(enableBlockedReason([pendingRoutine], { channel: 'ops' })).toBe(
      incompleteFillInMessage([{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }]),
    )
    expect(
      enableBlockedReason([pendingRoutine], { channel: 'ops', owner_repo: 'acme/widgets' }),
    ).toBeNull()
  })
})

describe('routine pack API client (#1395)', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('posts selected ids and presets to the pack endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(pack))
    vi.stubGlobal('fetch', fetchMock)

    const exported = await exportRoutinesPack('codey', {
      routineIds: ['r-1', 'r-2'],
      includePresets: true,
    })
    expect(exported.kind).toBe('agent_routines_pack')
    expect(fetchMock.mock.calls[0][0]).toBe(routinesPackPath('codey'))
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))
    expect(body.routine_ids).toEqual(['r-1', 'r-2'])
    expect(body.presets).toBe(1)
  })

  it('imports a pack with fill-ins and applies leftovers via PATCH without enabling', async () => {
    const importedRow: Routine = {
      ...pendingRoutine,
      name: 'GitHub Issue Solver (Issue → PR)',
      instruction: 'Investigate the issue in {{owner_repo}}.',
    }
    const filledRow = {
      ...importedRow,
      instruction: 'Investigate the issue in acme/widgets.',
      trigger: { ...importedRow.trigger, owner_repo: 'acme/widgets' },
    }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          object: 'agent_routines_pack_import',
          agent_id: 'writer',
          pending_enable: true,
          routines: [importedRow],
          created_count: 1,
          skipped: [],
          fill_ins_applied: [],
          fill_ins_remaining: [{ key: 'owner_repo', label: 'GitHub owner/repo', required: true }],
        }),
      )
      .mockResolvedValueOnce(jsonResponse(filledRow))
    vi.stubGlobal('fetch', fetchMock)

    const imported = await importRoutinesPack('writer', pack)
    expect(imported.pending_enable).toBe(true)
    expect(imported.fill_ins_remaining[0].key).toBe('owner_repo')
    expect(fetchMock.mock.calls[0][0]).toBe(routinesImportPath('writer'))

    const applied = await applyImportedRoutineFillIns('writer', imported.routines, {
      owner_repo: 'acme/widgets',
    })
    expect(applied[0].trigger).toMatchObject({ owner_repo: 'acme/widgets' })
    const patchInit = fetchMock.mock.calls[1][1] as RequestInit
    expect(fetchMock.mock.calls[1][0]).toMatch(/routines\/r-imported/)
    expect(patchInit.method).toBe('PATCH')
    const patch = JSON.parse(String(patchInit.body))
    expect(patch).toMatchObject({ trigger: { owner_repo: 'acme/widgets' } })
    expect(patch.active).toBeUndefined()
  })

  it('does not PATCH when enable is incomplete, and sets active after a complete fill', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({
        ...pendingRoutine,
        name: 'Notify ops',
        instruction: 'Investigate the issue in acme/widgets.',
        active: true,
        trigger: { ...pendingRoutine.trigger, owner_repo: 'acme/widgets' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await expect(enableImportedRoutines('codey', [pendingRoutine], { channel: 'ops' })).rejects.toThrow(
      /Complete required fill-ins before enabling: GitHub owner\/repo/,
    )
    expect(fetchMock).not.toHaveBeenCalled()

    const enabled = await enableImportedRoutines('codey', [pendingRoutine], {
      channel: 'ops',
      owner_repo: 'acme/widgets',
    })
    expect(enabled[0].active).toBe(true)
    const patch = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body))
    expect(patch).toMatchObject({
      name: 'Notify ops',
      instruction: 'Investigate the issue in acme/widgets.',
      active: true,
      trigger: { owner_repo: 'acme/widgets' },
    })
  })

  it('reports a partial enable when a later save fails', async () => {
    const second: Routine = { ...pendingRoutine, id: 'r-second', name: 'Second {{channel}}' }
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ...pendingRoutine, active: true, name: 'Notify ops' }))
      .mockResolvedValueOnce(jsonResponse({ error: 'nope' }, 500))
    vi.stubGlobal('fetch', fetchMock)

    await expect(
      enableImportedRoutines('codey', [pendingRoutine, second], {
        channel: 'ops',
        owner_repo: 'acme/widgets',
      }),
    ).rejects.toThrow(/Enabled 1 of 2 routines before a save failed/)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

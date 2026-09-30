import { describe, expect, it } from 'vitest'
import {
  formatDurationMs,
  formatRoutineHistoryTime,
  mergeRoutineSave,
  previewRoutineDryRun,
  resolveRoutinePreview,
  routineDraftWrite,
  routineModelOptionIds,
  triggerSummary,
  defaultTrigger,
  ROUTINE_TRIGGER_CRON,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  ROUTINE_TRIGGER_INTERVAL,
  ROUTINE_TRIGGER_MAILBOX_MESSAGE,
  type Routine,
} from '../routines'

describe('triggerSummary', () => {
  it('summarizes a GitHub PR-merge trigger', () => {
    expect(
      triggerSummary({
        kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
        owner_repo: 'owner/repo',
        event: 'merged',
        actor: 'anyone',
      }),
    ).toBe('When a PR merges in owner/repo…')
    expect(triggerSummary(defaultTrigger())).toBe('When a PR merges in a GitHub repo…')
  })

  it('summarizes interval, cron, and mailbox triggers', () => {
    expect(triggerSummary({ kind: ROUTINE_TRIGGER_INTERVAL, seconds: 3600 })).toBe('Every 1 hour…')
    expect(triggerSummary({ kind: ROUTINE_TRIGGER_CRON, expression: '0 3 * * *' })).toBe(
      'Cron 0 3 * * *…',
    )
    expect(
      triggerSummary({
        kind: ROUTINE_TRIGGER_MAILBOX_MESSAGE,
        sender: 'support',
        pattern: 'prove',
      }),
    ).toBe('When mailbox from support matches prove…')
  })
})

describe('previewRoutineDryRun (#1405)', () => {
  it('previews trigger match + prompt without implying live side effects', () => {
    const preview = previewRoutineDryRun({
      instruction: 'Write the merge recap.',
      active: false,
      model: 'orchestration',
      trigger: {
        kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
        owner_repo: 'owner/repo',
        event: 'merged',
        actor: 'anyone',
      },
    })
    expect(preview.dry_run).toBe(true)
    expect(preview.side_effects).toBe('none')
    expect(preview.prompt).toBe('Write the merge recap.')
    expect(preview.model).toBe('orchestration')
    expect(preview.armed).toBe(false)
    expect(preview.trigger_summary).toContain('owner/repo')
    expect(preview.note).toMatch(/No messages sent/)
  })
})

describe('mergeRoutineSave (#1405)', () => {
  it('keeps unsaved instruction and model when a partial save returns', () => {
    const current = {
      id: 'r-1',
      name: 'Local name',
      instruction: 'Local prompt',
      active: false,
      model: 'auxiliary',
      trigger: defaultTrigger(),
      history: [],
    } as Routine
    const updated = {
      ...current,
      name: 'Server name',
      instruction: 'Server prompt',
      model: '',
      active: true,
    }
    const merged = mergeRoutineSave(current, updated, { name: 'Server name' })
    expect(merged.name).toBe('Server name')
    expect(merged.instruction).toBe('Local prompt')
    expect(merged.model).toBe('auxiliary')
    expect(merged.active).toBe(false)
  })
})

describe('resolveRoutinePreview (#1405)', () => {
  it('shows the on-screen draft instead of the saved prompt', () => {
    const saved = {
      id: 'r-1',
      name: 'Ship notes',
      instruction: 'Saved prompt',
      active: false,
      model: 'orchestration',
      trigger: {
        kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
        owner_repo: 'owner/repo',
        event: 'merged',
        actor: 'anyone',
      },
      history: [],
    } as Routine
    const preview = resolveRoutinePreview(
      { ...saved, instruction: 'On screen', model: 'auxiliary' },
      { ...saved, preview: previewRoutineDryRun(saved) },
    )
    expect(preview.prompt).toBe('On screen')
    expect(preview.model).toBe('auxiliary')
    expect(preview.dry_run).toBe(true)
    expect(preview.side_effects).toBe('none')
    expect(preview.trigger_summary).toContain('owner/repo')
  })
})

describe('routineModelOptionIds (#1405)', () => {
  it('lists profile ids and keeps a stored value that is not a profile', () => {
    const ids = routineModelOptionIds(
      [
        { id: 'orchestration', model: 'gpt-4o-mini' },
        { id: 'auxiliary', model: 'gpt-4o-mini' },
      ],
      'custom-seat',
    )
    expect(ids).toEqual(['custom-seat', 'orchestration', 'auxiliary'])
    expect(ids).not.toContain('gpt-4o-mini')
  })
})

describe('routineDraftWrite (#1405)', () => {
  it('includes inactive + model so Save does not require Active', () => {
    const write = routineDraftWrite({
      id: 'r-1',
      name: 'Draft',
      instruction: 'Keep it.',
      active: false,
      model: 'auxiliary',
      trigger: defaultTrigger(),
      history: [],
    } as Routine)
    expect(write).toMatchObject({
      name: 'Draft',
      instruction: 'Keep it.',
      active: false,
      model: 'auxiliary',
    })
  })
})

describe('formatDurationMs', () => {
  it('formats milliseconds and seconds', () => {
    expect(formatDurationMs(12)).toBe('12ms')
    expect(formatDurationMs(1500)).toBe('1.5s')
  })
})

describe('formatRoutineHistoryTime', () => {
  const now = Date.parse('2026-09-05T21:34:00.000Z')

  it('uses Just now, N min ago, and Today at', () => {
    expect(formatRoutineHistoryTime(now - 12_000, now, 'UTC')).toBe('Just now')
    expect(formatRoutineHistoryTime(now - 32 * 60 * 1000, now, 'UTC')).toBe('32 min ago')
    expect(formatRoutineHistoryTime(Date.parse('2026-09-05T07:34:00.000Z'), now, 'UTC')).toBe(
      'Today at 7:34 AM',
    )
  })
})

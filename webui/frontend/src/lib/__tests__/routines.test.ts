import { describe, expect, it } from 'vitest'
import {
  formatDurationMs,
  formatRoutineHistoryTime,
  triggerSummary,
  defaultTrigger,
  ROUTINE_TRIGGER_CRON,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  ROUTINE_TRIGGER_INTERVAL,
  ROUTINE_TRIGGER_MAILBOX_MESSAGE,
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

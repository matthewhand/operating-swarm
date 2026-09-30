import { describe, expect, it } from 'vitest'
import {
  ROUTINE_TRIGGER_CRON,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  ROUTINE_TRIGGER_INTERVAL,
  TOOL_OPEN_PULL_REQUEST,
  defaultToolsForTrigger,
  effectiveRoutineTools,
  hasOpenPullRequestTool,
  isGithubIssueTrigger,
  toggleOpenPullRequestTool,
  type RoutineTrigger,
} from '../routines'

const issueTrigger: RoutineTrigger = {
  kind: ROUTINE_TRIGGER_GITHUB_EVENT,
  event_type: 'issues.opened',
  owner_repo: 'owner/repo',
}

const prTrigger: RoutineTrigger = {
  kind: ROUTINE_TRIGGER_GITHUB_EVENT,
  event_type: 'pull_request.opened',
  owner_repo: 'owner/repo',
}

describe('routine Open PR tool defaults (#1403)', () => {
  it('defaults on for GitHub-issue triggers', () => {
    expect(isGithubIssueTrigger(issueTrigger)).toBe(true)
    expect(defaultToolsForTrigger(issueTrigger)).toEqual([TOOL_OPEN_PULL_REQUEST])
    expect(
      effectiveRoutineTools({ trigger: issueTrigger, tools_explicit: false }, issueTrigger),
    ).toEqual([TOOL_OPEN_PULL_REQUEST])
  })

  it('defaults off for non-issue triggers', () => {
    const others: RoutineTrigger[] = [
      { kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED, owner_repo: 'owner/repo', event: 'merged', actor: 'anyone' },
      prTrigger,
      { kind: ROUTINE_TRIGGER_INTERVAL, seconds: 3600 },
      { kind: ROUTINE_TRIGGER_CRON, expression: '0 3 * * *' },
    ]
    for (const trigger of others) {
      expect(isGithubIssueTrigger(trigger)).toBe(false)
      expect(defaultToolsForTrigger(trigger)).toEqual([])
    }
  })

  it('keeps an explicit removal after trigger changes', () => {
    const removed = effectiveRoutineTools(
      { trigger: issueTrigger, tools: [], tools_explicit: true },
      issueTrigger,
    )
    expect(removed).toEqual([])
    expect(hasOpenPullRequestTool(removed)).toBe(false)
  })

  it('toggles Open Pull Request without dropping other tools', () => {
    expect(toggleOpenPullRequestTool([], true)).toEqual([TOOL_OPEN_PULL_REQUEST])
    expect(toggleOpenPullRequestTool([TOOL_OPEN_PULL_REQUEST], false)).toEqual([])
  })
})

import { describe, expect, it } from 'vitest'
import {
  GITHUB_COMPOSER_EVENT_ASSIGNED,
  GITHUB_COMPOSER_EVENT_COMMENT,
  GITHUB_COMPOSER_EVENT_MERGED,
  GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED,
  GITHUB_EVENT_ISSUE_ASSIGNED,
  GITHUB_EVENT_ISSUE_COMMENT,
  GITHUB_OBJECT_ISSUE,
  GITHUB_OBJECT_PULL_REQUEST,
  deserializeGithubTrigger,
  githubTriggerSaveError,
  serializeGithubTrigger,
  unsupportedGithubCombination,
} from '../githubTriggerComposer'
import {
  ROUTINE_ACTOR_ANYONE,
  ROUTINE_EVENT_MERGED,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  type GithubEventTrigger,
} from '../routines'

function draft(partial: Parameters<typeof serializeGithubTrigger>[0]) {
  return serializeGithubTrigger(partial)
}

const baseDraft = {
  actor: ROUTINE_ACTOR_ANYONE,
  ownerRepo: 'owner/repo',
  labels: [] as string[],
  branch: '',
  excludeAuthors: [] as string[],
}

describe('github trigger composer serialize/deserialize (#1402)', () => {
  it('round-trips an issue comment onto github_event', () => {
    const trigger = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
      objectKind: GITHUB_OBJECT_ISSUE,
    })
    expect(trigger).toEqual({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: GITHUB_EVENT_ISSUE_COMMENT,
      owner_repo: 'owner/repo',
      filters: { object_kind: GITHUB_OBJECT_ISSUE },
    })
    expect(deserializeGithubTrigger(trigger)).toMatchObject({
      eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
      objectKind: GITHUB_OBJECT_ISSUE,
      ownerRepo: 'owner/repo',
      actor: ROUTINE_ACTOR_ANYONE,
    })
  })

  it('round-trips an issue assigned onto github_event', () => {
    const trigger = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_ASSIGNED,
      objectKind: GITHUB_OBJECT_ISSUE,
      actor: 'mona',
    })
    expect(trigger).toEqual({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: GITHUB_EVENT_ISSUE_ASSIGNED,
      owner_repo: 'owner/repo',
      filters: { object_kind: GITHUB_OBJECT_ISSUE, actor: 'mona' },
    })
    expect(deserializeGithubTrigger(trigger)).toMatchObject({
      eventKind: GITHUB_COMPOSER_EVENT_ASSIGNED,
      objectKind: GITHUB_OBJECT_ISSUE,
      actor: 'mona',
      ownerRepo: 'owner/repo',
    })
  })

  it('round-trips a PR comment onto github_event with object_kind pull_request', () => {
    const trigger = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
      objectKind: GITHUB_OBJECT_PULL_REQUEST,
    })
    expect(trigger).toEqual({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: GITHUB_EVENT_ISSUE_COMMENT,
      owner_repo: 'owner/repo',
      filters: { object_kind: GITHUB_OBJECT_PULL_REQUEST },
    })
    expect(deserializeGithubTrigger(trigger)).toMatchObject({
      eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
      objectKind: GITHUB_OBJECT_PULL_REQUEST,
      ownerRepo: 'owner/repo',
    })
  })

  it('preserves labels, branch, and exclude_authors without loss', () => {
    const stored: GithubEventTrigger = {
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      event_type: GITHUB_EVENT_ISSUE_COMMENT,
      owner_repo: 'acme/widgets',
      filters: {
        object_kind: GITHUB_OBJECT_ISSUE,
        labels: ['bug', 'triage'],
        branch: 'main',
        exclude_authors: ['open-swarm[bot]'],
        actor: 'octocat',
      },
    }
    const again = serializeGithubTrigger(deserializeGithubTrigger(stored))
    expect(again).toEqual(stored)
  })

  it('serializes merged + pull request onto github_pr_merged', () => {
    const trigger = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_MERGED,
      objectKind: GITHUB_OBJECT_PULL_REQUEST,
      actor: 'anyone',
    })
    expect(trigger).toEqual({
      kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
      owner_repo: 'owner/repo',
      event: ROUTINE_EVENT_MERGED,
      actor: ROUTINE_ACTOR_ANYONE,
    })
    expect(deserializeGithubTrigger(trigger).eventKind).toBe(GITHUB_COMPOSER_EVENT_MERGED)
  })
})

describe('github trigger composer unsupported combinations (#1402)', () => {
  it('blocks merged on an issue before Save', () => {
    const message = unsupportedGithubCombination(GITHUB_COMPOSER_EVENT_MERGED, GITHUB_OBJECT_ISSUE)
    expect(message).toMatch(/pull requests only/i)
    expect(() =>
      draft({
        ...baseDraft,
        eventKind: GITHUB_COMPOSER_EVENT_MERGED,
        objectKind: GITHUB_OBJECT_ISSUE,
      }),
    ).toThrow(/pull requests only/i)
  })

  it('blocks review requested on an issue', () => {
    expect(
      unsupportedGithubCombination(GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED, GITHUB_OBJECT_ISSUE),
    ).toMatch(/pull requests only/i)
  })

  it('blocks assigned on a pull request', () => {
    expect(
      unsupportedGithubCombination(GITHUB_COMPOSER_EVENT_ASSIGNED, GITHUB_OBJECT_PULL_REQUEST),
    ).toMatch(/issues only/i)
  })

  it('keeps an empty specific-user login invalid until Anyone or a login is set', () => {
    const trigger = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
      objectKind: GITHUB_OBJECT_ISSUE,
      actor: '',
    })
    expect(trigger).toMatchObject({
      kind: ROUTINE_TRIGGER_GITHUB_EVENT,
      filters: { object_kind: GITHUB_OBJECT_ISSUE, actor: '' },
    })
    expect(githubTriggerSaveError(trigger)).toMatch(/GitHub login/i)
    expect(deserializeGithubTrigger(trigger).actor).toBe('')

    const merged = draft({
      ...baseDraft,
      eventKind: GITHUB_COMPOSER_EVENT_MERGED,
      objectKind: GITHUB_OBJECT_PULL_REQUEST,
      actor: '',
    })
    expect(merged).toMatchObject({
      kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
      actor: '',
    })
    expect(githubTriggerSaveError(merged)).toMatch(/GitHub login/i)
  })

  it('requires owner/repo on github_event before Save', () => {
    expect(
      githubTriggerSaveError({
        kind: ROUTINE_TRIGGER_GITHUB_EVENT,
        event_type: GITHUB_EVENT_ISSUE_COMMENT,
        owner_repo: '',
        filters: { object_kind: GITHUB_OBJECT_ISSUE },
      }),
    ).toMatch(/owner\/repo/i)
    expect(
      githubTriggerSaveError({
        kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
        owner_repo: '',
        event: ROUTINE_EVENT_MERGED,
        actor: ROUTINE_ACTOR_ANYONE,
      }),
    ).toBeNull()
  })
})

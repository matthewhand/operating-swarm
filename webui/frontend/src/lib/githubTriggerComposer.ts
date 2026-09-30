/**
 * #1402 — GitHub routine trigger composer.
 *
 * Chip-style fields (event kind, actor, issue/PR, repository) serialize onto
 * the existing OS trigger kinds (`github_event`, `github_pr_merged`). This is
 * a view over that schema, not a second trigger system.
 */
import {
  ROUTINE_ACTOR_ANYONE,
  ROUTINE_EVENT_MERGED,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  type GithubEventTrigger,
  type GithubPrMergedTrigger,
  type RoutineTrigger,
} from './routines'

export const GITHUB_COMPOSER_EVENT_COMMENT = 'comment'
export const GITHUB_COMPOSER_EVENT_ASSIGNED = 'assigned'
export const GITHUB_COMPOSER_EVENT_OPENED = 'opened'
export const GITHUB_COMPOSER_EVENT_MERGED = 'merged'
export const GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED = 'review_requested'
export const GITHUB_COMPOSER_EVENT_PUSH = 'push'

export const GITHUB_OBJECT_ISSUE = 'issue'
export const GITHUB_OBJECT_PULL_REQUEST = 'pull_request'

export const GITHUB_EVENT_ISSUE_COMMENT = 'issue_comment.created'
export const GITHUB_EVENT_ISSUE_ASSIGNED = 'issues.assigned'
export const GITHUB_EVENT_ISSUE_OPENED = 'issues.opened'
export const GITHUB_EVENT_PR_OPENED = 'pull_request.opened'
export const GITHUB_EVENT_PR_REVIEW_REQUESTED = 'pull_request.review_requested'
export const GITHUB_EVENT_PUSH = 'push'

export type GithubComposerEventKind =
  | typeof GITHUB_COMPOSER_EVENT_COMMENT
  | typeof GITHUB_COMPOSER_EVENT_ASSIGNED
  | typeof GITHUB_COMPOSER_EVENT_OPENED
  | typeof GITHUB_COMPOSER_EVENT_MERGED
  | typeof GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED
  | typeof GITHUB_COMPOSER_EVENT_PUSH

export type GithubComposerObjectKind =
  | typeof GITHUB_OBJECT_ISSUE
  | typeof GITHUB_OBJECT_PULL_REQUEST

export interface GithubTriggerComposerDraft {
  eventKind: GithubComposerEventKind
  actor: string
  objectKind: GithubComposerObjectKind
  ownerRepo: string
  labels: string[]
  branch: string
  excludeAuthors: string[]
}

export type GithubRoutineTrigger = GithubEventTrigger | GithubPrMergedTrigger

const OWNER_REPO_RE = /^[\w.-]+\/[\w.-]+$/

const EVENT_KIND_LABELS: Record<GithubComposerEventKind, string> = {
  comment: 'Comment',
  assigned: 'Assigned',
  opened: 'Opened',
  merged: 'Merged',
  review_requested: 'Review requested',
  push: 'Push',
}

const OBJECT_KIND_LABELS: Record<GithubComposerObjectKind, string> = {
  issue: 'Issue',
  pull_request: 'Pull request',
}

export function isGithubRoutineTrigger(trigger: RoutineTrigger | undefined | null): trigger is GithubRoutineTrigger {
  return trigger?.kind === ROUTINE_TRIGGER_GITHUB_EVENT || trigger?.kind === ROUTINE_TRIGGER_GITHUB_PR_MERGED
}

export function githubComposerEventKinds(): GithubComposerEventKind[] {
  return [
    GITHUB_COMPOSER_EVENT_COMMENT,
    GITHUB_COMPOSER_EVENT_ASSIGNED,
    GITHUB_COMPOSER_EVENT_OPENED,
    GITHUB_COMPOSER_EVENT_MERGED,
    GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED,
    GITHUB_COMPOSER_EVENT_PUSH,
  ]
}

export function githubComposerEventLabel(kind: GithubComposerEventKind): string {
  return EVENT_KIND_LABELS[kind]
}

export function githubComposerObjectLabel(kind: GithubComposerObjectKind): string {
  return OBJECT_KIND_LABELS[kind]
}

/** Object kinds that can be combined with this event. Empty = repository-wide (push). */
export function objectKindsForEvent(eventKind: GithubComposerEventKind): GithubComposerObjectKind[] {
  switch (eventKind) {
    case GITHUB_COMPOSER_EVENT_COMMENT:
    case GITHUB_COMPOSER_EVENT_OPENED:
      return [GITHUB_OBJECT_ISSUE, GITHUB_OBJECT_PULL_REQUEST]
    case GITHUB_COMPOSER_EVENT_ASSIGNED:
      return [GITHUB_OBJECT_ISSUE]
    case GITHUB_COMPOSER_EVENT_MERGED:
    case GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED:
      return [GITHUB_OBJECT_PULL_REQUEST]
    case GITHUB_COMPOSER_EVENT_PUSH:
      return []
    default:
      return [GITHUB_OBJECT_ISSUE, GITHUB_OBJECT_PULL_REQUEST]
  }
}

export function defaultGithubComposerDraft(): GithubTriggerComposerDraft {
  return {
    eventKind: GITHUB_COMPOSER_EVENT_OPENED,
    actor: ROUTINE_ACTOR_ANYONE,
    objectKind: GITHUB_OBJECT_ISSUE,
    ownerRepo: '',
    labels: [],
    branch: '',
    excludeAuthors: [],
  }
}

function normalizeActor(value: string | undefined | null): string {
  const text = (value || '').trim()
  if (!text || text.toLowerCase() === ROUTINE_ACTOR_ANYONE) return ROUTINE_ACTOR_ANYONE
  return text
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => String(item ?? '').trim()).filter(Boolean)
}

function extrasFromTrigger(trigger: GithubEventTrigger): Pick<
  GithubTriggerComposerDraft,
  'labels' | 'branch' | 'excludeAuthors'
> {
  const filters = trigger.filters || {}
  return {
    labels: asStringList(filters.labels),
    branch: String(filters.branch || '').trim(),
    excludeAuthors: asStringList(filters.exclude_authors),
  }
}

function actorFromTrigger(trigger: GithubRoutineTrigger): string {
  if (trigger.kind === ROUTINE_TRIGGER_GITHUB_PR_MERGED) {
    if (trigger.actor === '') return ''
    return normalizeActor(trigger.actor)
  }
  const filters = trigger.filters
  if (filters && Object.prototype.hasOwnProperty.call(filters, 'actor')) {
    const raw = String(filters.actor ?? '')
    if (!raw.trim()) return ''
    return normalizeActor(raw)
  }
  const topLevel = 'actor' in trigger ? String((trigger as { actor?: string }).actor || '') : ''
  return normalizeActor(topLevel)
}

export function deserializeGithubTrigger(trigger: RoutineTrigger): GithubTriggerComposerDraft {
  if (trigger.kind === ROUTINE_TRIGGER_GITHUB_PR_MERGED) {
    return {
      ...defaultGithubComposerDraft(),
      eventKind: GITHUB_COMPOSER_EVENT_MERGED,
      actor: actorFromTrigger(trigger),
      objectKind: GITHUB_OBJECT_PULL_REQUEST,
      ownerRepo: trigger.owner_repo || '',
    }
  }
  if (trigger.kind !== ROUTINE_TRIGGER_GITHUB_EVENT) {
    return defaultGithubComposerDraft()
  }

  const extras = extrasFromTrigger(trigger)
  const ownerRepo = trigger.owner_repo || ''
  const actor = actorFromTrigger(trigger)
  const objectFromFilters = String(trigger.filters?.object_kind || '').trim().toLowerCase()
  const objectKind: GithubComposerObjectKind =
    objectFromFilters === GITHUB_OBJECT_PULL_REQUEST || objectFromFilters === 'pr'
      ? GITHUB_OBJECT_PULL_REQUEST
      : GITHUB_OBJECT_ISSUE

  switch (trigger.event_type) {
    case GITHUB_EVENT_ISSUE_COMMENT:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_COMMENT,
        actor,
        objectKind,
        ownerRepo,
        ...extras,
      }
    case GITHUB_EVENT_ISSUE_ASSIGNED:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_ASSIGNED,
        actor,
        objectKind: GITHUB_OBJECT_ISSUE,
        ownerRepo,
        ...extras,
      }
    case GITHUB_EVENT_ISSUE_OPENED:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_OPENED,
        actor,
        objectKind: GITHUB_OBJECT_ISSUE,
        ownerRepo,
        ...extras,
      }
    case GITHUB_EVENT_PR_OPENED:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_OPENED,
        actor,
        objectKind: GITHUB_OBJECT_PULL_REQUEST,
        ownerRepo,
        ...extras,
      }
    case GITHUB_EVENT_PR_REVIEW_REQUESTED:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED,
        actor,
        objectKind: GITHUB_OBJECT_PULL_REQUEST,
        ownerRepo,
        ...extras,
      }
    case GITHUB_EVENT_PUSH:
      return {
        eventKind: GITHUB_COMPOSER_EVENT_PUSH,
        actor,
        objectKind: GITHUB_OBJECT_PULL_REQUEST,
        ownerRepo,
        ...extras,
      }
    default:
      return {
        ...defaultGithubComposerDraft(),
        actor,
        ownerRepo,
        objectKind,
        ...extras,
      }
  }
}

export function unsupportedGithubCombination(
  eventKind: GithubComposerEventKind,
  objectKind: GithubComposerObjectKind,
): string | null {
  const allowed = objectKindsForEvent(eventKind)
  if (allowed.length === 0) return null
  if (allowed.includes(objectKind)) return null
  if (eventKind === GITHUB_COMPOSER_EVENT_MERGED) {
    return 'Merged events apply to pull requests only. Switch the target to Pull request, or pick a different event.'
  }
  if (eventKind === GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED) {
    return 'Review requested applies to pull requests only. Switch the target to Pull request, or pick a different event.'
  }
  if (eventKind === GITHUB_COMPOSER_EVENT_ASSIGNED) {
    return 'Assigned is supported for issues only. Switch the target to Issue, or pick Comment / Opened for pull requests.'
  }
  return `“${githubComposerEventLabel(eventKind)}” cannot target a ${githubComposerObjectLabel(objectKind).toLowerCase()}.`
}

function githubEventFilters(draft: GithubTriggerComposerDraft, includeObjectKind: boolean): GithubEventTrigger['filters'] {
  const filters: NonNullable<GithubEventTrigger['filters']> = {}
  if (includeObjectKind) filters.object_kind = draft.objectKind
  if (draft.actor.trim() === '') {
    filters.actor = ''
  } else {
    const actor = normalizeActor(draft.actor)
    if (actor !== ROUTINE_ACTOR_ANYONE) filters.actor = actor
  }
  if (draft.labels.length) filters.labels = [...draft.labels]
  if (draft.branch.trim()) filters.branch = draft.branch.trim()
  if (draft.excludeAuthors.length) filters.exclude_authors = [...draft.excludeAuthors]
  return filters
}

export function serializeGithubTrigger(draft: GithubTriggerComposerDraft): GithubRoutineTrigger {
  const ownerRepo = draft.ownerRepo.trim()
  const actor = draft.actor.trim() === '' ? '' : normalizeActor(draft.actor)
  const unsupported = unsupportedGithubCombination(draft.eventKind, draft.objectKind)
  if (unsupported) {
    throw new Error(unsupported)
  }

  if (draft.eventKind === GITHUB_COMPOSER_EVENT_MERGED) {
    return {
      kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
      owner_repo: ownerRepo,
      event: ROUTINE_EVENT_MERGED,
      actor,
    }
  }

  let eventType: string
  let includeObjectKind = false
  switch (draft.eventKind) {
    case GITHUB_COMPOSER_EVENT_COMMENT:
      eventType = GITHUB_EVENT_ISSUE_COMMENT
      includeObjectKind = true
      break
    case GITHUB_COMPOSER_EVENT_ASSIGNED:
      eventType = GITHUB_EVENT_ISSUE_ASSIGNED
      includeObjectKind = true
      break
    case GITHUB_COMPOSER_EVENT_OPENED:
      eventType =
        draft.objectKind === GITHUB_OBJECT_PULL_REQUEST ? GITHUB_EVENT_PR_OPENED : GITHUB_EVENT_ISSUE_OPENED
      includeObjectKind = true
      break
    case GITHUB_COMPOSER_EVENT_REVIEW_REQUESTED:
      eventType = GITHUB_EVENT_PR_REVIEW_REQUESTED
      includeObjectKind = true
      break
    case GITHUB_COMPOSER_EVENT_PUSH:
      eventType = GITHUB_EVENT_PUSH
      includeObjectKind = false
      break
    default:
      eventType = GITHUB_EVENT_ISSUE_OPENED
      includeObjectKind = true
  }

  return {
    kind: ROUTINE_TRIGGER_GITHUB_EVENT,
    event_type: eventType,
    owner_repo: ownerRepo,
    filters: githubEventFilters(draft, includeObjectKind),
  }
}

export function githubTriggerSaveError(trigger: RoutineTrigger): string | null {
  if (!isGithubRoutineTrigger(trigger)) return null
  const draft = deserializeGithubTrigger(trigger)
  const unsupported = unsupportedGithubCombination(draft.eventKind, draft.objectKind)
  if (unsupported) return unsupported
  if (trigger.kind === ROUTINE_TRIGGER_GITHUB_EVENT) {
    const repo = draft.ownerRepo.trim()
    if (!repo) return 'GitHub event triggers need a repository as owner/repo before Save.'
    if (!OWNER_REPO_RE.test(repo)) return 'Repository must be owner/repo (GitHub only).'
  } else if (draft.ownerRepo.trim() && !OWNER_REPO_RE.test(draft.ownerRepo.trim())) {
    return 'Repository must be owner/repo (GitHub only).'
  }
  if (draft.actor.trim() === '') {
    return 'Enter a GitHub login, or switch the actor back to Anyone.'
  }
  const actor = normalizeActor(draft.actor)
  if (actor !== ROUTINE_ACTOR_ANYONE && (actor.includes('/') || actor.startsWith('ghp_') || actor.startsWith('github_pat_'))) {
    return 'Actor must be a GitHub login or Anyone.'
  }
  return null
}

export function applyComposerEventKind(
  draft: GithubTriggerComposerDraft,
  eventKind: GithubComposerEventKind,
): GithubTriggerComposerDraft {
  const allowed = objectKindsForEvent(eventKind)
  const objectKind = allowed.length === 0
    ? draft.objectKind
    : allowed.includes(draft.objectKind)
      ? draft.objectKind
      : allowed[0]
  return { ...draft, eventKind, objectKind }
}

export function applyComposerObjectKind(
  draft: GithubTriggerComposerDraft,
  objectKind: GithubComposerObjectKind,
): GithubTriggerComposerDraft {
  return { ...draft, objectKind }
}

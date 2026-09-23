import { apiDelete, apiGet, apiPatch, apiPost } from './api'
import { agentIdFromBlueprint } from './agentChat'
import { parseCreatedAtMs, sydneyDayKey } from './chatTime'

export const ROUTINE_TRIGGER_GITHUB_PR_MERGED = 'github_pr_merged'
export const ROUTINE_TRIGGER_GITHUB_EVENT = 'github_event'
export const ROUTINE_TRIGGER_INTERVAL = 'interval'
export const ROUTINE_TRIGGER_CRON = 'cron'
export const ROUTINE_TRIGGER_ONE_SHOT = 'one_shot'
export const ROUTINE_TRIGGER_MAILBOX_MESSAGE = 'mailbox_message'
export const ROUTINE_EVENT_MERGED = 'merged'
export const ROUTINE_ACTOR_ANYONE = 'anyone'

export const GITHUB_EVENT_TYPES = [
  'issues.opened',
  'pull_request.opened',
  'pull_request.review_requested',
  'push',
] as const

export type GithubEventType = (typeof GITHUB_EVENT_TYPES)[number]

export type RoutineTriggerKind =
  | typeof ROUTINE_TRIGGER_GITHUB_PR_MERGED
  | typeof ROUTINE_TRIGGER_GITHUB_EVENT
  | typeof ROUTINE_TRIGGER_INTERVAL
  | typeof ROUTINE_TRIGGER_CRON
  | typeof ROUTINE_TRIGGER_ONE_SHOT
  | typeof ROUTINE_TRIGGER_MAILBOX_MESSAGE

export interface GithubPrMergedTrigger {
  kind: typeof ROUTINE_TRIGGER_GITHUB_PR_MERGED
  owner_repo: string
  event: typeof ROUTINE_EVENT_MERGED
  actor: string
}

export interface GithubEventTrigger {
  kind: typeof ROUTINE_TRIGGER_GITHUB_EVENT
  event_type: GithubEventType | string
  owner_repo: string
  filters?: { labels?: string[]; branch?: string }
}

export interface IntervalTrigger {
  kind: typeof ROUTINE_TRIGGER_INTERVAL
  seconds: number
}

export interface CronTrigger {
  kind: typeof ROUTINE_TRIGGER_CRON
  expression: string
}

export interface OneShotTrigger {
  kind: typeof ROUTINE_TRIGGER_ONE_SHOT
  run_at: string
}

export interface MailboxMessageTrigger {
  kind: typeof ROUTINE_TRIGGER_MAILBOX_MESSAGE
  sender: string
  pattern: string
}

export type RoutineTrigger =
  | GithubPrMergedTrigger
  | GithubEventTrigger
  | IntervalTrigger
  | CronTrigger
  | OneShotTrigger
  | MailboxMessageTrigger

export interface HistoryArtifact {
  kind?: string
  url?: string
  label?: string
}

export interface RoutineHistoryRow {
  id: string
  ran_at: string
  status: string
  source: string
  event?: string
  conversation_id?: string
  summary?: string
  duration_ms?: number
  token_cost?: number
  artifact?: HistoryArtifact
  error?: string
}

export interface Routine {
  id: string
  agent_id?: string
  name: string
  instruction: string
  active: boolean
  trigger: RoutineTrigger
  history: RoutineHistoryRow[]
  when_to_run?: string
  schedule?: string
  cron?: string
  next_run?: string | null
  agent_name?: string
  agent_kind?: string
}

export interface RoutineList {
  object: string
  agent_id: string
  routines: Routine[]
}

export interface RoutineWrite {
  name?: string
  instruction?: string
  active?: boolean
  trigger?: Partial<RoutineTrigger> & {
    owner?: string
    repo?: string
    kind?: RoutineTriggerKind
    seconds?: number
    every?: string
    expression?: string
    cron?: string
    run_at?: string
    sender?: string
    pattern?: string
    event_type?: string
    owner_repo?: string
    actor?: string
    filters?: { labels?: string[]; branch?: string }
  }
}

export function defaultTrigger(): GithubPrMergedTrigger {
  return {
    kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
    owner_repo: '',
    event: ROUTINE_EVENT_MERGED,
    actor: ROUTINE_ACTOR_ANYONE,
  }
}

export function emptyTrigger(kind: RoutineTriggerKind): RoutineTrigger {
  switch (kind) {
    case ROUTINE_TRIGGER_GITHUB_EVENT:
      return { kind, event_type: 'issues.opened', owner_repo: '', filters: {} }
    case ROUTINE_TRIGGER_INTERVAL:
      return { kind, seconds: 3600 }
    case ROUTINE_TRIGGER_CRON:
      return { kind, expression: '0 3 * * *' }
    case ROUTINE_TRIGGER_ONE_SHOT:
      return { kind, run_at: '' }
    case ROUTINE_TRIGGER_MAILBOX_MESSAGE:
      return { kind, sender: '', pattern: '' }
    default:
      return defaultTrigger()
  }
}

export function triggerSummary(trigger: RoutineTrigger | undefined | null): string {
  if (!trigger) return 'When a PR merges in a GitHub repo…'
  if (trigger.kind === ROUTINE_TRIGGER_INTERVAL) {
    const seconds = trigger.seconds || 0
    if (seconds % 86400 === 0) {
      const days = seconds / 86400
      return `Every ${days} day${days === 1 ? '' : 's'}…`
    }
    if (seconds % 3600 === 0) {
      const hours = seconds / 3600
      return `Every ${hours} hour${hours === 1 ? '' : 's'}…`
    }
    if (seconds % 60 === 0) return `Every ${seconds / 60} min…`
    return `Every ${seconds}s…`
  }
  if (trigger.kind === ROUTINE_TRIGGER_CRON) {
    return `Cron ${trigger.expression || ''}…`
  }
  if (trigger.kind === ROUTINE_TRIGGER_ONE_SHOT) {
    return trigger.run_at ? `Once at ${trigger.run_at}…` : 'Once at a set time…'
  }
  if (trigger.kind === ROUTINE_TRIGGER_MAILBOX_MESSAGE) {
    const sender = trigger.sender?.trim() || 'anyone'
    if (trigger.pattern?.trim()) return `When mailbox from ${sender} matches ${trigger.pattern}…`
    return `When a mailbox message arrives from ${sender}…`
  }
  if (trigger.kind === ROUTINE_TRIGGER_GITHUB_EVENT) {
    const repo = trigger.owner_repo?.trim() || 'a GitHub repo'
    const extras: string[] = []
    const labels = trigger.filters?.labels || []
    if (labels.length) extras.push(`labels: ${labels.join(', ')}`)
    if (trigger.filters?.branch) extras.push(`branch: ${trigger.filters.branch}`)
    const suffix = extras.length ? ` (${extras.join('; ')})` : ''
    return `When ${trigger.event_type} in ${repo}${suffix}…`
  }
  const repo = 'owner_repo' in trigger ? trigger.owner_repo?.trim() : ''
  return `When a PR merges in ${repo || 'a GitHub repo'}…`
}

function partMap(
  ms: number,
  timeZone: string,
  options: Intl.DateTimeFormatOptions,
): Record<string, string> {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone, ...options }).formatToParts(
    new Date(ms),
  )
  const map: Record<string, string> = {}
  for (const part of parts) {
    if (part.type !== 'literal') map[part.type] = part.value
  }
  return map
}

function formatClock(ms: number, timeZone: string): string {
  const parts = partMap(ms, timeZone, {
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  })
  const dayPeriod = (parts.dayPeriod || 'AM').replace(/\./g, '').trim().toUpperCase()
  return `${Number(parts.hour)}:${parts.minute} ${dayPeriod}`
}

/** Just now / 32 min ago / Today at 7:34 AM (REQ-80 history). */
export function formatRoutineHistoryTime(
  value: string | number | undefined | null,
  nowMs: number = Date.now(),
  timeZone: string = 'Australia/Sydney',
): string {
  const ms = parseCreatedAtMs(value ?? undefined)
  if (ms == null) return ''
  const diffMs = nowMs - ms
  if (diffMs >= 0 && diffMs < 60 * 1000) return 'Just now'
  if (diffMs >= 60 * 1000 && diffMs < 60 * 60 * 1000) {
    const mins = Math.floor(diffMs / 60000)
    return `${mins} min ago`
  }
  const clock = formatClock(ms, timeZone)
  if (sydneyDayKey(ms, timeZone) === sydneyDayKey(nowMs, timeZone)) {
    return `Today at ${clock}`
  }
  const stamp = partMap(ms, timeZone, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  })
  return `${stamp.weekday} ${stamp.day} ${stamp.month} at ${clock}`
}

export function formatDurationMs(durationMs: number | undefined | null): string {
  if (durationMs == null || Number.isNaN(durationMs)) return ''
  if (durationMs < 1000) return `${Math.max(0, Math.round(durationMs))}ms`
  const seconds = durationMs / 1000
  if (seconds < 60) return `${seconds.toFixed(seconds < 10 ? 1 : 0)}s`
  const mins = Math.floor(seconds / 60)
  const rem = Math.round(seconds % 60)
  return rem ? `${mins}m ${rem}s` : `${mins}m`
}

export function historySucceeded(row: RoutineHistoryRow | undefined | null): boolean {
  const status = (row?.status || '').toLowerCase()
  return status === 'success' || status === 'ok' || status === 'pass'
}

export function routinesPath(agentId: string): string {
  const agent = agentIdFromBlueprint(agentId)
  return `/v1/agents/${encodeURIComponent(agent)}/routines/`
}

export function routinePath(agentId: string, routineId: string): string {
  return `${routinesPath(agentId)}${encodeURIComponent(routineId)}/`
}

export async function fetchRoutines(agentId: string): Promise<Routine[]> {
  const data = await apiGet<RoutineList>(routinesPath(agentId))
  return Array.isArray(data?.routines) ? data.routines : []
}

export async function fetchAllRoutines(): Promise<Routine[]> {
  const data = await apiGet<RoutineList | { routines: Routine[] }>("/v1/routines")
  return Array.isArray((data as any)?.routines)
    ? (data as any).routines
    : Array.isArray(data)
      ? (data as unknown as Routine[])
      : []
}

export async function createRoutine(agentId: string, body: RoutineWrite = {}): Promise<Routine> {
  const trigger = body.trigger
  return apiPost<Routine>(routinesPath(agentId), {
    name: body.name ?? 'New routine',
    instruction: body.instruction ?? '',
    active: body.active ?? true,
    trigger: trigger ?? defaultTrigger(),
  })
}

export async function updateRoutine(
  agentId: string,
  routineId: string,
  patch: RoutineWrite,
): Promise<Routine> {
  return apiPatch<Routine>(routinePath(agentId, routineId), patch)
}

export async function deleteRoutine(agentId: string, routineId: string): Promise<void> {
  await apiDelete(routinePath(agentId, routineId))
}

export async function testRunRoutine(agentId: string, routineId: string): Promise<Routine> {
  return apiPost<Routine>(`${routinePath(agentId, routineId)}test-run/`, {})
}

export async function runNowRoutine(agentId: string, routineId: string): Promise<Routine> {
  return apiPost<Routine>(`${routinePath(agentId, routineId)}run-now/`, {})
}

export async function deliverGithubPrMerged(payload: {
  owner_repo: string
  actor?: string
  event?: string
}): Promise<{ count: number }> {
  return apiPost<{ count: number }>('/v1/routines/github-merge/', {
    owner_repo: payload.owner_repo,
    actor: payload.actor ?? ROUTINE_ACTOR_ANYONE,
    event: payload.event ?? ROUTINE_EVENT_MERGED,
  })
}

export async function deliverMailboxMessage(payload: {
  sender?: string
  content?: string
  subject?: string
}): Promise<{ count: number }> {
  return apiPost<{ count: number }>('/v1/routines/mailbox-message/', payload)
}

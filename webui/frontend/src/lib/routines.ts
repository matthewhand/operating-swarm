import { apiDelete, apiGet, apiPatch, apiPost, buildHeaders, throwApiError } from './api'
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

export const TOOL_OPEN_PULL_REQUEST = 'open_pull_request'
export const TOOL_MEMORIES = 'memories'

export const ROUTINE_TOOL_CATALOG = [
  {
    id: TOOL_OPEN_PULL_REQUEST,
    label: 'Open Pull Request',
    description: 'Open or update a GitHub pull request from this routine run. Never auto-merges.',
    wired: true,
  },
] as const

export type RoutineToolId = (typeof ROUTINE_TOOL_CATALOG)[number]['id']

export const GITHUB_EVENT_TYPES = [
  'issues.opened',
  'issues.assigned',
  'issue_comment.created',
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

export interface GithubEventFilters {
  labels?: string[]
  branch?: string
  exclude_authors?: string[]
  actor?: string
  object_kind?: 'issue' | 'pull_request'
}

export interface GithubEventTrigger {
  kind: typeof ROUTINE_TRIGGER_GITHUB_EVENT
  event_type: GithubEventType | string
  owner_repo: string
  actor?: string
  filters?: GithubEventFilters
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
  slug?: string
  name: string
  description?: string
  instruction: string
  job?: string
  active: boolean
  /** Optional seat/profile id. Empty means the seat default. */
  model?: string
  enabled?: boolean
  pending_fill?: boolean
  fill_in_keys?: string[]
  trigger: RoutineTrigger
  /** Effective tool ids (defaults applied when tools_explicit is false). */
  tools?: string[]
  /** True when the operator/API set tools; false means defaults follow the trigger. */
  tools_explicit?: boolean
  history: RoutineHistoryRow[]
  when_to_run?: string
  schedule?: string
  cron?: string
  next_run?: string | null
  agent_name?: string
  agent_kind?: string
  dry_run?: boolean
  preview?: RoutineDryRunPreview
}

/** #1405 — documented Test preview. Never a live fire. */
export interface RoutineDryRunPreview {
  dry_run: boolean
  side_effects: string
  note: string
  trigger_summary: string
  trigger_kind: string
  trigger_match: {
    kind: string
    summary: string
    configured: boolean
  }
  prompt: string
  model: string
  armed: boolean
  would_run_if_triggered: boolean
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
  model?: string
  /** Opt in to a deliberate copy of an existing routine (#1316). */
  allow_duplicate?: boolean
  /** Explicit tools list. Empty array persists removal of defaults (#1403). */
  tools?: string[]
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
    filters?: GithubEventFilters
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

export function isGithubIssueTrigger(trigger: RoutineTrigger | undefined | null): boolean {
  if (!trigger || trigger.kind !== ROUTINE_TRIGGER_GITHUB_EVENT) return false
  return String(trigger.event_type || '').startsWith('issues.')
}

export function defaultToolsForTrigger(trigger: RoutineTrigger | undefined | null): string[] {
  return isGithubIssueTrigger(trigger) ? [TOOL_OPEN_PULL_REQUEST] : []
}

export function effectiveRoutineTools(
  routine: Pick<Routine, 'tools' | 'tools_explicit' | 'trigger'> | null | undefined,
  trigger: RoutineTrigger | undefined | null = routine?.trigger,
): string[] {
  if (routine?.tools_explicit) return [...(routine.tools || [])]
  return defaultToolsForTrigger(trigger ?? routine?.trigger)
}

export function hasOpenPullRequestTool(tools: string[] | undefined | null): boolean {
  return (tools || []).includes(TOOL_OPEN_PULL_REQUEST)
}

export function toggleOpenPullRequestTool(tools: string[] | undefined | null, enabled: boolean): string[] {
  const next = (tools || []).filter((id) => id !== TOOL_OPEN_PULL_REQUEST)
  if (enabled) next.unshift(TOOL_OPEN_PULL_REQUEST)
  return next
}

export function extraRoutineTools(tools: string[] | undefined | null): string[] {
  return (tools || []).filter((id) => id !== TOOL_OPEN_PULL_REQUEST)
}

export function addRoutineTool(tools: string[] | undefined | null, toolId: string): string[] {
  const id = String(toolId || '').trim()
  const next = [...(tools || [])]
  if (id && !next.includes(id)) next.push(id)
  return next
}

export function removeRoutineTool(tools: string[] | undefined | null, toolId: string): string[] {
  return (tools || []).filter((id) => id !== toolId)
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
    if (trigger.filters?.object_kind) extras.push(`on ${trigger.filters.object_kind}`)
    const actor = trigger.filters?.actor || trigger.actor
    if (actor && actor !== ROUTINE_ACTOR_ANYONE) extras.push(`from ${actor}`)
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

/**
 * #1316 — thrown when the server refuses a twin routine (HTTP 409).
 * Carries the existing routine so the composer can offer to open it.
 */
export class DuplicateRoutineError extends Error {
  readonly status = 409
  readonly existingRoutine: Routine | null
  readonly existingRoutineId: string

  constructor(message: string, existingRoutine: Routine | null = null) {
    super(message)
    this.name = 'DuplicateRoutineError'
    this.existingRoutine = existingRoutine
    this.existingRoutineId = existingRoutine?.id ?? ''
  }
}

export function isDuplicateRoutineError(error: unknown): error is DuplicateRoutineError {
  return error instanceof DuplicateRoutineError
}

export async function createRoutine(agentId: string, body: RoutineWrite = {}): Promise<Routine> {
  const trigger = body.trigger
  const payload: Record<string, unknown> = {
    name: body.name ?? 'New routine',
    instruction: body.instruction ?? '',
    active: body.active ?? true,
    model: body.model ?? '',
    trigger: trigger ?? defaultTrigger(),
  }
  if (body.allow_duplicate) payload.allow_duplicate = true
  if (Array.isArray(body.tools)) payload.tools = body.tools

  // Issued directly (not via apiPost) so the 409 conflict payload survives and
  // can be surfaced as a typed error carrying the existing routine (#1316).
  const path = routinesPath(agentId)
  const response = await fetch(path, {
    method: 'POST',
    headers: buildHeaders(true),
    body: JSON.stringify(payload),
  })
  if (response.status === 409) {
    let existing: Routine | null = null
    let message = 'A routine with the same name, instruction, and trigger already exists.'
    try {
      const data = (await response.json()) as { error?: string; existing_routine?: Routine }
      if (data?.existing_routine) existing = data.existing_routine
      if (data?.error) message = data.error
    } catch {
      // Non-JSON conflict body — keep the default message.
    }
    throw new DuplicateRoutineError(message, existing)
  }
  if (!response.ok) {
    await throwApiError(path, response)
  }
  return (await response.json()) as Routine
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

const DRY_RUN_NOTE =
  'Dry-run preview. No messages sent, no PRs merged, instruction not executed.'

/**
 * Keep on-screen draft fields that this partial save did not write.
 * A name/armed/trigger round-trip used to replace `editing` with the server
 * row and wipe an instruction or model the operator had not blurred yet.
 */
export function mergeRoutineSave(
  current: Routine,
  updated: Routine,
  patch: Partial<Routine>,
): Routine {
  const next: Routine = { ...current, ...updated }
  if (!Object.prototype.hasOwnProperty.call(patch, 'name')) next.name = current.name
  if (!Object.prototype.hasOwnProperty.call(patch, 'instruction')) next.instruction = current.instruction
  if (!Object.prototype.hasOwnProperty.call(patch, 'model')) next.model = current.model
  if (!Object.prototype.hasOwnProperty.call(patch, 'active')) next.active = current.active
  if (!Object.prototype.hasOwnProperty.call(patch, 'trigger')) next.trigger = current.trigger
  return next
}

/** Profile ids only. Raw model names (shared by several profiles) are not seat ids. */
export function routineModelOptionIds(
  profiles: Array<{ id?: string | null; model?: string | null }> | undefined,
  current?: string,
): string[] {
  const ids: string[] = []
  const seen = new Set<string>()
  for (const profile of profiles ?? []) {
    const id = (profile.id || '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    ids.push(id)
  }
  const stored = (current || '').trim()
  if (stored && !seen.has(stored)) ids.unshift(stored)
  return ids
}

/** Client-side Test preview for unsaved drafts (#1405). No network. */
export function previewRoutineDryRun(
  routine: Pick<Routine, 'instruction' | 'active' | 'trigger' | 'model'>,
): RoutineDryRunPreview {
  const trigger = routine.trigger
  const summary = triggerSummary(trigger)
  const kind = trigger?.kind || ''
  return {
    dry_run: true,
    side_effects: 'none',
    note: DRY_RUN_NOTE,
    trigger_summary: summary,
    trigger_kind: kind,
    trigger_match: {
      kind,
      summary,
      configured: Boolean(trigger),
    },
    prompt: routine.instruction || '',
    model: routine.model || '',
    armed: Boolean(routine.active),
    would_run_if_triggered: Boolean(routine.active),
  }
}

/**
 * Test shows the draft on screen. The server envelope only confirms the
 * dry-run contract; its saved prompt must not hide unsaved edits.
 */
export function resolveRoutinePreview(routine: Routine, remote?: Routine): RoutineDryRunPreview {
  const local = previewRoutineDryRun(routine)
  const remotePreview = remote?.preview
  if (!remotePreview) return local
  return {
    ...remotePreview,
    trigger_summary: local.trigger_summary,
    trigger_kind: local.trigger_kind,
    trigger_match: local.trigger_match,
    prompt: local.prompt,
    model: local.model,
    armed: local.armed,
    would_run_if_triggered: local.would_run_if_triggered,
    dry_run: true,
    side_effects: remotePreview.side_effects || local.side_effects,
    note: remotePreview.note || local.note,
  }
}

/** Persistable builder fields — Save does not require Active (#1405). */
export function routineDraftWrite(routine: Routine): RoutineWrite {
  return {
    name: routine.name,
    instruction: routine.instruction,
    active: Boolean(routine.active),
    model: routine.model || '',
    trigger: routine.trigger,
    ...(routine.tools_explicit ? { tools: effectiveRoutineTools(routine) } : {}),
  }
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

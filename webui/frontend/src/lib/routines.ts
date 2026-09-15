import { apiDelete, apiGet, apiPatch, apiPost } from './api'
import { agentIdFromBlueprint } from './agentChat'
import { parseCreatedAtMs, sydneyDayKey } from './chatTime'

export const ROUTINE_TRIGGER_GITHUB_PR_MERGED = 'github_pr_merged'
export const ROUTINE_EVENT_MERGED = 'merged'
export const ROUTINE_ACTOR_ANYONE = 'anyone'

export interface RoutineTrigger {
  kind: typeof ROUTINE_TRIGGER_GITHUB_PR_MERGED
  owner_repo: string
  event: typeof ROUTINE_EVENT_MERGED
  actor: string
}

export interface RoutineHistoryRow {
  id: string
  ran_at: string
  status: string
  source: string
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
  next_run?: string
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
  trigger?: Partial<RoutineTrigger> & { owner?: string; repo?: string }
}

export function defaultTrigger(): RoutineTrigger {
  return {
    kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
    owner_repo: '',
    event: ROUTINE_EVENT_MERGED,
    actor: ROUTINE_ACTOR_ANYONE,
  }
}

export function triggerSummary(trigger: RoutineTrigger | undefined | null): string {
  const repo = trigger?.owner_repo?.trim() || 'a GitHub repo'
  return `When a PR merges in ${repo}…`
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
  return apiPost<Routine>(routinesPath(agentId), {
    name: body.name ?? 'New routine',
    instruction: body.instruction ?? '',
    active: body.active ?? true,
    trigger: {
      kind: ROUTINE_TRIGGER_GITHUB_PR_MERGED,
      owner_repo: body.trigger?.owner_repo ?? '',
      event: ROUTINE_EVENT_MERGED,
      actor: body.trigger?.actor ?? ROUTINE_ACTOR_ANYONE,
    },
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

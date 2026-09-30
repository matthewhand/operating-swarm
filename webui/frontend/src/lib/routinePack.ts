/**
 * Routines-domain pack client (#1395 UI on #1394 APIs).
 *
 * Export selects seat routines and previews the fill-ins that pack will
 * require, including repo/channel ids export will strip to `{{FILL_IN}}`.
 * Import leaves rows inactive; the operator fills leftover `{{key}}` slots
 * and then enables. Incomplete slots block enable.
 */

import { apiGet, apiPost } from './api'
import {
  routinesPath,
  updateRoutine,
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  type Routine,
  type RoutineTrigger,
} from './routines'

export const ROUTINES_PACK_KIND = 'agent_routines_pack'
export const ROUTINES_PACK_OBJECT = 'agent_routines_pack'
export const ROUTINES_PACK_IMPORT_OBJECT = 'agent_routines_pack_import'
export const ROUTINES_PACK_VALIDATE_URL = '/v1/routines/packs/validate/'

/**
 * Shared source pattern. The key class matches the server scan in
 * `src/swarm/core/routines.py` (`{{_key}}` is a slot). Callers that scan or
 * replace must use a fresh RegExp — `/g` keeps lastIndex.
 */
export const FILL_IN_SCAN_RE = /\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}/g

export const FILL_IN_LABELS: Record<string, string> = {
  owner_repo: 'GitHub owner/repo',
  repo: 'GitHub owner/repo',
  repository: 'GitHub owner/repo',
  channel: 'Channel',
  channel_id: 'Channel',
  schedule: 'Schedule',
  cron: 'Cron expression',
  FILL_IN: 'Fill in',
}

const ID_FIELD_CANONICAL: Record<string, string> = {
  owner_repo: 'owner_repo',
  repository: 'owner_repo',
  repo: 'owner_repo',
  channel: 'channel',
  channel_id: 'channel',
  channelId: 'channel',
}

const OWNER_REPO_RE = /^[\w.-]+\/[\w.-]+$/
const GITHUB_TRIGGER_KINDS = new Set<string>([
  ROUTINE_TRIGGER_GITHUB_EVENT,
  ROUTINE_TRIGGER_GITHUB_PR_MERGED,
  '',
])

export type RoutineListStatus = 'pending-fill' | 'enabled' | 'paused'
export type RoutinePackStatus = RoutineListStatus

export interface RoutinePackFillIn {
  key: string
  label: string
  required?: boolean
  locations?: string[]
}

export interface RoutinePackRow {
  name: string
  instruction: string
  trigger: RoutineTrigger
  fill_ins?: RoutinePackFillIn[]
  key?: string
  role?: string
  description?: string
}

export interface RoutinePack {
  object: typeof ROUTINES_PACK_OBJECT | string
  kind: typeof ROUTINES_PACK_KIND | string
  schema: number
  routines: RoutinePackRow[]
  fill_ins: RoutinePackFillIn[]
  agent_id?: string
}

export interface RoutinePackSkip {
  name: string
  existing_routine_id?: string
  reason?: string
}

export interface RoutinePackImport {
  object: typeof ROUTINES_PACK_IMPORT_OBJECT | string
  agent_id: string
  pending_enable: boolean
  routines: Routine[]
  created_count: number
  skipped: RoutinePackSkip[]
  fill_ins_applied: string[]
  fill_ins_remaining: RoutinePackFillIn[]
  pack?: RoutinePack
}

type FillInCarrier = {
  name: string
  instruction: string
  trigger: RoutineTrigger
  description?: string
  job?: string
}

type RoutineFillState = Partial<FillInCarrier> & {
  active?: boolean
  enabled?: boolean
  pending_fill?: boolean
  fill_in_keys?: string[]
}

export function fillInScanPattern(): RegExp {
  return new RegExp(FILL_IN_SCAN_RE.source, 'g')
}

export function routinesPackPath(agentId: string): string {
  return `${routinesPath(agentId)}pack/`
}

export function routinesImportPath(agentId: string): string {
  return `${routinesPath(agentId)}import/`
}

export function fillInLabel(key: string): string {
  return FILL_IN_LABELS[key] || key.replace(/_/g, ' ')
}

export function incompleteFillInMessage(slots: RoutinePackFillIn[]): string {
  const labels = slots.map((slot) => slot.label || fillInLabel(slot.key))
  return `Complete required fill-ins before enabling: ${labels.join(', ')}.`
}

export class IncompleteFillInsError extends Error {
  readonly keys: string[]

  constructor(slots: RoutinePackFillIn[]) {
    super(incompleteFillInMessage(slots))
    this.name = 'IncompleteFillInsError'
    this.keys = slots.map((slot) => slot.key)
  }
}

export function canExportRoutinesPack(
  selectedIds: Iterable<string>,
  includePresets = false,
): boolean {
  if (includePresets) return true
  for (const id of selectedIds) {
    if (String(id).trim()) return true
  }
  return false
}

export function exportBlockedReason(
  selectedIds: Iterable<string>,
  includePresets = false,
): string | null {
  if (canExportRoutinesPack(selectedIds, includePresets)) return null
  return 'Select at least one routine, or include built-in presets.'
}

export function parsePackJson(raw: string): unknown {
  const text = String(raw || '').trim()
  if (!text) throw new Error('Paste a routines pack JSON document.')
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('Pack JSON is not valid JSON.')
  }
  if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
    const body = parsed as Record<string, unknown>
    if (body.pack && typeof body.pack === 'object') return body.pack
  }
  return parsed
}

export function isRoutinePack(raw: unknown): raw is RoutinePack {
  if (!raw || typeof raw !== 'object') return false
  const body = raw as Record<string, unknown>
  return Array.isArray(body.routines) && body.routines.length > 0
}

export function applyFillIns<T>(value: T, mapping: Record<string, string>, field = ''): T {
  if (Array.isArray(value)) {
    return value.map((item) => applyFillIns(item, mapping, field)) as T
  }
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[key] = applyFillIns(item, mapping, key)
    }
    return out as T
  }
  if (typeof value !== 'string') return value
  const whole = value.trim().match(/^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$/)
  if (whole?.[1] === 'FILL_IN') {
    const canonical = ID_FIELD_CANONICAL[field] || field || 'FILL_IN'
    if (mapping[canonical]) return mapping[canonical] as T
    if (mapping[field]) return mapping[field] as T
    if (mapping.FILL_IN) return mapping.FILL_IN as T
    return value
  }
  return value.replace(fillInScanPattern(), (match, key: string) => {
    if (key === 'FILL_IN') {
      const canonical = ID_FIELD_CANONICAL[field] || 'FILL_IN'
      if (mapping[canonical]) return mapping[canonical]
      if (mapping.FILL_IN) return mapping.FILL_IN
      return match
    }
    return Object.prototype.hasOwnProperty.call(mapping, key) ? mapping[key] : match
  }) as T
}

export function scanFillInKeys(value: unknown): string[] {
  const keys: string[] = []
  const seen = new Set<string>()

  const add = (key: string) => {
    if (!key || seen.has(key)) return
    seen.add(key)
    keys.push(key)
  }

  const walk = (item: unknown, field: string) => {
    if (typeof item === 'string') {
      const whole = item.trim().match(/^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$/)
      if (whole) {
        const name = whole[1] === 'FILL_IN' ? ID_FIELD_CANONICAL[field] || field || 'FILL_IN' : whole[1]
        add(name)
        return
      }
      for (const match of item.matchAll(fillInScanPattern())) {
        const name = match[1] === 'FILL_IN' ? ID_FIELD_CANONICAL[field] || 'FILL_IN' : match[1]
        add(name)
      }
      return
    }
    if (Array.isArray(item)) {
      item.forEach((child) => walk(child, field))
      return
    }
    if (item && typeof item === 'object') {
      for (const [key, child] of Object.entries(item as Record<string, unknown>)) {
        walk(child, key)
      }
    }
  }

  walk(value, '')
  return keys
}

export function remainingFillIns(routines: FillInCarrier[]): RoutinePackFillIn[] {
  const keys = scanFillInKeys(
    routines.map((row) => [row.name, row.description, row.instruction || row.job, row.trigger]),
  )
  return keys.map((key) => ({ key, label: fillInLabel(key), required: true }))
}

/** Empty GitHub owner/repo is a required slot on export, same as the pack API. */
export function triggerForFillInPreview(trigger: RoutineTrigger): RoutineTrigger {
  if (!trigger || !('owner_repo' in trigger)) return trigger
  const kind = trigger.kind
  if (kind !== ROUTINE_TRIGGER_GITHUB_EVENT && kind !== ROUTINE_TRIGGER_GITHUB_PR_MERGED) {
    return trigger
  }
  if (String(trigger.owner_repo || '').trim()) return trigger
  return { ...trigger, owner_repo: '{{owner_repo}}' }
}

function fillInSource(row: FillInCarrier): FillInCarrier {
  return {
    name: row.name,
    description: row.description,
    instruction: row.instruction || row.job || '',
    job: row.job,
    trigger: triggerForFillInPreview(row.trigger),
  }
}

function triggerRecord(trigger: RoutineTrigger | undefined): Record<string, unknown> {
  return (trigger ?? {}) as unknown as Record<string, unknown>
}

/** Owner/repo text the packer will see, including a split owner + repo pair. */
function resolvedOwnerRepo(trigger: Record<string, unknown>): string {
  const ownerRepo = String(trigger.owner_repo ?? '').trim()
  if (ownerRepo) return ownerRepo
  const owner = String(trigger.owner ?? '').trim()
  const repo = String(trigger.repo ?? '').trim()
  if (owner && repo && OWNER_REPO_RE.test(`${owner}/${repo}`)) return `${owner}/${repo}`
  const repository = String(trigger.repository ?? '').trim()
  if (repository) return repository
  return repo
}

function addUniqueKey(keys: string[], key: string): void {
  if (key && !keys.includes(key)) keys.push(key)
}

/** Unresolved `{{key}}` slots (and empty GitHub owner/repo). Does not treat live ids as missing. */
export function unresolvedFillIns(routines: FillInCarrier[]): RoutinePackFillIn[] {
  return remainingFillIns(routines.map(fillInSource))
}

/** Repo/channel ids (and existing tokens) an export will turn into fill-ins. */
export function previewRequiredFillIns(routines: FillInCarrier[]): RoutinePackFillIn[] {
  const keys: string[] = []
  for (const slot of unresolvedFillIns(routines)) {
    addUniqueKey(keys, slot.key)
  }
  for (const row of routines) {
    const trigger = triggerRecord(row.trigger)
    for (const [field, canonical] of Object.entries(ID_FIELD_CANONICAL)) {
      const text = String(trigger[field] ?? '').trim()
      if (text.length < 3 || text.startsWith('{{')) continue
      if (canonical === 'owner_repo' && !OWNER_REPO_RE.test(text)) continue
      addUniqueKey(keys, canonical)
    }
    const kind = String(trigger.kind ?? '')
    if (GITHUB_TRIGGER_KINDS.has(kind)) {
      const owner = resolvedOwnerRepo(trigger)
      if (!owner) addUniqueKey(keys, 'owner_repo')
      else if (!owner.startsWith('{{') && OWNER_REPO_RE.test(owner)) addUniqueKey(keys, 'owner_repo')
    }
  }
  return keys.map((key) => ({ key, label: fillInLabel(key), required: true }))
}

export function routinePendingFillInKeys(routine: RoutineFillState): string[] {
  if (routine.fill_in_keys?.length) return routine.fill_in_keys
  return scanFillInKeys([
    routine.name,
    routine.description,
    routine.instruction || routine.job,
    routine.trigger,
  ])
}

export function routineListStatus(routine: RoutineFillState & { active: boolean }): RoutineListStatus {
  const flagged = Boolean(routine.pending_fill) || (routine.fill_in_keys?.length ?? 0) > 0
  const hasFlags = routine.pending_fill !== undefined || routine.fill_in_keys !== undefined
  const unresolved =
    flagged ||
    (!hasFlags &&
      unresolvedFillIns([
        {
          name: routine.name || '',
          instruction: routine.instruction || routine.job || '',
          description: routine.description,
          job: routine.job,
          trigger: (routine.trigger || { kind: 'interval', seconds: 60 }) as RoutineTrigger,
        },
      ]).length > 0)
  if (unresolved) return 'pending-fill'
  if (routine.enabled ?? routine.active) return 'enabled'
  return 'paused'
}

export const routinePackStatus = routineListStatus

export function routineStatusLabel(status: RoutineListStatus): string {
  if (status === 'pending-fill') return 'Pending fill'
  if (status === 'enabled') return 'Enabled'
  return 'Paused'
}

export const routinePackStatusLabel = routineStatusLabel

/** Block turning a paused pending-fill routine on. Pausing an active row stays allowed. */
export function routineEnableGate(routine: RoutineFillState): { blocked: boolean; message: string | null } {
  if (routineListStatus({ ...routine, active: Boolean(routine.active) }) !== 'pending-fill') {
    return { blocked: false, message: null }
  }
  const keys = routinePendingFillInKeys(routine)
  const labels = keys.length ? keys.map((key) => fillInLabel(key)).join(', ') : 'the remaining slots'
  return {
    blocked: !routine.active,
    message: `Fill in ${labels} before enabling.`,
  }
}

export function filledMapping(raw: Record<string, string>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(raw)) {
    const name = String(key || '').trim()
    const text = String(value ?? '').trim()
    if (!name || !text) continue
    out[name] = text
  }
  return out
}

/**
 * Rows this import actually created and left inactive.
 * Skipped duplicates stay in `routines` so the list can name them, but Enable
 * must not PATCH those existing rows.
 */
export function routinesPendingEnable(
  result: Pick<RoutinePackImport, 'routines' | 'skipped'>,
): Routine[] {
  const skipped = new Set(
    (result.skipped || [])
      .map((row) => String(row.existing_routine_id || '').trim())
      .filter(Boolean),
  )
  return (result.routines || []).filter((row) => {
    const id = String(row?.id || '').trim()
    return Boolean(id) && row.active !== true && !skipped.has(id)
  })
}

/** Slots to show after import. Prefer the API list; scan created rows if it is empty. */
export function fillInsAfterImport(result: RoutinePackImport): RoutinePackFillIn[] {
  const created = routinesPendingEnable(result)
  if (!created.length) return []
  const declared = (result.fill_ins_remaining || []).filter((slot) => String(slot?.key || '').trim())
  if (declared.length) return declared
  return unresolvedFillIns(created)
}

export function enableBlockedReason(
  routines: FillInCarrier[],
  fillIns: Record<string, string>,
): string | null {
  const mapping = filledMapping(fillIns)
  const prepared = routines.map((row) =>
    fillInSource({
      name: applyFillIns(row.name, mapping),
      instruction: applyFillIns(row.instruction, mapping),
      description: applyFillIns(row.description || '', mapping),
      job: row.job,
      trigger: applyFillIns(row.trigger, mapping),
    }),
  )
  const leftover = remainingFillIns(prepared)
  if (!leftover.length) return null
  return incompleteFillInMessage(leftover)
}

export function mergeFillIns(...groups: Array<RoutinePackFillIn[] | undefined>): RoutinePackFillIn[] {
  const out: RoutinePackFillIn[] = []
  const seen = new Set<string>()
  for (const group of groups) {
    for (const slot of group || []) {
      const key = String(slot?.key || '').trim()
      if (!key || seen.has(key)) continue
      seen.add(key)
      out.push({ ...slot, key, label: slot.label || fillInLabel(key), required: slot.required !== false })
    }
  }
  return out
}

export function downloadRoutinesPack(pack: RoutinePack, filename?: string): void {
  const blob = new Blob([`${JSON.stringify(pack, null, 2)}\n`], {
    type: 'application/json',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  const agent = String(pack.agent_id || 'agent').replace(/[^\w.-]+/g, '-')
  anchor.href = url
  anchor.download = filename || `${agent}-routines-pack.json`
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function exportRoutinesPack(
  agentId: string,
  opts: { routineIds?: string[]; includePresets?: boolean } = {},
): Promise<RoutinePack> {
  const ids = (opts.routineIds || []).map((id) => String(id).trim()).filter(Boolean)
  if (ids.length || opts.includePresets) {
    return apiPost<RoutinePack>(routinesPackPath(agentId), {
      routine_ids: ids.length ? ids : undefined,
      presets: opts.includePresets ? 1 : undefined,
    })
  }
  return apiGet<RoutinePack>(routinesPackPath(agentId))
}

export async function importRoutinesPack(
  agentId: string,
  pack: unknown,
  fillIns?: Record<string, string>,
): Promise<RoutinePackImport> {
  const mapping = filledMapping(fillIns || {})
  const body: Record<string, unknown> = { pack }
  if (Object.keys(mapping).length) body.fill_ins = mapping
  return apiPost<RoutinePackImport>(routinesImportPath(agentId), body)
}

export async function validateRoutinesPack(pack: unknown): Promise<RoutinePack> {
  return apiPost<RoutinePack>(ROUTINES_PACK_VALIDATE_URL, pack)
}

/** Substitute leftover slots. Does not enable — enable is a separate step. */
export async function applyImportedRoutineFillIns(
  agentId: string,
  routines: Routine[],
  fillIns: Record<string, string>,
): Promise<Routine[]> {
  const mapping = filledMapping(fillIns)
  if (!Object.keys(mapping).length) return routines
  const updated: Routine[] = []
  for (const row of routines) {
    const next = {
      name: applyFillIns(row.name, mapping),
      instruction: applyFillIns(row.instruction, mapping),
      trigger: applyFillIns(row.trigger, mapping),
    }
    const changed =
      next.name !== row.name ||
      next.instruction !== row.instruction ||
      JSON.stringify(next.trigger) !== JSON.stringify(row.trigger)
    if (!changed) {
      updated.push(row)
      continue
    }
    updated.push(await updateRoutine(agentId, row.id, next))
  }
  return updated
}

/**
 * Apply fill-ins and set `active: true` only when every required slot is filled.
 * Incomplete input throws and does not PATCH.
 */
export async function enableImportedRoutines(
  agentId: string,
  routines: Routine[],
  fillIns: Record<string, string>,
): Promise<Routine[]> {
  const blocked = enableBlockedReason(routines, fillIns)
  if (blocked) {
    const mapping = filledMapping(fillIns)
    const prepared = routines.map((row) =>
      fillInSource({
        name: applyFillIns(row.name, mapping),
        instruction: applyFillIns(row.instruction, mapping),
        trigger: applyFillIns(row.trigger, mapping),
      }),
    )
    throw new IncompleteFillInsError(remainingFillIns(prepared))
  }
  const mapping = filledMapping(fillIns)
  const updated: Routine[] = []
  for (const row of routines) {
    try {
      updated.push(
        await updateRoutine(agentId, row.id, {
          name: applyFillIns(row.name, mapping),
          instruction: applyFillIns(row.instruction, mapping),
          trigger: applyFillIns(row.trigger, mapping),
          active: true,
        }),
      )
    } catch (err) {
      if (!updated.length) throw err
      const reason = err instanceof Error ? err.message : 'Could not enable routines.'
      throw new Error(
        `Enabled ${updated.length} of ${routines.length} routines before a save failed: ${reason}`,
      )
    }
  }
  return updated
}

/**
 * OpenMousBot operate-list → navbar options (#102).
 *
 * Maps GET /api/bots / operate list payloads to id + name. Nested
 * `messages` (and any other bulky fields) are dropped so a 387KB dump
 * cannot land in the routing picker.
 */

import { isOpenMousBotKind } from './remoteKinds'

export const OMB_BOT_REQUIRED_GAP = 'omb_bot_required'

export const OMB_NO_AGENTS_WARNING =
  'No OpenMousBot agents listed. Pick an agent in the navbar — send will not guess a specialist.'

export const OMB_SELECT_AGENT_WARNING =
  'Select an OpenMousBot agent. Send needs the listed bot id (omb_bot_required).'

export interface OmbBotOption {
  id: string
  name: string
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

function looksLikeRemoteSpec(value: unknown): boolean {
  const rec = asRecord(value)
  if (!rec) return false
  return (
    rec.object === 'remote' ||
    typeof rec.base_url === 'string' ||
    typeof rec.host_label === 'string' ||
    rec.configured === true ||
    rec.configured === false
  )
}

function botList(payload: unknown): unknown[] {
  if (Array.isArray(payload)) {
    return payload.some(looksLikeRemoteSpec) ? [] : payload
  }
  const rec = asRecord(payload)
  if (!rec) return []
  if (Array.isArray(rec.bots)) return rec.bots
  if (Array.isArray(rec.agents)) return rec.agents
  if (Array.isArray(rec.members)) return rec.members
  // Hermes nests its model list one level deeper (`models: {object, data}`) —
  // the same envelope `sessionsFromOperateResult` unwraps for sessions.
  if (Array.isArray(rec.models)) return rec.models
  const nestedModels = asRecord(rec.models)
  if (nestedModels) {
    if (Array.isArray(nestedModels.data)) return nestedModels.data
    if (Array.isArray(nestedModels.models)) return nestedModels.models
    if (Array.isArray(nestedModels.agents)) return nestedModels.agents
    if (Array.isArray(nestedModels.bots)) return nestedModels.bots
  }
  if (Array.isArray(rec.data)) {
    return rec.data.some(looksLikeRemoteSpec) ? [] : rec.data
  }
  const nested = asRecord(rec.data)
  if (nested) {
    if (Array.isArray(nested.bots)) return nested.bots
    if (Array.isArray(nested.agents)) return nested.agents
  }
  return []
}

/** Network list → compact {id, name} rows. Never copies `messages`. */
export function ombBotsFromOperate(payload: unknown): OmbBotOption[] {
  const out: OmbBotOption[] = []
  const seen = new Set<string>()
  for (const item of botList(payload)) {
    if (typeof item === 'string') {
      const id = item.trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      out.push({ id, name: id })
      continue
    }
    const rec = asRecord(item)
    if (!rec) continue
    const id = rec.id != null ? String(rec.id).trim() : rec.bot_id != null ? String(rec.bot_id).trim() : ''
    if (!id || seen.has(id) || isOpenMousBotKind(id)) continue
    seen.add(id)
    const nameRaw = rec.name != null ? String(rec.name).trim() : rec.title != null ? String(rec.title).trim() : ''
    out.push({ id, name: nameRaw || id })
  }
  return out
}

export function ombNavbarOptions(bots: readonly OmbBotOption[]): Array<{ id: string; label: string }> {
  return bots.map((bot) => ({ id: bot.id, label: bot.name || bot.id }))
}

/** True for Chief of Staff / CoS / chief-of-staff / chiefOfStaff spellings. */
export function isChiefOfStaffName(value: string): boolean {
  const compact = (value || '').trim().toLowerCase().replace(/[\s_-]+/g, '')
  return compact === 'cos' || compact === 'chiefofstaff'
}

/** The workspace Chief of Staff bot id, or '' when no listed bot is the CoS. */
export function ombChiefOfStaffId(bots: readonly OmbBotOption[]): string {
  for (const bot of bots) {
    if (isChiefOfStaffName(bot.name) || isChiefOfStaffName(bot.id)) return bot.id
  }
  return ''
}

/**
 * The bot id a send should target. An explicit pick always wins; otherwise the
 * workspace Chief of Staff is the default. '' only when neither exists.
 */
export function ombSendTarget(
  sessionId: string,
  remoteId: string,
  bots: readonly OmbBotOption[] = [],
): string {
  const session = sessionId.trim()
  if (session && !isOpenMousBotKind(session) && session !== remoteId.trim()) return session
  return ombChiefOfStaffId(bots)
}

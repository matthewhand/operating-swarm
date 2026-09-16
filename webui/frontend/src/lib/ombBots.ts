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

export function ombSendTarget(sessionId: string, remoteId: string): string {
  const session = sessionId.trim()
  if (!session) return ''
  if (isOpenMousBotKind(session) || session === remoteId.trim()) return ''
  return session
}

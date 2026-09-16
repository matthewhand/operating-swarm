/**
 * Remote thread/session list for harnesses that advertise ``capabilities.sessions``
 * (AnythingLLM threads, Hermes sessions). Resume key is the row ``id``.
 */

import { operateRemote, type RemoteOperateResult } from './api'
import type { RemoteEntry } from './remotesCatalog'
import type { MemberSession } from './sessionPicker'

export interface RemoteThreadRow {
  id: string
  title: string
  snippet: string
  updated_at?: string
  channel?: string
}

const SESSION_KINDS = new Set(['anythingllm', 'hermes'])

export function remoteListsSessions(
  remote: Pick<RemoteEntry, 'id' | 'kind'> & { capabilities?: { sessions?: boolean } },
): boolean {
  if (remote.capabilities?.sessions) return true
  const kind = (remote.kind || remote.id || '').trim().toLowerCase()
  return SESSION_KINDS.has(kind)
}

export function remoteChatTurnParams(remoteId: string, sessionId?: string) {
  const sid = (sessionId || '').trim()
  return {
    remote: remoteId,
    name: remoteId,
    op: 'send' as const,
    ...(sid ? { session_id: sid, target: sid } : {}),
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

export function sessionsFromOperateResult(
  result: RemoteOperateResult | undefined,
): RemoteThreadRow[] {
  if (!result?.data) return []
  const raw = result.data
  let list: unknown = raw
  const rec = asRecord(raw)
  if (rec) {
    if (Array.isArray(rec.sessions)) list = rec.sessions
    else if (Array.isArray(rec.data)) list = rec.data
  }
  if (!Array.isArray(list)) return []
  const out: RemoteThreadRow[] = []
  const seen = new Set<string>()
  for (const item of list) {
    if (typeof item === 'string') {
      const id = item.trim()
      if (!id || seen.has(id)) continue
      seen.add(id)
      out.push({ id, title: id, snippet: '' })
      continue
    }
    const row = asRecord(item)
    if (!row) continue
    const id = String(row.id ?? row.session_id ?? '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push({
      id,
      title: String(row.title || row.name || id).trim() || id,
      snippet: String(row.snippet || row.preview || '').trim(),
      updated_at: String(row.updated_at || row.updatedAt || '').trim() || undefined,
      channel: String(row.channel || '').trim() || undefined,
    })
  }
  return out
}

export function filterRemoteSessionRows<
  T extends { id?: string; title?: string; snippet?: string; channel?: string },
>(rows: readonly T[], query: string): T[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...rows]
  return rows.filter((row) =>
    [row.id, row.title, row.snippet, row.channel].some((value) =>
      (value || '').toLowerCase().includes(q),
    ),
  )
}

export function memberSessionsFromRemoteOperate(
  remote: Pick<RemoteEntry, 'id' | 'title' | 'kind'>,
  result: RemoteOperateResult | undefined,
): MemberSession[] {
  return sessionsFromOperateResult(result).map((row, index) => ({
    id: `${remote.id}:${row.id}`,
    groupId: remote.id,
    groupKind: 'remote',
    memberId: row.id,
    title: row.title || row.id,
    snippet: row.snippet || row.channel || '',
    status: 'finished',
    startedAt: index,
    href: `/chat?remote=${encodeURIComponent(remote.id)}&session=${encodeURIComponent(row.id)}`,
  }))
}

export async function fetchRemoteThreadSessions(
  remote: Pick<RemoteEntry, 'id' | 'title' | 'kind'> & { capabilities?: { sessions?: boolean } },
  query = '',
): Promise<MemberSession[]> {
  const result = await operateRemote(
    remote.id,
    { op: 'list', ...(query.trim() ? { query: query.trim() } : {}) },
    { timeoutMs: 15000 },
  )
  return memberSessionsFromRemoteOperate(remote, result)
}

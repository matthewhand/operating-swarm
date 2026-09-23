/**
 * Remote thread/session list for harnesses that advertise ``capabilities.sessions``
 * (Letta agents, Open WebUI chats, Flowise chatflows, n8n workflows, AnythingLLM threads, Hermes sessions). Resume key is the row ``id``.
 */

import { operateRemote, type RemoteOperateResult } from './api'
import { parseStartedAt } from './avatarStack'
import { ombBotsFromOperate, ombNavbarOptions } from './ombBots'
import type { RemoteEntry } from './remotesCatalog'
import type { MemberSession } from './sessionPicker'

/** Operate-list rows that are agents/bots on the far side (navbar 2nd dropdown). */
export function remoteAgentsFromOperate(payload: unknown): Array<{ id: string; label: string }> {
  return ombNavbarOptions(ombBotsFromOperate(payload))
}

export interface RemoteThreadRow {
  id: string
  title: string
  snippet: string
  updated_at?: string
  created_at?: string
  channel?: string
}

const SESSION_KINDS = new Set(['letta', 'openwebui', 'open-webui', 'open_webui', 'owui', 'flowise', 'flowiseai', 'n8n', 'n8n-io', 'anythingllm', 'hermes'])

export function remoteListsSessions(
  remote: Pick<RemoteEntry, 'id'> & { kind?: string; capabilities?: { sessions?: boolean } },
): boolean {
  if (remote.capabilities?.sessions) return true
  const kind = (remote.kind || remote.id || '').trim().toLowerCase()
  return SESSION_KINDS.has(kind)
}

/**
 * #852 — the session a session-capable remote should land on when the user
 * clicks the agent without choosing one: running first (same order the
 * pickers use), then newest. `null` when there is nothing to auto-select —
 * the caller falls through to a fresh send instead of opening a modal.
 */
export function mostRecentRemoteSession(
  sessions: readonly MemberSession[],
): MemberSession | null {
  if (!sessions || sessions.length === 0) return null
  return [...sessions].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'running' ? -1 : 1
    return b.startedAt - a.startedAt
  })[0]
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
    // #810: real session rows win (TrueForge attaches data.sessions); when a
    // backend stamps rows_are='agents' the agent rows must NEVER present as
    // sessions — resuming one 404s on the remote (#425).
    if (Array.isArray(rec.sessions)) list = rec.sessions
    else if (rec.rows_are === 'agents') list = []
    else if (Array.isArray(rec.data)) list = rec.data
    else if (Array.isArray(rec.members)) list = rec.members
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
    // #796/#787: herdr members carry the routing target in `name` and the
    // human label in `display` — the pane id stays the id, the display name
    // becomes the title the operator sees.
    const id = String(row.id ?? row.session_id ?? row.name ?? '').trim()
    if (!id || seen.has(id)) continue
    seen.add(id)
    out.push({
      id,
      title: String(row.title || row.display || row.name || id).trim() || id,
      snippet: String(row.snippet || row.preview || '').trim(),
      updated_at: String(row.updated_at || row.updatedAt || '').trim() || undefined,
      created_at: String(row.created_at || row.createdAt || '').trim() || undefined,
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
  return sessionsFromOperateResult(result).map((row) => ({
    id: `${remote.id}:${row.id}`,
    groupId: remote.id,
    groupKind: 'remote',
    memberId: row.id,
    title: row.title || row.id,
    snippet: row.snippet || row.channel || '',
    status: 'finished',
    // #1099/#1100: real activity time when the harness exposes it (TrueForge
    // sends updated_at, older harnesses only created_at). Zero otherwise —
    // formatters render epoch-0 as *no stamp*, never a literal 0.
    startedAt: parseStartedAt(row.updated_at || row.created_at, 0),
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

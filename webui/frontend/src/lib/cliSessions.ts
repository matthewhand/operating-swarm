/**
 * REQ-104 — CLI Select session (provider list + paste id + design A bind).
 *
 * Activity SoT: provider `updated_at` when the CLI can list; else last swarm-touch.
 * Prior foreign history is a UI pill (`kind: prior_history`), not CLI turns.
 */

import { folderRequestValue } from './agentFolder'
import { apiGet, apiPost } from './api'
import {
  agentIdFromBlueprint,
  conversationIdForAgent,
  setConversationIdForAgent,
} from './agentChat'
import { messagesFromThreadPayload } from './transcriptReconstruct'

export { setConversationIdForAgent } from './agentChat'

const SESSION_ID_RE = /^[A-Za-z0-9._:-]{1,128}$/
const SECRET_PREFIX = /^(sk-|gsk_|xai-|AIza|ghp_|github_pat_|xox[baprs]-|Bearer )/i

/** Mirror of swarm.core.cli_sessions.sanitize_cli_session_id (ids only, no secrets). */
export function sanitizeCliSessionId(raw: string | null | undefined): string | null {
  if (raw == null) return null
  const text = String(raw).trim()
  if (!text || text.length > 128) return null
  if (/[= \n\t/\\]/.test(text)) return null
  if (SECRET_PREFIX.test(text)) return null
  if (!SESSION_ID_RE.test(text)) return null
  return text
}

export const CLI_SESSION_SWITCHED_EVENT = 'swarm:cli-session-switched'
export const RECENT_SESSION_LIMIT = 10

export type CliSessionSource = 'provider' | 'swarm'

export interface CliProviderSession {
  id: string
  title: string
  snippet: string
  updated_at: string
  source: CliSessionSource
  /** Owning folder/cwd hint when the provider store exposes one (qwen). */
  folder?: string
}

export interface CliSessionList {
  object: 'cli_session_list'
  agent_id: string
  cli: string
  can_list: boolean
  list_capability?: 'works' | 'paste-only' | 'unsupported'
  sessions: CliProviderSession[]
  recent: CliProviderSession[]
  empty_reason: string | null
  warning?: string | null
  activity_sot: 'provider' | 'swarm'
}

export interface CliSessionSelectResult {
  object: 'cli_session_select'
  agent_id: string
  cli: string
  conversation_id: string
  cli_session_id: string | null
  messages: Array<{
    role: string
    content: string
    kind?: string
    from_conversation_id?: string
  }>
  turns?: Array<{ role: string; content: string; kind?: string }>
  ui_events?: Array<{ role: string; content: string; kind?: string; ts?: string }>
  status: string
  collapsed_prior: boolean
  import: 'none' | 'full' | 'partial'
  folder?: string | null
  git_branch?: string | null
  same_session?: boolean
}

export async function fetchCliSessions(agentId: string, cli: string): Promise<CliSessionList> {
  const folder = folderRequestValue(agentId)
  const qs = new URLSearchParams({
    agent: agentIdFromBlueprint(agentId),
    cli,
  })
  if (folder) qs.set('folder', folder)
  return apiGet<CliSessionList>(`/v1/cli-sessions/?${qs.toString()}`)
}

/** Newest provider activity across sessions+recent as epoch ms (rail timestamps, #67). */
export function latestCliActivityMs(
  list: { sessions?: Array<{ updated_at?: string | null }>; recent?: Array<{ updated_at?: string | null }> } | null | undefined,
): number | null {
  if (!list) return null
  let best: number | null = null
  for (const row of [...(list.sessions ?? []), ...(list.recent ?? [])]) {
    const raw = row?.updated_at
    if (!raw) continue
    const ms = Date.parse(String(raw))
    if (Number.isFinite(ms) && (best == null || ms > best)) best = ms
  }
  return best
}

export async function selectCliSession(opts: {
  agentId: string
  cli: string
  sessionId?: string | null
  startNew?: boolean
  fromConversationId?: string
  title?: string
  snippet?: string
  folder?: string | null
}): Promise<CliSessionSelectResult> {
  const from =
    (opts.fromConversationId || '').trim() || conversationIdForAgent(opts.agentId)
  const folder = (opts.folder || '').trim() || folderRequestValue(opts.agentId)
  const data = await apiPost<CliSessionSelectResult>('/v1/cli-sessions/select/', {
    agent: agentIdFromBlueprint(opts.agentId),
    cli: opts.cli,
    session_id: opts.startNew ? undefined : opts.sessionId,
    start_new: Boolean(opts.startNew),
    from_conversation_id: from,
    title: opts.title || '',
    snippet: opts.snippet || '',
    ...(folder ? { folder } : {}),
  })
  if (data.conversation_id) {
    setConversationIdForAgent(opts.agentId, data.conversation_id)
  }
  return {
    ...data,
    messages: messagesFromThreadPayload(data),
  }
}

export function dispatchCliSessionSwitched(detail: {
  agentId: string
  conversationId: string
  status: string
}): void {
  try {
    window.dispatchEvent(new CustomEvent(CLI_SESSION_SWITCHED_EVENT, { detail }))
  } catch {
    /* tests / non-browser */
  }
}

/** Relative activity stamp: `2m ago` / `Yesterday` / date. */
export function formatActivityAge(updatedAt: string | number, nowMs = Date.now()): string {
  if (!updatedAt) return ''
  const ms = typeof updatedAt === 'number' ? updatedAt : Date.parse(updatedAt)
  if (!Number.isFinite(ms)) return ''
  const delta = Math.max(0, nowMs - ms)
  const minute = 60_000
  const hour = 60 * minute
  const day = 24 * hour
  if (delta < minute) return 'just now'
  if (delta < hour) return `${Math.floor(delta / minute)}m ago`
  if (delta < day) return `${Math.floor(delta / hour)}h ago`
  const startToday = new Date(nowMs)
  startToday.setHours(0, 0, 0, 0)
  const startStamp = new Date(ms)
  startStamp.setHours(0, 0, 0, 0)
  const days = Math.round((startToday.getTime() - startStamp.getTime()) / day)
  if (days === 1) return 'Yesterday'
  if (days < 7) return `${days}d ago`
  return startStamp.toLocaleDateString()
}

export function looksLikeSessionId(raw: string): boolean {
  return sanitizeCliSessionId(raw) != null
}

export function filterCliSessions(
  sessions: readonly CliProviderSession[],
  query: string,
): CliProviderSession[] {
  const q = query.trim().toLowerCase()
  if (!q) return [...sessions]
  return sessions.filter((row) => {
    const title = (row.title || '').toLowerCase()
    const snippet = (row.snippet || '').toLowerCase()
    const id = (row.id || '').toLowerCase()
    return title.includes(q) || snippet.includes(q) || id.includes(q)
  })
}

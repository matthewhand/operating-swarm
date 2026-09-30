/**
 * REQ-105 — Django-backed sessions for any agent.
 *
 * Shared picker chrome with #468. This module lists / creates swarm-owned
 * rows only. It does not browse CLI provider sessions.
 */

import { apiGet, apiPost } from './api'
import { agentIdFromBlueprint, setConversationIdForAgent } from './agentChat'
import { formatRailTimestamp } from './chatTime'
import {
  listAgentSessions,
  upsertAgentSession,
  type AgentSession,
  type AgentSessionStatus,
} from './scaleOutSessions'

export const AGENT_SESSIONS_EVENT = 'swarm:agent-sessions'

export interface DjangoAgentSession {
  id: string
  conversation_id: string
  agent_id: string
  title: string
  snippet: string
  created_at: string
  updated_at: string
  labels: string[]
  cli_session_id: string | null
  status: AgentSessionStatus
  started_at?: string
  updated_at_ms?: number
  started_at_ms?: number
  empty?: boolean
}

export interface AgentSessionList {
  object: string
  agent_id: string
  sessions: DjangoAgentSession[]
}

function asStatus(value: unknown): AgentSessionStatus {
  return value === 'running' ? 'running' : 'finished'
}

function parseIsoMs(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value !== 'string' || !value.trim()) return fallback
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

export function parseDjangoSession(value: unknown, agentId: string): DjangoAgentSession | null {
  if (!value || typeof value !== 'object') return null
  const row = value as Record<string, unknown>
  const id = String(row.id || row.conversation_id || '').trim()
  if (!id) return null
  const created = typeof row.created_at === 'string' ? row.created_at : ''
  const updated = typeof row.updated_at === 'string' ? row.updated_at : created
  return {
    id,
    conversation_id: String(row.conversation_id || id),
    agent_id: typeof row.agent_id === 'string' && row.agent_id ? row.agent_id : agentId,
    title: typeof row.title === 'string' && row.title.trim() ? row.title : 'Session 1',
    snippet: typeof row.snippet === 'string' ? row.snippet : '',
    created_at: created,
    updated_at: updated,
    labels: Array.isArray(row.labels)
      ? row.labels.filter((item): item is string => typeof item === 'string')
      : [],
    cli_session_id: typeof row.cli_session_id === 'string' && row.cli_session_id
      ? row.cli_session_id
      : null,
    status: asStatus(row.status),
    started_at: typeof row.started_at === 'string' ? row.started_at : created,
    updated_at_ms:
      typeof row.updated_at_ms === 'number' ? row.updated_at_ms : parseIsoMs(updated),
    started_at_ms:
      typeof row.started_at_ms === 'number' ? row.started_at_ms : parseIsoMs(created),
    empty: row.empty === true,
  }
}

export function djangoSessionToPicker(row: DjangoAgentSession): AgentSession {
  const startedAt = row.started_at_ms || parseIsoMs(row.created_at)
  const updatedAt = row.updated_at_ms || parseIsoMs(row.updated_at, startedAt)
  return {
    id: row.id,
    agentId: row.agent_id,
    title: row.title,
    snippet: row.snippet,
    status: row.status,
    startedAt,
    updatedAt,
  }
}

/** Merge Django rows with leftover local scale-out sessions (same picker). */
export function mergePickerSessions(
  agentId: string,
  django: readonly DjangoAgentSession[],
): AgentSession[] {
  const agent = agentIdFromBlueprint(agentId)
  const fromDjango = django.map(djangoSessionToPicker)
  const seen = new Set(fromDjango.map((row) => row.id))
  const local = listAgentSessions(agent).filter((row) => !seen.has(row.id))
  return [...fromDjango, ...local]
}

export function sessionRelativeLabel(
  session: { updatedAt?: number; startedAt?: number },
  nowMs: number = Date.now(),
): string | null {
  return formatRailTimestamp(session.updatedAt || session.startedAt || 0, nowMs)
}

export function emitAgentSessionsChanged(agentId?: string): void {
  try {
    window.dispatchEvent(new CustomEvent(AGENT_SESSIONS_EVENT, { detail: { agentId } }))
  } catch {
    /* jsdom / SSR */
  }
}

export async function fetchAgentSessions(agentId: string): Promise<DjangoAgentSession[]> {
  const agent = agentIdFromBlueprint(agentId)
  try {
    const data = await apiGet<AgentSessionList>(
      `/v1/agents/${encodeURIComponent(agent)}/sessions/`,
    )
    const rows = Array.isArray(data?.sessions) ? data.sessions : []
    return rows
      .map((row) => parseDjangoSession(row, agent))
      .filter((row): row is DjangoAgentSession => row != null)
  } catch {
    return []
  }
}

export async function createAgentSession(
  agentId: string,
  opts?: { title?: string; labels?: string[] },
): Promise<DjangoAgentSession | null> {
  const agent = agentIdFromBlueprint(agentId)
  try {
    const data = await apiPost<DjangoAgentSession>(
      `/v1/agents/${encodeURIComponent(agent)}/sessions/`,
      { new: true, empty: true, title: opts?.title || '', labels: opts?.labels || [] },
    )
    const parsed = parseDjangoSession(data, agent)
    if (parsed?.id) {
      setConversationIdForAgent(agent, parsed.id)
      // #1709: the rail row is the only place a chat shows up as a chat, and it
      // reads the scale-out cache — so a created row has to land there or the
      // sidepane cannot show that a chat was added. The Django row stays
      // canonical; this is the same derived cache the picker merges from, and
      // `mergePickerSessions` dedupes the two by id.
      //
      // Filed under `agent` rather than `parsed.agent_id`: every reader
      // normalizes to the blueprint id (the rail indexes `loadAllAgentSessions`
      // by its own row id, `mergePickerSessions` reads under
      // `agentIdFromBlueprint`), so the server's echo is not a safe key.
      upsertAgentSession({ ...djangoSessionToPicker(parsed), agentId: agent })
    }
    emitAgentSessionsChanged(agent)
    return parsed
  } catch {
    return null
  }
}

export async function loadPickerSessions(agentId: string): Promise<AgentSession[]> {
  const django = await fetchAgentSessions(agentId)
  return mergePickerSessions(agentId, django)
}

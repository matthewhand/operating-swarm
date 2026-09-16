/**
 * Configured remotes for the AGENTS rail (REQ-68).
 *
 * Reads GET /v1/remotes/ only. Never health-probes or operate() — those hit
 * live LAN. Compatible with remotes opt-in (#384): default catalog rows
 * without agents stay off the rail.
 *
 * UI label for the omb kind is OpenMousBot, never OMB.
 */

import { parseStartedAt } from './avatarStack'

export const REMOTES_URL = '/v1/remotes/'
/** Optional local fixture (no LAN). Checked before GET /v1/remotes/. */
export const REMOTES_FIXTURE_URL = '/remotes_catalog.json'
export const OPENMOUSBOT_LABEL = 'OpenMousBot'
export const OPENMOUSBOT_IDS = new Set(['omb', 'openmousbot', 'openmausbot'])

export interface RemoteAgent {
  id: string
  name: string
  role?: string
  started_at?: string
  startedAt?: number
  working?: boolean
  status?: 'running' | 'finished'
  snippet?: string
}

export interface RemoteEntry {
  id: string
  kind: string
  title: string
  configured: boolean
  agents: RemoteAgent[]
  capabilities?: { sessions?: boolean; list?: boolean; send?: boolean }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null
}

/** Public label. Internal ids may stay `omb`. */
export function remoteDisplayName(remote: {
  id?: string
  title?: string
  name?: string
  kind?: string
}): string {
  const id = String(remote.id || remote.kind || '').trim().toLowerCase()
  if (OPENMOUSBOT_IDS.has(id)) return OPENMOUSBOT_LABEL
  const raw = String(remote.title || remote.name || remote.id || '').trim()
  if (!raw) return 'Remote'
  if (OPENMOUSBOT_IDS.has(raw.toLowerCase()) || /^omb$/i.test(raw) || /openmausbot/i.test(raw)) {
    return OPENMOUSBOT_LABEL
  }
  return raw
}

export function remoteHideId(remoteId: string): string {
  return `remote:${remoteId}`
}

function parseAgent(raw: unknown, index: number): RemoteAgent | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const name =
    typeof rec.name === 'string' && rec.name.trim()
      ? rec.name.trim()
      : remoteDisplayName({ id, title: typeof rec.title === 'string' ? rec.title : '' })
  const role = typeof rec.role === 'string' ? rec.role : undefined
  const started =
    rec.started_at ?? rec.startedAt ?? rec.created_at ?? rec.updated_at ?? index
  const status = rec.status === 'running' || rec.status === 'finished' ? rec.status : undefined
  const snippet = typeof rec.snippet === 'string' ? rec.snippet : undefined
  return {
    id,
    name,
    role,
    started_at: typeof rec.started_at === 'string' ? rec.started_at : undefined,
    startedAt: parseStartedAt(started, index),
    working: rec.working === true || status === 'running',
    status,
    snippet,
  }
}

function agentList(rec: Record<string, unknown>): unknown[] {
  if (Array.isArray(rec.agents)) return rec.agents
  if (Array.isArray(rec.bots)) return rec.bots
  if (Array.isArray(rec.members)) return rec.members
  if (Array.isArray(rec.workers)) return rec.workers
  return []
}

export function parseRemote(raw: unknown): RemoteEntry | null {
  const rec = asRecord(raw)
  if (!rec) return null
  if (rec.object === 'blueprint' || rec.object === 'team_roster' || rec.object === 'team') {
    return null
  }
  const id = typeof rec.id === 'string' ? rec.id.trim() : ''
  if (!id) return null
  const source = typeof rec.source === 'string' ? rec.source : ''
  const configured =
    rec.configured === true || (source !== '' && source !== 'default')
  const kind =
    typeof rec.kind === 'string' && rec.kind.trim()
      ? rec.kind.trim()
      : id
  const title = remoteDisplayName({
    id,
    kind,
    title: typeof rec.title === 'string' ? rec.title : undefined,
    name: typeof rec.name === 'string' ? rec.name : undefined,
  })
  const agents = agentList(rec)
    .map((row, index) => parseAgent(row, index))
    .filter((row): row is RemoteAgent => row !== null)
  const capsRec = asRecord(rec.capabilities)
  const capabilities = capsRec
    ? {
        sessions: capsRec.sessions === true,
        list: capsRec.list === true,
        send: capsRec.send === true,
      }
    : undefined
  return { id, kind, title, configured, agents, capabilities }
}

/** Always listed on the conversation rail (Hermes + OpenMousBot). */
export const PINNED_RAIL_REMOTE_IDS = new Set(['hermes', 'omb', 'openmousbot', 'openmausbot'])

/** Pinned remotes, plus any the operator added or that already report agents. */
export function isRailRemote(remote: RemoteEntry): boolean {
  const id = String(remote.id || '').trim().toLowerCase()
  if (PINNED_RAIL_REMOTE_IDS.has(id) || PINNED_RAIL_REMOTE_IDS.has(String(remote.kind || '').toLowerCase())) {
    return true
  }
  return remote.configured || remote.agents.length > 0
}

export function parseRemotes(payload: unknown): RemoteEntry[] {
  if (Array.isArray(payload)) {
    return payload.map(parseRemote).filter((row): row is RemoteEntry => row !== null)
  }
  const rec = asRecord(payload)
  if (!rec) return []
  const list = Array.isArray(rec.data)
    ? rec.data
    : Array.isArray(rec.configured)
      ? rec.configured
      : null
  if (!list) return []
  return list.map(parseRemote).filter((row): row is RemoteEntry => row !== null)
}

export function parseRailRemotes(payload: unknown): RemoteEntry[] {
  return parseRemotes(payload).filter(isRailRemote)
}

/**
 * Optional /remotes_catalog.json, then GET /v1/remotes/ — list only.
 * Empty on auth/network/unexpected shape. Does not POST health or operate
 * (no live LAN).
 */
export async function fetchConfiguredRemotes(): Promise<RemoteEntry[]> {
  for (const url of [REMOTES_FIXTURE_URL, REMOTES_URL]) {
    try {
      const response = await fetch(url, { headers: { Accept: 'application/json' } })
      if (!response.ok) continue
      const parsed = parseRailRemotes(await response.json())
      if (parsed.length > 0) return parsed
    } catch {
      // Try the next candidate; empty list is the last resort.
    }
  }
  return []
}

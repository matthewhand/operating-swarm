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
import { ApiThrottleError, coalescedRemotesFetch, isThrottleError } from './api'

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
  /** #601: server-stamped activity instant (epoch ms), absent when unknown. */
  lastMessageAt?: number
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
  return {
    id,
    kind,
    title,
    configured,
    agents,
    capabilities,
    ...parseLastMessageAt(rec),
  }
}

/** #601: server stamps ISO-8601 or epoch-ms; normalise to epoch ms or absent. */
function parseLastMessageAt(rec: Record<string, unknown>): { lastMessageAt: number } | Record<string, never> {
  const raw = rec.last_message_at ?? rec.lastMessageAt
  if (typeof raw === 'number' && Number.isFinite(raw) && raw > 0) return { lastMessageAt: raw }
  if (typeof raw === 'string' && raw.trim()) {
    const parsed = Date.parse(raw)
    if (Number.isFinite(parsed)) return { lastMessageAt: parsed }
  }
  return {}
}

/**
 * Historic pin set (Hermes + OpenMousBot). Kept for callers that still
 * special-case those kinds. It does **not** force unconfigured catalog
 * rows onto the rail — that produced a chat seat whose only reply was
 * "not added as a remote — catalog placeholder" (issue #430).
 */
export const PINNED_RAIL_REMOTE_IDS = new Set(['hermes', 'omb', 'openmousbot', 'openmausbot'])

/** Operator-added remotes, or rows that already report agents. */
export function isRailRemote(remote: RemoteEntry): boolean {
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
  // #581: optional fixture first (static file — not throttled), then the
  // shared coalesced GET /v1/remotes/ instead of an independent fetch.
  try {
    const response = await fetch(REMOTES_FIXTURE_URL, {
      headers: { Accept: 'application/json' },
    })
    if (response.ok) {
      const parsed = parseRailRemotes(await response.json())
      if (parsed.length > 0) return parsed
    }
  } catch {
    // Fixture is optional; fall through to the API.
  }
  try {
    const payload = await coalescedRemotesFetchWithThrottleRetry()
    return parseRailRemotes(payload)
  } catch (err) {
    // #680: a swallowed 429 used to be cached by react-query as a truthful
    // empty list — the rail's Remotes section stayed missing until a manual
    // reload. Re-throw so the query lands in the error state (retryable),
    // never fabricate an empty result from a failure.
    if (isThrottleError(err)) throw err
    return []
  }
}

/**
 * #680: the coalesced GET with bounded throttle patience.
 *
 * A 429 means the burst tripped the server throttle — the data exists, we
 * just asked too fast. Wait out the server's Retry-After (capped) and retry
 * a bounded number of times so the section self-heals without a manual
 * reload. A genuine failure still surfaces after the budget is spent.
 */
const THROTTLE_RETRY_CAP_SECONDS = 20
const THROTTLE_MAX_ATTEMPTS = 3

function throttleWaitMs(err: ApiThrottleError, attempt: number): number {
  const seconds = Math.min(
    err.retryAfterSeconds > 0 ? err.retryAfterSeconds : 2 ** attempt,
    THROTTLE_RETRY_CAP_SECONDS,
  )
  return seconds * 1_000
}

export async function coalescedRemotesFetchWithThrottleRetry(): Promise<
  ReturnType<typeof coalescedRemotesFetch>
> {
  for (let attempt = 0; ; attempt += 1) {
    try {
      return await coalescedRemotesFetch()
    } catch (err) {
      if (!isThrottleError(err) || attempt >= THROTTLE_MAX_ATTEMPTS - 1) throw err
      await new Promise((resolve) => setTimeout(resolve, throttleWaitMs(err, attempt)))
    }
  }
}

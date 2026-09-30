/**
 * Remote thread/session list for harnesses that advertise ``capabilities.sessions``
 * (Open WebUI chats, Flowise chatflows, n8n workflows, AnythingLLM threads,
 * Hermes sessions, Octop threads, OpenMuse tasks). Resume key is the row ``id``.
 */

import { buildHeaders, operateRemote, type RemoteOperateResult } from './api'
import { parseStartedAt } from './avatarStack'
import { ombBotsFromOperate, ombNavbarOptions } from './ombBots'
import type { RemoteEntry } from './remotesCatalog'
import type { MemberSession } from './sessionPicker'

/** Operate-list rows that are agents/bots on the far side (navbar 2nd dropdown). */
export function remoteAgentsFromOperate(payload: unknown): Array<{ id: string; label: string }> {
  return ombNavbarOptions(ombBotsFromOperate(payload))
}

/**
 * #1358 — is this remote id/kind a TrueForge instance?
 *
 * Matches the canonical `trueforge` id/kind plus named instances
 * (`trueforge_prod`, `trueforge-secondary`, `tf_local`) the same way the
 * backend `is_trueforge_remote` does, so a named instance still uses the
 * TrueForge catalog / session picker and resumes its real threads instead of
 * minting a new session every turn.
 */
export function isTrueForgeKind(id: string | null | undefined): boolean {
  const key = (id ?? '').trim().toLowerCase()
  if (!key) return false
  if (key === 'trueforge') return true
  return (
    key.startsWith('trueforge_') ||
    key.startsWith('trueforge-') ||
    key.startsWith('tf_') ||
    key.startsWith('tf-')
  )
}

export interface TrueForgeCatalogAgent {
  id: string
  label: string
  name?: string
}

export interface TrueForgeCatalogSession {
  id: string
  title?: string
  snippet?: string
  agent?: string
  created_at?: string
  updated_at?: string
}

export interface TrueForgeCatalog {
  object: string
  remote: string
  kind: 'trueforge'
  ok: boolean
  detail: string
  http_status?: number | null
  agents: TrueForgeCatalogAgent[]
  sessions: TrueForgeCatalogSession[]
}

function emptyTrueForgeCatalog(remoteId: string, detail: string): TrueForgeCatalog {
  return {
    object: 'trueforge.catalog',
    remote: remoteId,
    kind: 'trueforge',
    ok: false,
    detail,
    agents: [],
    sessions: [],
  }
}

function asCatalogAgent(raw: unknown): TrueForgeCatalogAgent | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const id = String(rec.id ?? rec.agent_id ?? rec.name ?? '').trim()
  if (!id) return null
  const label = String(rec.label ?? rec.name ?? rec.title ?? id).trim() || id
  return { id, label, name: label }
}

function asCatalogSession(raw: unknown): TrueForgeCatalogSession | null {
  const rec = asRecord(raw)
  if (!rec) return null
  const id = String(rec.id ?? rec.session_id ?? '').trim()
  if (!id) return null
  return {
    id,
    title: String(rec.title ?? id).trim() || id,
    snippet: String(rec.snippet ?? rec.agent ?? '').trim(),
    agent: String(rec.agent ?? '').trim(),
    created_at: String(rec.created_at ?? '').trim(),
    updated_at: String(rec.updated_at ?? '').trim(),
  }
}

/**
 * #1358 — TrueForge agents + sessions from the dedicated endpoint.
 *
 * Scoped to one TrueForge instance. A non-2xx response, a network failure, or
 * a malformed body degrades to an honest empty catalog (never a foreign
 * provider's rows, never the default inference profile) — this never throws.
 */
export async function fetchTrueForgeCatalog(remoteId: string): Promise<TrueForgeCatalog> {
  const rid = (remoteId || '').trim()
  if (!rid) return emptyTrueForgeCatalog(rid, 'No TrueForge remote selected.')
  const url = `/v1/remotes/${encodeURIComponent(rid)}/trueforge/`
  try {
    const response = await fetch(url, { method: 'GET', headers: buildHeaders(false) })
    if (!response.ok) {
      return emptyTrueForgeCatalog(rid, `TrueForge catalog failed (http ${response.status}).`)
    }
    const payload = asRecord(await response.json())
    if (!payload) return emptyTrueForgeCatalog(rid, 'TrueForge returned an unexpected catalog.')
    return {
      object: 'trueforge.catalog',
      remote: String(payload.remote ?? rid).trim() || rid,
      kind: 'trueforge',
      ok: payload.ok === true,
      detail: String(payload.detail ?? '').trim(),
      http_status: typeof payload.http_status === 'number' ? payload.http_status : response.status,
      agents: Array.isArray(payload.agents)
        ? payload.agents.map(asCatalogAgent).filter((row): row is TrueForgeCatalogAgent => row !== null)
        : [],
      sessions: Array.isArray(payload.sessions)
        ? payload.sessions
            .map(asCatalogSession)
            .filter((row): row is TrueForgeCatalogSession => row !== null)
        : [],
    }
  } catch {
    return emptyTrueForgeCatalog(rid, 'TrueForge is unreachable.')
  }
}

/** #1358 — TrueForge agent rows as navbar options (id + label). */
export function trueForgeAgentsFromCatalog(
  catalog: TrueForgeCatalog | null | undefined,
): Array<{ id: string; label: string }> {
  if (!catalog?.agents?.length) return []
  return catalog.agents.map((agent) => ({ id: agent.id, label: agent.label || agent.id }))
}

/** #1358 — TrueForge sessions as pickable member rows. */
export function trueForgeMemberSessions(
  remote: Pick<RemoteEntry, 'id' | 'title' | 'kind'>,
  catalog: TrueForgeCatalog | null | undefined,
): MemberSession[] {
  if (!catalog?.sessions?.length) return []
  return catalog.sessions.map((row) => ({
    id: `${remote.id}:${row.id}`,
    groupId: remote.id,
    groupKind: 'remote',
    memberId: row.id,
    title: row.title || row.id,
    snippet: row.snippet || row.agent || '',
    status: 'finished',
    startedAt: parseStartedAt(row.updated_at || row.created_at, 0),
    href: `/chat?remote=${encodeURIComponent(remote.id)}&session=${encodeURIComponent(row.id)}`,
  }))
}

/** #1358 — catalog → operate-shaped result so existing consumers read one shape. */
export async function fetchTrueForgeNavbarCatalog(remoteId: string): Promise<RemoteOperateResult> {
  const catalog = await fetchTrueForgeCatalog(remoteId)
  return {
    remote: remoteId,
    op: 'list',
    ok: catalog.ok,
    detail: catalog.detail,
    http_status: catalog.http_status ?? null,
    data: {
      agents: catalog.agents,
      sessions: catalog.sessions,
      rows_are: 'agents',
      resume_key: 'session_id',
    },
  }
}

export interface RemoteThreadRow {
  id: string
  title: string
  snippet: string
  updated_at?: string
  created_at?: string
  channel?: string
}

/**
 * Session-capable remote kinds — a **hardcoded mirror** of the backend
 * `sessions=True` declaration, NOT an independent source of truth.
 *
 * The backend owns the truth. Only two places declare it:
 *   - `src/swarm/core/remote_impls/_wiring.py` — each harness's own
 *     `capabilities=` (TrueForge :359, Octop :372, OpenMuse :391).
 *   - `src/swarm/core/remote_harness.py:285` — the `capabilities_for()`
 *     *fallback* set, consulted for an impl that is not registered yet.
 * `capabilities_for()` docs say the registered harness wins; the two agree
 * today, which is why a mirror can be checked id-by-id.
 *
 * Why the mirror exists at all: both production callers
 * (`ChatPage.tsx:1996`, `useChatSend.ts:153`) pass a synthetic
 * `{ id, kind }` built from the `?remote=` URL param, so `capabilities` is
 * always `undefined` and the backend declaration never reaches this gate.
 * Until those call sites pass the catalog entry, **this list can drift** —
 * and it did: OpenMuse was missing, so the UI showed no history for a seat
 * the adapter could enumerate. Adding an id here requires confirming
 * `sessions=True` in the backend, and re-checking it when a harness lands.
 *
 * Deliberately ABSENT because the backend declares `sessions=False` for
 * every registered impl (verified by enumerating `capabilities_for()` over
 * `_REGISTRY`): `omb`, `rakazo`, `herdr`, `swarm`. They still have
 * `list=True` — listing agents is not resuming sessions, so adding them
 * would advertise history the adapter cannot resume.
 *
 * Aliases are the spellings `remoteKinds.ts` `KIND_ALIASES` folds into each
 * canonical kind, because the URL param arrives as `kind` unnormalised.
 */
const SESSION_KINDS = new Set([
  'openwebui',
  'open-webui',
  'open_webui',
  'owui',
  'flowise',
  'flowiseai',
  'n8n',
  'n8n-io',
  'anythingllm',
  'hermes',
  'trueforge',
  'octop',
  // OpenMuse — tasks are the resumable unit (`_wiring.py:391`
  // `RemoteCapabilities(sessions=True, ...)`; also the `remote_harness.py:285`
  // fallback). Its list route is `GET /api/agent` — no trailing slash.
  'openmuse',
  'open-muse',
  'open_muse',
])

/**
 * Named Octop instances (`octop-lab`, `octop_prod`) and the tencent aliases.
 * Chat passes the URL remote id as both id and kind, so a prefix check is
 * what lets the seat load threads instead of sending with no agent.
 */
export function isOctopKind(id: string | null | undefined): boolean {
  const key = (id ?? '').trim().toLowerCase()
  if (!key) return false
  if (
    key === 'octop' ||
    key === 'tencent-octop' ||
    key === 'tencentoctop' ||
    key === 'tencent_octop'
  ) {
    return true
  }
  return key.startsWith('octop_') || key.startsWith('octop-')
}

/**
 * Does this remote enumerate resumable sessions?
 *
 * The backend declaration wins in **both** directions: an explicit
 * `capabilities.sessions` (from `remotesCatalog.ts`, which normalises it to a
 * strict boolean) is returned as-is, so a backend `false` is never overruled
 * by the `SESSION_KINDS` mirror. Only when the caller has no declaration —
 * which is the case for both production callers, hence the mirror's
 * existence — do we fall back to the kind tables below.
 *
 * Unknown/future kinds fail SAFE (`false`): a kind nobody has declared must
 * not claim session support the adapter may not have (#425 territory).
 */
export function remoteListsSessions(
  remote: Pick<RemoteEntry, 'id'> & { kind?: string; capabilities?: { sessions?: boolean } },
): boolean {
  const declared = remote.capabilities?.sessions
  if (typeof declared === 'boolean') return declared
  const kind = (remote.kind || remote.id || '').trim().toLowerCase()
  return SESSION_KINDS.has(kind) || isTrueForgeKind(kind) || isOctopKind(kind) || isOctopKind(remote.id)
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

/**
 * Harnesses stamp activity differently: TrueForge sends ISO strings, Hermes
 * sends epoch seconds (`last_active` / `started_at`). Normalise both to a
 * string the shared `parseStartedAt` reads correctly — numbers become ISO so
 * epoch seconds are never mistaken for epoch ms (a 1970 date).
 */
function normalizeStamp(value: unknown): string | undefined {
  if (typeof value === 'number' && Number.isFinite(value) && value > 0) {
    return new Date(value < 1e12 ? value * 1000 : value).toISOString()
  }
  if (typeof value === 'string' && value.trim()) return value.trim()
  return undefined
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
    // sessions — resuming one 404s on the remote (#425). Hermes nests its
    // rows one level deeper (``sessions: {object, data: [...]}``).
    const nested = asRecord(rec.sessions)
    if (Array.isArray(rec.sessions)) list = rec.sessions
    else if (nested && Array.isArray(nested.data)) list = nested.data
    else if (nested && Array.isArray(nested.sessions)) list = nested.sessions
    else if (nested && Array.isArray(nested.items)) list = nested.items
    else if (nested && (nested.id || nested.session_id)) list = [nested]
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
      updated_at: normalizeStamp(row.updated_at ?? row.updatedAt ?? row.last_active),
      created_at: normalizeStamp(row.created_at ?? row.createdAt ?? row.started_at),
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
  // #1358: TrueForge sessions come from the dedicated TrueForge catalog
  // endpoint — never the generic operate path, and never another provider.
  if (isTrueForgeKind(remote.kind) || isTrueForgeKind(remote.id)) {
    const catalog = await fetchTrueForgeCatalog(remote.id)
    return trueForgeMemberSessions(remote, catalog)
  }
  const result = await operateRemote(
    remote.id,
    { op: 'list', ...(query.trim() ? { query: query.trim() } : {}) },
    { timeoutMs: 15000 },
  )
  return memberSessionsFromRemoteOperate(remote, result)
}
